"""Transport HTTPS borné : résolution publique, adresse épinglée et aucun redirect implicite."""

from __future__ import annotations

import http.client
import base64
import ipaddress
import json
import os
import re
import socket
import ssl
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlencode, urlsplit

MAX_REPONSE = 1_000_000


class TransportError(ValueError):
    """Erreur publique expurgée, sans URL complète ni credential."""


def cible(url: str) -> tuple[str, int, str]:
    if not isinstance(url, str) or not 1 <= len(url) <= 4000 or any(ord(c) < 33 for c in url):
        raise TransportError("URL HTTPS invalide.")
    try:
        u = urlsplit(url)
        if u.scheme != "https" or u.username or u.password or u.fragment or not u.hostname:
            raise ValueError
        host = u.hostname.rstrip(".").encode("idna").decode("ascii").lower()
        if not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", host) or ".." in host:
            raise ValueError
        if any(k.lower() in {"token", "key", "api_key", "access_token", "authorization", "password", "secret"}
               for k, _ in parse_qsl(u.query)):
            raise ValueError
        port = u.port or 443
        if port != 443:
            raise ValueError
    except (ValueError, UnicodeError) as exc:
        raise TransportError("URL HTTPS publique sans credential, fragment ni port personnalisé requise.") from exc
    return host, port, (u.path or "/") + ("?" + u.query if u.query else "")


def _adresse(host: str, port: int) -> str:
    try:
        addresses = list(dict.fromkeys(x[4][0] for x in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)))
        if not addresses or any(not ipaddress.ip_address(ip).is_global for ip in addresses):
            raise TransportError("Destination privée, locale ou réservée refusée.")
        return addresses[0]
    except (OSError, ValueError) as exc:
        raise TransportError("Résolution de la destination impossible ou non publique.") from exc


class _Connexion(http.client.HTTPSConnection):
    def __init__(self, host: str, port: int, adresse: str, timeout: float):
        super().__init__(host, port, timeout=timeout, context=ssl.create_default_context())
        self.adresse = adresse

    def connect(self):
        # Ne pas résoudre une seconde fois : le socket utilise exactement l'adresse validée.
        sock = socket.create_connection((self.adresse, self.port), self.timeout)
        try:
            self.sock = self._context.wrap_socket(sock, server_hostname=self.host)
        except BaseException:
            sock.close()
            raise


def _proxy(host: str, port: int, timeout: float):
    """Proxy approuvé par le propriétaire, réservé à une liste exacte de noms publics.

    Le proxy est ici la frontière réseau de confiance : il résout la cible et doit refuser les adresses
    privées/réservées. Son IP finale n'est pas observable dans CONNECT. Le TLS de la cible reste vérifié.
    Aucune variable HTTPS_PROXY ambiante n'est activée sans la configuration explicite JARVIS_*.
    """
    proxy = os.environ.get("JARVIS_HTTPS_PROXY", "")
    if not proxy:
        return None
    allowed = {h.strip().lower().rstrip(".") for h in os.environ.get("JARVIS_PROXY_HOTES_AUTORISES", "").split(",") if h.strip()}
    if host not in allowed or host in {"localhost", "localhost.localdomain"} or host.endswith((".local", ".localhost", ".internal")):
        raise TransportError("Hôte absent du périmètre exact du proxy approuvé.")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise TransportError("Le proxy approuvé accepte seulement des noms publics exacts, sans adresse littérale.")
    try:
        p = urlsplit(proxy)
        if (p.scheme != "http" or not p.hostname or p.path not in ("", "/") or p.query or p.fragment
                or len(proxy) > 4000 or any(ord(c) < 33 for c in proxy)):
            raise ValueError
        proxy_port = p.port or 80
        if not 1 <= proxy_port <= 65535:
            raise ValueError
        headers = {}
        if p.username is not None:
            credentials = unquote(p.username) + ":" + unquote(p.password or "")
            if any(ord(c) < 32 for c in credentials):
                raise ValueError
            headers["Proxy-Authorization"] = "Basic " + base64.b64encode(credentials.encode()).decode("ascii")
        connexion = http.client.HTTPSConnection(p.hostname, proxy_port, timeout=timeout, context=ssl.create_default_context())
        connexion.set_tunnel(host, port, headers=headers)
        return connexion
    except (ValueError, UnicodeError) as exc:
        raise TransportError("Configuration du proxy approuvé invalide.") from exc


