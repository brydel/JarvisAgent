"""Tableau de bord web de l'usine : le plan des ateliers dans le navigateur, en lecture seule.

Servi par le démon sur 127.0.0.1 uniquement (accessible depuis Windows par http://localhost:7717).
Aucune action n'est possible d'ici : approuver un plan reste réservé au cockpit, au terminal et à
Telegram. La page ne montre aucun secret, et le serveur refuse toute requête qui ne vise pas ce PC.
"""

from __future__ import annotations

import json
import mimetypes
import shutil
import subprocess
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import config, store

PAGE = Path(__file__).with_name("usine.html")
CACHE_SECS = 2.0
_cache: dict = {"ts": 0.0, "body": b""}
_cache_lock = threading.Lock()


def etat() -> dict:
    """Tout ce que la page affiche, en un seul objet JSON."""
    from . import modeles, report, roles, taches, usage
    snap = report.snapshot()
    agents = []
    for a in snap["agents"] or []:
        agents.append({
            "projet": a["project"], "worktree": a["worktree"], "statut": a["status"], "duree": a["elapsed"],
            "titre": a["title"], "fournisseur": (a["kind"] or (a.get("tache") or {}).get("agent") or "").lower(),
            "role": a.get("role") or "", "modele": a.get("modele") or "", "effort": a.get("effort") or "",
            "issue": a.get("issue") or "", "raison": (a.get("tache") or {}).get("raison", ""),
            "taille": (a.get("tache") or {}).get("taille", ""), "plan": (a.get("tache") or {}).get("plan", ""),
        })
    alerte, arret = usage.thresholds()
    jetons = {}
    for nom, u in (snap["usage"] or {}).items():
        jetons[nom] = {"niveau": u["niveau"], "marge": u.get("marge"), "source": u.get("source"),
                       "fenetres": {k: {"pct": u[k]["used"], "reset": usage.fmt_reset(u[k].get("resets_at"))}
                                    for k in ("5h", "semaine") if u.get(k)},
                       "reprise": usage.fmt_reset(u.get("reprise")), "prevision": u.get("prevision")}

    def _plan(p: dict) -> dict:
        return {"id": p["id"], "titre": p["titre"], "mode": p["mode"], "pourquoi": p.get("resume", ""),
                "items": [{"projet": i["projet"], "issue": i["issue"], "role": i.get("role", ""),
                           "affectation": modeles.libelle(i["agent"], i.get("modele", ""), i.get("effort", "")),
                           "lance": i["lance"], "desc": i.get("desc", "")} for i in p["items"]]}

    return {
        "ts": time.time(),
        "equipes": [{"nom": eq, "roles": [{k: r[k] for k in ("nom", "titre", "court", "sigle", "couleur", "resume")}
                                          for r in membres]} for eq, membres in roles.par_equipe()],
        "agents": agents, "agents_erreur": snap["agents_error"] if snap["agents"] is None else "",
        "occupes": snap["busy"], "capacite": snap["max_agents"], "capacite_base": snap["max_base"],
        "capacite_raisons": snap["capacite_raisons"], "pause": snap["paused"], "chef": snap["chef"],
        "pauses": snap.get("pauses") or {}, "reservations": snap.get("reservations", 0), "lourdes": snap.get("lourdes", 0),
        "exceptions": snap.get("exceptions", 0), "profil": snap.get("profil") or "", "config_erreurs": snap.get("config_erreurs") or [],
        "demon": snap["demon"], "telegram": bool(config.settings()["telegram"].get("chat_id")),
        "jetons": jetons, "seuils": {"alerte": alerte, "arret": arret},
        "plans": [_plan(p) for p in snap["pending"]], "en_cours": [_plan(p) for p in snap["active"]],
        "propositions": [{"id": i["id"], "nom": i["nom"], "fournisseur": i["champs"].get("fournisseur"),
                          "pourquoi": i.get("pourquoi", ""), "source": i.get("source", "")}
                         for i in snap["propositions"]],
        "livrables": [{"id": i["id"], "titre": i["titre"], "genre": i["genre"], "projet": i["projet"],
                       "issue": i["issue"], "ts": i["ts"], "envoye": i["envoye"], "octets": i["octets"],
                       "planche": bool(i.get("planche"))} for i in reversed(snap["livrables"])],
        "projets": [{"nom": n, "priorite": p["priorite"], "actif": p["actif"]}
                    for n, p in sorted(snap["projects"].items(), key=lambda kv: (kv[1]["priorite"], kv[0]))],
        "fil": [{"ts": e["ts"], "type": e.get("type", ""), "texte": e.get("texte", "")} for e in store.feed_tail(40)],
        "bilan": taches.bilan(7),
        "executions": _executions(),
    }


def _executions() -> list[dict]:
    try:
        from . import observabilite
        return observabilite.dernieres_executions(20)
    except Exception:  # noqa: BLE001 — le tableau de bord s'affiche même si un registre est illisible
        return []


def _etat_json() -> bytes:
    with _cache_lock:
        if time.time() - _cache["ts"] > CACHE_SECS:
            try:
                body = json.dumps(etat(), ensure_ascii=False, default=str).encode()
            except Exception as exc:  # noqa: BLE001 — la page affiche l'erreur au lieu de rester figée
                body = json.dumps({"erreur": str(exc), "ts": time.time()}).encode()
            _cache.update(ts=time.time(), body=body)
        return _cache["body"]


