"""Jarvis Studio (M2, local) : API authentifiée au-dessus du moteur de missions, et la page Board.

Servi sur 127.0.0.1 uniquement (`jarvis mission studio`). Le navigateur n'est jamais une source de vérité : chaque
réponse est relue dans la base des missions, et le flux d'événements reprend au dernier numéro reçu.

Sécurité (chaque point est testé dans tests/test_studio.py) :
- seules les requêtes adressées à ce PC par son nom local sont servies (parade au DNS rebinding) ;
- authentification par un jeton secret (~/.config/jarvis/studio_jeton, 600) échangé contre un cookie de session
  HttpOnly, SameSite=Strict ; le jeton voyage dans le fragment d'URL (#…), jamais dans une requête ni un journal ;
- toute écriture exige l'en-tête X-Jarvis-Studio et, si le navigateur l'envoie, une Origin locale : une autre page
  web ne peut pas agir à ta place ; aucune réponse CORS ;
- l'API ne lance aucun processus, n'expose aucun shell ni identifiant : elle appelle les fonctions de missions.py,
  qui appliquent la politique. Les approbations faites ici sont celles de l'humain authentifié ;
- CSP stricte (pas de script en ligne, aucune ressource externe) ; les contenus sont affichés comme du texte.

Limite : une seule organisation (le tenant local) et un seul utilisateur ; les comptes et membres viennent avec
PostgreSQL (docs/jarvis-next/MIGRATION_ROADMAP.md).
"""

from __future__ import annotations

import hmac
import json
import os
import re
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from . import config, missions

PORT_DEFAUT = 7718
STATIQUES = {
    "/": ("studio_board.html", "text/html; charset=utf-8"),
    "/studio.js": ("studio_board.js", "text/javascript; charset=utf-8"),
    "/studio.css": ("studio_board.css", "text/css; charset=utf-8"),
}
DOSSIER = Path(__file__).resolve().parent
COOKIE = "jarvis_studio"
SESSION_S = 12 * 3600
CORPS_MAX = 60_000
HOTES_LOCAUX = ("localhost", "127.0.0.1", "::1")
CSP = ("default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; "
       "base-uri 'none'; form-action 'self'; frame-ancestors 'none'")
ID = re.compile(r"^[A-Z]{2,3}-[0-9a-f]{12}$")

_sessions: dict[str, float] = {}
_verrou = threading.Lock()


def chemin_jeton() -> Path:
    return config.CONFIG_DIR / "studio_jeton"


def jeton(*, nouveau: bool = False) -> str:
    """Le secret d'accès au Studio, créé au premier lancement (600). `nouveau` le remplace et ferme les sessions."""
    p = chemin_jeton()
    if not nouveau:
        try:
            valeur = p.read_text().strip()
            if len(valeur) >= 32:
                return valeur
        except OSError:
            pass
    p.parent.mkdir(parents=True, exist_ok=True)
    valeur = secrets.token_urlsafe(32)
    fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as fh:
        fh.write(valeur + "\n")
    os.chmod(p, 0o600)
    with _verrou:
        _sessions.clear()
    return valeur


def _ouvrir_session() -> str:
    sid = secrets.token_urlsafe(32)
    with _verrou:
        maintenant = time.time()
        for k in [k for k, v in _sessions.items() if v < maintenant]:
            del _sessions[k]
        _sessions[sid] = maintenant + SESSION_S
    return sid


def _session_valide(sid: str) -> bool:
    with _verrou:
        fin = _sessions.get(sid)
        return bool(fin and fin > time.time())