def _lire(response, connexion, maximum, echeance, attendre_rpc_id):
    data = bytearray()
    sse = response.getheader("Content-Type", "").split(";", 1)[0].strip() == "text/event-stream"
    while True:
        restant = echeance - time.monotonic()
        if restant <= 0:
            raise TransportError("Délai total HTTPS dépassé.")
        if connexion.sock is not None:
            connexion.sock.settimeout(restant)
        chunk = response.read1(min(4096, maximum + 1 - len(data)))
        if not chunk:
            return bytes(data)
        data.extend(chunk)
        if len(data) > maximum:
            raise TransportError("Réponse trop volumineuse.")
        if sse and attendre_rpc_id is not None:
            # La connexion peut rester ouverte après la réponse. Ne pas attendre EOF ; ignorer les
            # keepalives et notifications puis s'arrêter au premier événement corrélé complet.
            frames = re.split(br"\r\n\r\n|\n\n|\r\r", data)
            for frame in frames[:-1]:
                parts = [line[5:].lstrip(b" ") for line in frame.splitlines() if line.startswith(b"data:")]
                if not parts:
                    continue
                try:
                    message = json.loads(b"\n".join(parts))
                except (ValueError, UnicodeError, RecursionError) as exc:
                    raise TransportError("Événement SSE JSON invalide.") from exc
                if (isinstance(message, dict) and message.get("jsonrpc") == "2.0"
                        and type(message.get("id")) is int and message["id"] == attendre_rpc_id):
                    return b"data: " + json.dumps(message, ensure_ascii=False, allow_nan=False).encode() + b"\n\n"


def _requete_directe(url: str, *, methode: str = "GET", donnees: dict | None = None,
                     entetes: dict | None = None, timeout: float = 10, maximum: int = MAX_REPONSE,
                     attendre_rpc_id: int | None = None, _echeance: float | None = None,
                     formulaire: dict | None = None, annulation=None) -> dict:
    """Partie réseau privée ; exécutée en processus isolé en production."""
    echeance = _echeance if _echeance is not None else time.monotonic() + timeout
    host, port, chemin = cible(url)
    if methode not in {"GET", "POST"} or not 0 < timeout <= 120 or not 0 < maximum <= MAX_REPONSE:
        raise TransportError("Paramètres de transport invalides.")
    if formulaire is not None and (donnees is not None or methode != "POST" or not isinstance(formulaire, dict)
            or any(not isinstance(k, str) or not isinstance(v, str) for k, v in formulaire.items())):
        raise TransportError("Formulaire de transport invalide.")
    if annulation is not None:
        annulation.verifier()
    body = (urlencode(formulaire).encode() if formulaire is not None else
            None if donnees is None else json.dumps(donnees, allow_nan=False, ensure_ascii=False).encode())
    if body is not None and len(body) > 128_000:
        raise TransportError("Requête trop volumineuse.")
    headers = {"User-Agent": "JarvisOS/1", "Accept-Encoding": "identity", **(entetes or {})}
    if body is not None:
        headers["Content-Type"] = "application/x-www-form-urlencoded" if formulaire is not None else "application/json"
    connexion = _proxy(host, port, timeout)
    if connexion is None:
        connexion = _Connexion(host, port, _adresse(host, port), timeout)
    try:
        connexion.request(methode, chemin, body=body, headers=headers)
        response = connexion.getresponse()
        if response.getheader("Content-Encoding", "identity").lower() not in ("", "identity"):
            raise TransportError("Réponse compressée non prise en charge.")
        if 300 <= response.status < 400:
            raise TransportError("Redirection refusée : autoriser explicitement la destination finale.")
        data = _lire(response, connexion, maximum, echeance, attendre_rpc_id)
        return {"status": response.status, "entetes": {k.lower(): v for k, v in response.getheaders()
                if k.lower() in {"content-type", "mcp-session-id", "content-encoding"}},
                "contenu": data}
    except (OSError, http.client.HTTPException) as exc:
        raise TransportError("Connexion HTTPS interrompue ou indisponible.") from exc
    finally:
        connexion.close()