class Handler(BaseHTTPRequestHandler):
    server_version = "Jarvis"

    def _send(self, code: int, body: bytes, ctype: str = "text/plain; charset=utf-8") -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy",
                         "default-src 'self'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; img-src 'self' data:")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _local(self) -> bool:
        # Une page web malveillante peut viser 127.0.0.1 sous un autre nom de domaine : on n'accepte
        # que les requêtes adressées à ce PC par son nom local.
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]").lower()
        return host in ("localhost", "127.0.0.1", "::1")

    def _fichier(self, path: Path) -> None:
        """Sert un livrable enregistré (lecture par plages, pour que les vidéos se lisent et s'avancent)."""
        try:
            size = path.stat().st_size
        except OSError:
            self._send(404, "Fichier introuvable : il a peut-être été déplacé.".encode())
            return
        start, end = 0, size - 1
        rng = self.headers.get("Range", "")
        partial = False
        if rng.startswith("bytes="):
            a, _, b = rng[6:].partition("-")
            try:
                if a:
                    start = int(a)
                    end = min(int(b), size - 1) if b else size - 1
                else:
                    start = max(0, size - int(b))
                partial = True
            except ValueError:
                start, end, partial = 0, size - 1, False
            if start > end or start >= size:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.end_headers()
                return
        self.send_response(206 if partial else 200)
        # Vidéos et images s'affichent dans la page ; tout le reste (HTML, Markdown, PDF…) se télécharge
        # et ne s'exécute jamais sur l'origine du tableau de bord : un livrable est écrit par un agent.
        from . import studio
        en_ligne = studio.genre(path) in ("video", "image")
        ctype = (mimetypes.guess_type(path.name)[0] if en_ligne else None) or "application/octet-stream"
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(end - start + 1))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "sandbox; default-src 'none'")
        if not en_ligne:
            nom = "".join(c if c.isalnum() or c in "._-" else "_" for c in path.name)
            self.send_header("Content-Disposition", f'attachment; filename="{nom}"')
        if partial:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        if self.command == "HEAD":
            return
        try:
            with path.open("rb") as fh:
                fh.seek(start)
                left = end - start + 1
                while left > 0:
                    chunk = fh.read(min(256 * 1024, left))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    left -= len(chunk)
        except (OSError, ConnectionError):
            pass  # le navigateur a fermé la lecture : rien à faire

    def do_GET(self):  # noqa: N802
        if not self._local():
            self._send(403, "Ce tableau de bord ne répond qu'à ce PC (http://localhost).".encode())
            return
        route = self.path.split("?", 1)[0]
        if route in ("/", "/index.html"):
            try:
                self._send(200, PAGE.read_bytes(), "text/html; charset=utf-8")
            except OSError:
                self._send(500, b"usine.html introuvable")
        elif route == "/api/etat":
            self._send(200, _etat_json(), "application/json; charset=utf-8")
        elif route.startswith(("/livrable/", "/planche/")):
            # Seuls les fichiers inscrits au registre des livrables sont servis, jamais un chemin libre.
            from . import livrables
            genre, _, ident = route[1:].partition("/")
            item = next((i for i in livrables.tous() if i["id"] == ident.upper()), None)
            cible = (item or {}).get("fichier" if genre == "livrable" else "planche")
            reel = livrables.chemin_servi(cible) if cible else None
            if not reel:
                self._send(404, "Livrable inconnu, déplacé, ou qui n'est plus dans le dossier des livrables.".encode())
                return
            self._fichier(reel)
        else:
            self._send(404, "Page inconnue.".encode())

    do_HEAD = do_GET  # noqa: N815

    def log_message(self, *args):  # silencieux : le démon a son propre fil d'activité
        pass


def _serveur(port: int) -> ThreadingHTTPServer:
    ThreadingHTTPServer.allow_reuse_address = True
    ThreadingHTTPServer.daemon_threads = True
    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def serve(stop: threading.Event, port: int) -> None:
    """Fil du démon : sert la page tant que le démon tourne. Un port occupé n'arrête pas le démon."""
    try:
        httpd = _serveur(port)
    except OSError as exc:
        store.feed_add("erreur", f"tableau de bord web : port {port} indisponible ({exc})")
        return
    httpd.timeout = 1
    try:
        while not stop.is_set():
            httpd.handle_request()
    finally:
        httpd.server_close()


def _repond(port: int) -> bool:
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # jamais par un proxy
        with opener.open(f"http://127.0.0.1:{port}/api/etat", timeout=3) as resp:
            return resp.status == 200
    except OSError:
        return False


def _ouvrir(url: str) -> None:
    """Ouvre le navigateur de Windows (WSL) ou du poste. Sans effet si c'est impossible."""
    for cmd in (["wslview", url], ["cmd.exe", "/c", "start", "", url], ["xdg-open", url]):
        if shutil.which(cmd[0]):
            try:
                subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
                return
            except OSError:
                continue


def main(port: int | None = None) -> int:
    """`jarvis web` : ouvre le tableau de bord (et le sert ici si le démon ne le fait pas déjà)."""
    port = port or int(config.settings()["web"].get("port", 7717))
    url = f"http://localhost:{port}"
    if _repond(port):
        print(f"Tableau de bord : {url} (servi par le démon)")
        _ouvrir(url)
        return 0
    try:
        httpd = _serveur(port)
    except OSError as exc:
        print(f"Erreur : port {port} indisponible ({exc}). Change-le : jarvis regler web.port 7720")
        return 1
    print(f"Tableau de bord : {url} (lecture seule, ce PC uniquement). Ctrl+C pour arrêter.")
    _ouvrir(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return 0
