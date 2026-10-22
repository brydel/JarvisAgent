"""Passerelle facultative vers un modele local, sans outil ni repli implicite.

Bibliotheque standard. Desactivee par defaut, ecoute locale uniquement. Ce service
ne lance pas de modele et n'est pas enregistre dans le routeur Claude/Codex.
"""
from __future__ import annotations

import hmac
import http.client
import json
import os
import threading
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MAX_BODY = 32_768
MAX_RESPONSE = 524_288


@dataclass(frozen=True)
class Settings:
    enabled: bool = False
    token: str = ""
    model: str = ""
    upstream_port: int = 11434
    upstream_token: str = ""
    timeout: float = 45.0
    max_output_tokens: int = 2048

    def validate(self) -> None:
        if self.enabled and (len(self.token) < 32 or not self.model.strip()):
            raise ValueError("Activation refusee : jeton prive de 32 caracteres et modele explicite requis.")
        if not 1 <= self.upstream_port <= 65535:
            raise ValueError("Port amont invalide.")
        if not 1 <= self.timeout <= 120 or not 1 <= self.max_output_tokens <= 8192:
            raise ValueError("Limites de temps ou de sortie invalides.")
        if len(self.model) > 200 or any(ord(c) < 32 for c in self.model):
            raise ValueError("Identifiant de modele invalide.")
        if any(c in self.upstream_token for c in "\r\n"):
            raise ValueError("Jeton amont invalide.")

    @classmethod
    def environment(cls) -> "Settings":
        value = cls(enabled=os.environ.get("JARVIS_MODEL_ENABLED") == "1",
                    token=os.environ.get("JARVIS_MODEL_BRIDGE_TOKEN", ""),
                    model=os.environ.get("JARVIS_MODEL_ID", ""),
                    upstream_port=int(os.environ.get("JARVIS_MODEL_PORT", "11434")),
                    upstream_token=os.environ.get("JARVIS_MODEL_UPSTREAM_TOKEN", ""))
        value.validate()
        return value


class BridgeError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


def generate(settings: Settings, prompt: str, maximum: int) -> dict:
    """Contrat local /v1/chat/completions ; destination fixee, aucun proxy ni redirection."""
    payload = json.dumps({"model": settings.model, "messages": [{"role": "user", "content": prompt}],
                          "max_tokens": maximum, "stream": False}).encode()
    headers = {"Content-Type": "application/json"}
    if settings.upstream_token:
        headers["Authorization"] = "Bearer " + settings.upstream_token
    connection = http.client.HTTPConnection("127.0.0.1", settings.upstream_port, timeout=settings.timeout)
    try:
        connection.request("POST", "/v1/chat/completions", payload, headers)
        response = connection.getresponse()
        if response.status != 200:
            raise BridgeError(502, "Le serveur de modele a refuse la demande. Aucun repli effectue.")
        raw = response.read(MAX_RESPONSE + 1)
        if len(raw) > MAX_RESPONSE:
            raise BridgeError(502, "Reponse du modele trop volumineuse.")
        body = json.loads(raw)
        text = body["choices"][0]["message"]["content"]
        if not isinstance(text, str):
            raise ValueError("texte attendu")
        # Ne pas relayer appels d'outils, metadonnees privees ou champs arbitraires.
        return {"text": text, "model": settings.model, "provider": "local_optional", "tool_calls_executed": False}
    except BridgeError:
        raise
    except (OSError, ValueError, KeyError, IndexError, TypeError, http.client.HTTPException) as exc:
        raise BridgeError(502, "Modele indisponible ou reponse invalide. Aucun repli effectue.") from exc
    finally:
        connection.close()


def server(settings: Settings, port: int = 7731) -> ThreadingHTTPServer:
    settings.validate()
    gate = threading.BoundedSemaphore(1)

    class Handler(BaseHTTPRequestHandler):
        server_version = "JarvisModelBridge/1"
        protocol_version = "HTTP/1.0"

        def setup(self):
            super().setup()
            self.connection.settimeout(10)

        def log_message(self, *args):
            pass  # Ni requetes, ni prompts, ni identifiants dans les journaux.

        def reply(self, code: int, data: dict):
            body = json.dumps(data, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            try:
                self.wfile.write(body)
            except OSError:
                pass

        def local(self) -> bool:
            port = self.server.server_address[1]
            return self.headers.get("Host") in (f"127.0.0.1:{port}", f"localhost:{port}") and not self.headers.get("Origin")

        def do_GET(self):  # noqa: N802
            if not self.local():
                return self.reply(403, {"error": "Acces local serveur uniquement."})
            if self.path != "/health":
                return self.reply(404, {"error": "Route inconnue."})
            self.reply(200, {"enabled": settings.enabled, "upstream_verified": False,
                             "default_provider": False, "protocol": 1})

        def do_POST(self):  # noqa: N802
            if not self.local():
                return self.reply(403, {"error": "Acces local serveur uniquement."})
            if self.path != "/v1/generate":
                return self.reply(404, {"error": "Route inconnue."})
            if not settings.enabled:
                return self.reply(503, {"error": "Passerelle desactivee. Claude et Codex restent les fournisseurs par defaut."})
            supplied = self.headers.get("Authorization", "")
            expected = "Bearer " + settings.token
            if not hmac.compare_digest(supplied.encode(), expected.encode()):
                return self.reply(401, {"error": "Authentification requise."})
            if self.headers.get("Transfer-Encoding") or self.headers.get_content_type() != "application/json":
                return self.reply(415, {"error": "JSON borne avec Content-Length requis."})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 1 <= length <= MAX_BODY:
                    return self.reply(413, {"error": "Corps trop grand ou absent."})
                data = json.loads(self.rfile.read(length))
                if not isinstance(data, dict) or set(data) - {"prompt", "max_tokens"}:
                    raise ValueError("champs non autorises")
                prompt = data.get("prompt")
                maximum = data.get("max_tokens", settings.max_output_tokens)
                if not isinstance(prompt, str) or not 1 <= len(prompt.strip()) <= 24_000:
                    raise ValueError("prompt invalide")
                if isinstance(maximum, bool) or not isinstance(maximum, int) or not 1 <= maximum <= settings.max_output_tokens:
                    raise ValueError("limite invalide")
            except (ValueError, TypeError, OSError):
                return self.reply(400, {"error": "Demande invalide. Seuls prompt et max_tokens sont acceptes."})
            if not gate.acquire(blocking=False):
                return self.reply(429, {"error": "Une inference est deja en cours. Reessaie plus tard."})
            try:
                self.reply(200, generate(settings, prompt, maximum))
            except BridgeError as exc:
                self.reply(exc.status, {"error": str(exc)})
            finally:
                gate.release()

    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    httpd.daemon_threads = True
    return httpd


if __name__ == "__main__":
    srv = server(Settings.environment())
    print("Passerelle locale sur 127.0.0.1:7731 ; aucune inference automatique.", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