def _worker():
    """Protocole privé stdin/stdout ; aucun secret n'est passé dans la ligne de commande."""
    try:
        args = json.loads(sys.stdin.buffer.read(256000))
        result = _requete_directe(**args)
        result["contenu"] = base64.b64encode(result["contenu"]).decode("ascii")
        print(json.dumps({"resultat": result}, allow_nan=False))
    except BaseException:
        # Ne jamais renvoyer traceback, arguments, endpoint complet ou valeur d'environnement.
        print('{"erreur":"Requête HTTPS refusée, interrompue ou indisponible."}')


_WORKER_CODE = "import sys; sys.path.insert(0, sys.argv[1]); from jarvis.outils_http import _worker; _worker()"


def requete(url: str, *, methode: str = "GET", donnees: dict | None = None,
            entetes: dict | None = None, timeout: float = 10, maximum: int = MAX_REPONSE,
            attendre_rpc_id: int | None = None, formulaire: dict | None = None, annulation=None) -> dict:
    """Borne dure incluant DNS, TLS, en-têtes et serveur trickle, sans thread réseau orphelin.

    Le parent arrête le processus réseau à échéance ; le socket ferme avec lui. Le délai n'est pas
    réinitialisé par les octets reçus. Les en-têtes viennent uniquement du contrôleur de connexion.
    """
    cible(url)
    if (type(timeout) not in (int, float) or not 0 < timeout <= 120 or type(maximum) is not int
            or not 0 < maximum <= MAX_REPONSE or (attendre_rpc_id is not None and type(attendre_rpc_id) is not int)):
        raise TransportError("Paramètres de transport invalides.")
    if formulaire is not None and (donnees is not None or methode != "POST" or not isinstance(formulaire, dict)
            or any(not isinstance(k, str) or not isinstance(v, str) for k, v in formulaire.items())):
        raise TransportError("Formulaire de transport invalide.")
    args = {"url": url, "methode": methode, "donnees": donnees, "entetes": entetes, "timeout": timeout,
            "formulaire": formulaire,
            "maximum": maximum, "attendre_rpc_id": attendre_rpc_id, "_echeance": time.monotonic() + timeout}
    proc = None
    try:
        payload = json.dumps(args, allow_nan=False).encode()
        if len(payload) > 250000:
            raise ValueError
        def lancer():
            return subprocess.Popen([sys.executable, "-c", _WORKER_CODE, str(Path(__file__).resolve().parents[1])],
                                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                    start_new_session=os.name == "posix")
        proc = annulation.demarrer(lancer) if annulation is not None else lancer()
        entree = payload
        while True:
            if annulation is not None:
                annulation.verifier()
            restant = args["_echeance"] - time.monotonic()
            if restant <= 0:
                raise subprocess.TimeoutExpired("HTTPS", timeout)
            try:
                stdout, _ = proc.communicate(input=entree, timeout=min(0.1, restant))
            except subprocess.TimeoutExpired:
                entree = None
                continue
            break
        if annulation is not None:
            annulation.verifier()
        data = json.loads(stdout)
        if proc.returncode != 0 or "resultat" not in data:
            raise ValueError
        response = data["resultat"]
        response["contenu"] = base64.b64decode(response["contenu"], validate=True)
        if len(response["contenu"]) > maximum:
            raise ValueError
        return response
    except subprocess.TimeoutExpired as exc:
        raise TransportError("Délai total HTTPS dépassé ; processus réseau arrêté.") from exc
    except (ValueError, OSError, KeyError, TypeError) as exc:
        raise TransportError("Requête HTTPS refusée, interrompue ou indisponible.") from exc
    finally:
        if proc is not None:
            from .annulation import _arreter
            _arreter(proc)