class Handler(BaseHTTPRequestHandler):
    server_version = "JarvisStudio/1"
    protocol_version = "HTTP/1.1"

    # --- réponses ---
    def _envoyer(self, code: int, corps: bytes, ctype: str = "application/json; charset=utf-8",
                 entetes: dict | None = None) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(corps)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", CSP)
        for k, v in (entetes or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(corps)

    def _json(self, code: int, data) -> None:
        self._envoyer(code, json.dumps(data, ensure_ascii=False).encode())

    def _erreur(self, code: int, message: str) -> None:
        self._json(code, {"erreur": message})

    # --- contrôles ---
    def _local(self) -> bool:
        hote = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]").lower()
        return hote in HOTES_LOCAUX

    def _origine_locale(self) -> bool:
        origine = self.headers.get("Origin")
        if origine is None:
            return True  # navigateur qui n'en envoie pas (même origine, GET) ; l'en-tête personnalisé suffit
        hote = (urlsplit(origine).hostname or "").lower()
        return hote in HOTES_LOCAUX and urlsplit(origine).port == self.server.server_address[1]

    def _cookie(self) -> str:
        for morceau in (self.headers.get("Cookie") or "").split(";"):
            nom, _, valeur = morceau.strip().partition("=")
            if nom == COOKIE:
                return valeur
        return ""

    def _authentifie(self) -> bool:
        return _session_valide(self._cookie())

    def _corps(self) -> dict | None:
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return None
        if n <= 0 or n > CORPS_MAX:
            return None
        try:
            data = json.loads(self.rfile.read(n).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None
        return data if isinstance(data, dict) else None

    # --- GET ---
    def do_GET(self):  # noqa: N802
        if not self._local():
            self._erreur(403, "Jarvis Studio ne répond qu'à ce PC (http://localhost).")
            return
        url = urlsplit(self.path)
        route, q = url.path, parse_qs(url.query)
        if route in STATIQUES or route == "/connexion":
            fichier, ctype = STATIQUES["/" if route == "/connexion" else route]
            try:
                self._envoyer(200, (DOSSIER / fichier).read_bytes(), ctype)
            except OSError:
                self._erreur(500, f"{fichier} introuvable")
            return
        if route == "/api/session":
            self._json(200, {"authentifie": self._authentifie()})
            return
        if not route.startswith("/api/"):
            self._erreur(404, "Page inconnue.")
            return
        if not self._authentifie():
            self._erreur(401, "Session absente ou expirée : rouvre le lien donné par « jarvis mission studio ».")
            return
        org = missions.tenant_local()
        try:
            if route == "/api/board":
                self._json(200, {"objets": missions.board(org, (q.get("espace") or ["accueil"])[0][:80])})
            elif route == "/api/missions":
                self._json(200, {"missions": missions.missions(org, 50)})
            elif route.startswith("/api/missions/"):
                mid = route.rsplit("/", 1)[1]
                if not ID.match(mid):
                    self._erreur(404, "mission inconnue")
                    return
                self._json(200, missions.mission(org, mid))
            elif route == "/api/approbations":
                self._json(200, {"approbations": missions.approbations_en_attente(org)})
            elif route == "/api/execution":
                self._json(200, missions.etat_execution(org))
            elif route == "/api/evenements":
                apres = int((q.get("apres") or ["0"])[0] or 0)
                self._json(200, {"evenements": missions.evenements(org, apres=apres)})
            elif route == "/api/flux":
                apres = self.headers.get("Last-Event-ID") or (q.get("apres") or ["0"])[0]
                self._flux(org, int(apres or 0))
            else:
                self._erreur(404, "Route inconnue.")
        except ValueError:
            self._erreur(400, "paramètre invalide")
        except missions.MissionError as exc:
            self._erreur(404 if exc.code == "inconnue" else 400, str(exc))

    def _flux(self, org: str, apres: int) -> None:
        """Server-Sent Events : chaque événement porte son numéro ; le navigateur reprend où il s'était arrêté."""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True
        dernier_signe = time.time()
        arret = getattr(self.server, "arret", None)
        try:
            self.wfile.write(b"retry: 2000\n\n")
            while not (arret and arret.is_set()) and _session_valide(self._cookie()):
                lot = missions.evenements(org, apres=apres)
                for e in lot:
                    apres = e["seq"]
                    self.wfile.write(f"id: {e['seq']}\ndata: {json.dumps(e, ensure_ascii=False)}\n\n".encode())
                if lot:
                    self.wfile.flush()
                elif time.time() - dernier_signe > 15:
                    self.wfile.write(b": battement\n\n")
                    self.wfile.flush()
                    dernier_signe = time.time()
                time.sleep(getattr(self.server, "intervalle_flux", 0.5))
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass

    # --- écritures ---
    def _ecriture_autorisee(self) -> bool:
        if not self._local():
            self._erreur(403, "Jarvis Studio ne répond qu'à ce PC.")
            return False
        if self.headers.get("X-Jarvis-Studio") != "1" or not self._origine_locale():
            self._erreur(403, "Requête d'une autre origine refusée.")
            return False
        return True

    def do_POST(self):  # noqa: N802
        if not self._ecriture_autorisee():
            return
        route = urlsplit(self.path).path
        corps = self._corps()
        if corps is None:
            self._erreur(400, "Corps JSON attendu (60 000 octets au plus).")
            return
        if route == "/api/session":
            attendu = jeton()
            fourni = str(corps.get("jeton") or "")
            if not fourni or not hmac.compare_digest(fourni.encode(), attendu.encode()):
                time.sleep(0.3)  # ralentit les essais
                self._erreur(401, "Jeton invalide.")
                return
            sid = _ouvrir_session()
            self._envoyer(200, b'{"authentifie": true}', entetes={
                "Set-Cookie": f"{COOKIE}={sid}; HttpOnly; SameSite=Strict; Path=/; Max-Age={SESSION_S}"})
            return
        if not self._authentifie():
            self._erreur(401, "Session absente ou expirée.")
            return
        org = missions.tenant_local()
        try:
            if route == "/api/board":
                o = missions.board_ajouter(org, str(corps.get("espace") or "accueil")[:80],
                                           str(corps.get("type") or "note"), str(corps.get("contenu") or ""),
                                           auteur="studio", x=float(corps.get("x") or 0), y=float(corps.get("y") or 0))
                self._json(201, o)
            elif m := re.match(r"^/api/board/(BO-[0-9a-f]{12})/position$", route):
                missions.board_deplacer(org, m.group(1), corps.get("x", 0), corps.get("y", 0), par="studio")
                self._json(200, {"ok": True})
            elif m := re.match(r"^/api/approbations/(AP-[0-9a-f]{12})$", route):
                accord = corps.get("accord")
                if not isinstance(accord, bool):
                    self._erreur(400, "« accord » doit valoir true ou false")
                    return
                statut = missions.decider_approbation(org, m.group(1), accord, acteur="studio:humain",
                                                      acteur_type="humain")
                self._json(200, {"statut": statut})
            elif m := re.match(r"^/api/missions/(MI-[0-9a-f]{12})/annuler$", route):
                self._json(200, {"annulees": missions.annuler_mission(org, m.group(1), par="studio:humain")})
            else:
                self._erreur(404, "Route inconnue.")
        except (TypeError, ValueError):
            self._erreur(400, "valeur invalide")
        except missions.MissionError as exc:
            self._erreur(404 if exc.code == "inconnue" else 409 if exc.code in ("approbation", "transition") else 400,
                         str(exc))

    def do_HEAD(self):  # noqa: N802
        if urlsplit(self.path).path in STATIQUES:
            self.do_GET()
        else:
            self._erreur(405, "HEAD seulement sur les pages.")

    def log_message(self, *args):
        pass  # aucune URL journalisée : rien ne doit y traîner


def serveur(port: int = PORT_DEFAUT) -> ThreadingHTTPServer:
    ThreadingHTTPServer.allow_reuse_address = True
    ThreadingHTTPServer.daemon_threads = True
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    httpd.arret = threading.Event()
    httpd.intervalle_flux = 0.5
    return httpd


def lien(port: int, valeur: str) -> str:
    return f"http://localhost:{port}/connexion#{valeur}"
