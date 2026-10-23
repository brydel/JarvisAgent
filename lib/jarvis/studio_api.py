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
from urllib.parse import parse_qs, unquote, urlsplit

from . import apercus, board, config, missions, studio_product
from .annulation import ExecutionAnnulee
from .oauth import CoffreError

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
# Board V2 : scripts toujours limités à ce serveur ; styles en ligne autorisés (React Flow positionne les nœuds par
# attributs style) ; médias et images du serveur ou de blobs locaux (aperçus avant envoi) ; worker pdf.js local.
CSP_V2 = ("default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; font-src 'self'; "
          "img-src 'self' data: blob:; media-src 'self' blob:; connect-src 'self'; worker-src 'self' blob:; "
          "base-uri 'none'; form-action 'self'; frame-ancestors 'none'")
DOSSIER_V2 = Path(__file__).resolve().parent / "studio_v2"
TYPES_V2 = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".mjs": "text/javascript; charset=utf-8",
            ".css": "text/css; charset=utf-8", ".woff2": "font/woff2", ".png": "image/png", ".jpg": "image/jpeg",
            ".svg": "image/svg+xml", ".json": "application/json", ".mp3": "audio/mpeg", ".mp4": "video/mp4",
            ".webp": "image/webp", ".wav": "audio/wav", ".pdf": "application/pdf"}
MO_FLUX = 256 * 1024

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

    def setup(self):
        super().setup()
        self.connection.settimeout(15)  # Une connexion HTTP inactive ne retient pas la fermeture du Studio.

    # --- réponses ---
    def _envoyer(self, code: int, corps: bytes, ctype: str = "application/json; charset=utf-8",
                 entetes: dict | None = None, *, csp: str = CSP, cache: str = "no-store") -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(corps)))
        self.send_header("Cache-Control", cache)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", csp)
        for k, v in (entetes or {}).items():
            self.send_header(k, v)
        try:
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(corps)
        except (BrokenPipeError, ConnectionResetError):
            # le navigateur a abandonné la requête (onglet fermé, vue changée, rechargement) : rien à signaler,
            # et surtout pas une « erreur 503 » réécrite sur la même connexion fermée
            self.close_connection = True

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
        if route == "/api/v2/oauth/callback":
            # Retour Google : SameSite=Strict peut exclure le cookie. L'état secret à usage unique
            # lie le retour au flux déjà ouvert par le propriétaire, jamais à une config de cette URL.
            from . import oauth
            from .annulation import ControleExecution, ExecutionAnnulee
            try:
                requis = {"state", "code"}
                if not requis <= set(q) <= requis | {"scope", "authuser", "prompt", "hd", "iss"} or any(len(v) != 1 for v in q.values()):
                    raise ValueError
                controle = ControleExecution(interruption=lambda: "arrêt du Studio" if self.server.arret.is_set() else "")
                oauth.callback(q["state"][0], q["code"][0], annulation=controle)
                message = "Autorisation Gmail enregistrée. Tu peux fermer cette page et revenir au Studio."
                code = 200
            except CoffreError:
                message = "Connexion indisponible. Reviens au Studio après restauration du coffre local."
                code = 503
            except (OSError, ValueError, ExecutionAnnulee):
                message = "Autorisation non enregistrée. Reviens au Studio pour démarrer une nouvelle connexion."
                code = 400
            self._envoyer(code, ("<!doctype html><html lang='fr'><meta charset='utf-8'><title>Connexion Gmail</title>"
                                "<h1>Connexion Gmail</h1><p>" + message + "</p></html>").encode(), "text/html; charset=utf-8")
            return
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
        if route == "/v2" or route.startswith("/v2/"):
            self._page_v2(route)
            return
        if not route.startswith("/api/"):
            self._erreur(404, "Page inconnue.")
            return
        if not self._authentifie():
            self._erreur(401, "Session absente ou expirée : rouvre le lien donné par « jarvis mission studio ».")
            return
        org = missions.tenant_local()
        try:
            from . import os_api
            resultat_os = os_api.lire(route, q, org)
            if resultat_os is not None:
                self._json(*resultat_os)
                return
            if route == "/api/v2/atelier":
                self._json(200, studio_product.catalogue(org))
            elif m := re.fullmatch(r"/api/v2/atelier/candidats/(RB-[0-9]{4,})", route):
                self._json(200, studio_product.comparer(org, m.group(1)))
            elif route == "/api/board":
                self._json(200, {"objets": missions.board(org, (q.get("espace") or ["accueil"])[0][:80])})
            elif route == "/api/missions":
                self._json(200, {"missions": missions.missions(org, 50)})
            elif m := re.match(r"^/api/missions/(MI-[0-9a-f]{12})(/inspection)?$", route):
                self._json(200, (missions.inspecter if m.group(2) else missions.mission)(org, m.group(1)))
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
            elif route == "/api/v2/board":
                self._json(200, {**board.objets(org, board.nom_espace((q.get("espace") or ["accueil"])[0])),
                                 "reglages": missions.reglages_board(org)})
            elif route == "/api/v2/espaces":
                self._json(200, {"espaces": board.espaces(org)})
            elif route == "/api/v2/activite":
                from . import activite
                self._json(200, activite.instantane(org, (q.get("espace") or ["accueil"])[0]))
            elif route == "/api/v2/os/schemas":
                from . import contrats
                self._json(200, contrats.schemas())
            elif route == "/api/v2/os/capacites":
                from . import capacites
                self._json(200, capacites.collecter())
            elif route == "/api/v2/os/mandats":
                from . import mandats
                try:
                    self._json(200, {"mandats": mandats.lister()})
                except mandats.MandatError:
                    self._erreur(503, "Registre de mandats indisponible ; aucune autorisation déduite.")
            elif m := re.fullmatch(r"/api/v2/activite/([0-9a-f]{24})/apercu", route):
                from . import activite
                self._json(200, {"texte": activite.apercu(org, m.group(1), (q.get("espace") or ["accueil"])[0])})
            elif m := re.match(r"^/api/v2/fichiers/(AS-[0-9a-f]{12})$", route):
                self._fichier(*board.fichier(org, m.group(1)))
            elif m := re.match(r"^/api/v2/objets/(BO-[0-9a-f]{12})/commentaires$", route):
                self._json(200, {"commentaires": board.commentaires(org, m.group(1))})
            else:
                self._erreur(404, "Route inconnue.")
        except CoffreError:
            self._erreur(503, "Coffre OAuth indisponible ; aucune connexion déduite.")
        except ValueError:
            self._erreur(400, "paramètre invalide")
        except OSError:
            self._erreur(503, "État local indisponible ; aucune connexion ni autorisation déduite.")
        except missions.MissionError as exc:
            self._erreur(404 if exc.code == "inconnue" else 403 if exc.code == "interdit" else 400, str(exc))

    def _page_v2(self, route: str) -> None:
        """Board V2 : application construite (studio/board-v2 → lib/jarvis/studio_v2). Noms de fichiers filtrés."""
        nom = route[len("/v2/"):] if route.startswith("/v2/") else ""
        if nom in ("", "index.html", "connexion"):
            nom = "index.html"
        if not re.fullmatch(r"(assets/|demo/)?[A-Za-z0-9._-]+", nom) or ".." in nom:
            self._erreur(404, "Page inconnue.")
            return
        chemin = DOSSIER_V2 / nom
        if not chemin.is_file():
            self._erreur(404, "Board V2 non construit : cd studio/board-v2 && npm install && npm run build"
                         if nom == "index.html" else "Ressource inconnue.")
            return
        ctype = TYPES_V2.get(chemin.suffix, "application/octet-stream")
        cache = "no-store" if nom == "index.html" else "public, max-age=31536000, immutable"  # noms avec empreinte
        self._envoyer(200, chemin.read_bytes(), ctype, csp=CSP_V2, cache=cache)

    def _fichier(self, chemin: Path, info: dict) -> None:
        """Sert un fichier du Board, par plages (avance dans l'audio et la vidéo). Jamais interprété par la page :
        type MIME issu de la reconnaissance des octets, nosniff, CSP « sandbox »."""
        taille = chemin.stat().st_size
        debut, fin, partiel = 0, taille - 1, False
        plage = re.fullmatch(r"bytes=(\d*)-(\d*)", self.headers.get("Range", "").strip())
        if plage and (plage.group(1) or plage.group(2)):
            if plage.group(1):
                debut = int(plage.group(1))
                fin = min(int(plage.group(2)), taille - 1) if plage.group(2) else taille - 1
            else:
                debut, fin = max(0, taille - int(plage.group(2))), taille - 1
            if debut > fin or debut >= taille:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{taille}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            partiel = True
        self.send_response(206 if partiel else 200)
        self.send_header("Content-Type", info["mime"])
        self.send_header("Content-Length", str(fin - debut + 1))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Cache-Control", "private, max-age=86400")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "sandbox; default-src 'none'")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        if partiel:
            self.send_header("Content-Range", f"bytes {debut}-{fin}/{taille}")
        self.end_headers()
        if self.command == "HEAD":
            return
        try:
            with chemin.open("rb") as fh:
                fh.seek(debut)
                reste = fin - debut + 1
                while reste > 0:
                    bloc = fh.read(min(256 * 1024, reste))
                    if not bloc:
                        break
                    self.wfile.write(bloc)
                    reste -= len(bloc)
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass

    def _televerser(self, org: str) -> None:
        """Corps brut écrit en flux dans un fichier temporaire, puis reconnu, borné et rangé par board.py."""
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = 0
        if n <= 0 or n > max(board.LIMITES.values()):
            self._erreur(413 if n > 0 else 400, "taille de fichier absente ou trop grande")
            return
        tmp = board.fichier_temporaire()
        try:
            with tmp.open("wb") as fh:
                reste = n
                while reste > 0:
                    bloc = self.rfile.read(min(MO_FLUX, reste))
                    if not bloc:
                        raise ValueError("téléversement interrompu")
                    fh.write(bloc)
                    reste -= len(bloc)
            nom = unquote(self.headers.get("X-Nom-Fichier", ""))[:200]
            self._json(201, board.enregistrer_fichier(org, tmp, nom, auteur="studio"))
        except ValueError as exc:
            self._erreur(400, str(exc))
        except missions.MissionError as exc:
            self._erreur(415 if exc.code == "fichier" else 400, str(exc))
        finally:
            tmp.unlink(missing_ok=True)

    def _apercu(self, org: str, url: str) -> None:
        def ranger(octets: bytes, nom: str):
            chemin = apercus.ecrire_temp(octets, board.config.STATE_DIR / "board_assets" / "televersements")
            try:
                return board.enregistrer_fichier(org, chemin, nom, auteur="apercu")
            except missions.MissionError:
                return None
            finally:
                chemin.unlink(missing_ok=True)
        try:
            self._json(200, apercus.apercu(url, enregistrer_image=ranger,
                                           autoriser_prives=getattr(self.server, "apercus_prives", False)))
        except apercus.ApercuRefuse as exc:
            self._json(422, {"erreur": str(exc), "url": url})

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
        if route == "/api/v2/fichiers":  # corps binaire, pas du JSON
            if not self._authentifie():
                self._erreur(401, "Session absente ou expirée.")
                return
            self._televerser(missions.tenant_local())
            return
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
            elif route.startswith("/api/v2/"):
                self._post_v2(org, route, corps)
            else:
                self._erreur(404, "Route inconnue.")
        except CoffreError:
            self._erreur(503, "Coffre OAuth indisponible ; aucun échange autorisé.")
        except (TypeError, ValueError):
            self._erreur(400, "valeur invalide")
        except ExecutionAnnulee:
            self._erreur(503, "Studio en cours d'arrêt ; aucun nouveau départ autorisé.")
        except OSError:
            self._erreur(503, "État local indisponible ; aucune écriture externe confirmée.")
        except missions.MissionError as exc:
            conflits = ("approbation", "transition", "conflit", "verrouille", "concurrence")
            self._erreur(404 if exc.code == "inconnue" else 403 if exc.code == "interdit" else 409 if exc.code in conflits else 400, str(exc))

    def _post_v2(self, org: str, route: str, corps: dict) -> None:
        from . import os_api
        resultat_os = os_api.ecrire(route, corps, org, stop=self.server.arret)
        if resultat_os is not None:
            self._json(*resultat_os)
            return
        espace = board.nom_espace(corps.get("espace"))
        if m := re.fullmatch(r"/api/v2/atelier/agents/([a-z0-9_-]{1,64})/(verifier|proposer)", route):
            action = studio_product.verifier if m.group(2) == "verifier" else studio_product.proposer
            self._json(200 if m.group(2) == "verifier" else 201, action(org, m.group(1), corps))
        elif m := re.fullmatch(r"/api/v2/atelier/candidats/(RB-[0-9]{4,})/decider", route):
            self._json(200, studio_product.decider(org, m.group(1), corps))
        elif route == "/api/v2/objets":
            type_ = str(corps.get("type") or "note")
            o = missions.board_ajouter(
                org, espace, type_, str(corps.get("contenu") or ""), auteur="studio",
                x=float(corps.get("x") or 0), y=float(corps.get("y") or 0), largeur=float(corps.get("largeur") or 0),
                hauteur=float(corps.get("hauteur") or 0), priorite=str(corps.get("priorite") or ""),
                meta=corps.get("meta") if isinstance(corps.get("meta"), dict) else {},
                asset_id=corps.get("asset_id") or None, mission_id=corps.get("mission_id") or None,
                # Board V2 : tout élément est contextualisé par le chef ; « analyser: false » (duplication, note vide) l'évite
                analyser=False, contextualiser=corps.get("analyser") is not False)
            self._json(201, o)
        elif route == "/api/v2/objets/lot":
            mods = corps.get("modifications")
            if not isinstance(mods, list):
                self._erreur(400, "« modifications » : liste attendue")
                return
            self._json(200, {"resultats": board.mettre_a_jour_lot(org, mods, par="studio")})
        elif route == "/api/v2/objets/supprimer":
            ids = [str(i) for i in corps.get("ids") or [] if isinstance(i, str)]
            self._json(200, {"n": board.supprimer(org, ids, par="studio", restaurer=bool(corps.get("restaurer")))})
        elif m := re.match(r"^/api/v2/objets/(BO-[0-9a-f]{12})$", route):
            champs = corps.get("champs")
            if not isinstance(champs, dict):
                self._erreur(400, "« champs » : objet attendu")
                return
            self._json(200, board.mettre_a_jour(org, m.group(1), champs, version=corps.get("version"), par="studio"))
        elif route == "/api/v2/reglages":
            valeurs = {k: corps[k] for k in ("auto_analyse", "actions_auto") if isinstance(corps.get(k), bool)}
            if not valeurs:
                self._erreur(400, "« auto_analyse » ou « actions_auto » : booléen attendu")
                return
            self._json(200, missions.regler_board(org, **valeurs, par="studio:humain"))
        elif m := re.match(r"^/api/v2/objets/(BO-[0-9a-f]{12})/contextualiser$", route):
            self._json(201, {"mission_id": missions.lancer_contextualisation(org, m.group(1), auteur="studio:humain",
                                                                             relance=True)})
        elif m := re.match(r"^/api/v2/objets/(BO-[0-9a-f]{12})/propositions$", route):
            index = corps.get("index")
            if not isinstance(index, int) or isinstance(index, bool):
                self._erreur(400, "« index » : entier attendu")
                return
            self._json(200, missions.decider_proposition(org, m.group(1), index, str(corps.get("decision") or ""),
                                                         par="studio:humain"))
        elif m := re.match(r"^/api/v2/objets/(BO-[0-9a-f]{12})/commentaires$", route):
            self._json(201, {"id": board.commenter(org, m.group(1), str(corps.get("texte") or ""), auteur="studio:humain")})
        elif route == "/api/v2/liens":
            self._json(201, {"id": board.lier(org, espace, str(corps.get("source_id")), str(corps.get("cible_id")),
                                              libelle=str(corps.get("libelle") or ""),
                                              style=str(corps.get("style") or "defaut"), par="studio")})
        elif m := re.match(r"^/api/v2/liens/(BL-[0-9a-f]{12})$", route):
            board.modifier_lien(org, m.group(1), libelle=corps.get("libelle"), style=corps.get("style"),
                                supprime=corps.get("supprime") if isinstance(corps.get("supprime"), bool) else None,
                                par="studio")
            self._json(200, {"ok": True})
        elif route == "/api/v2/apercu":
            self._apercu(org, str(corps.get("url") or ""))
        elif route == "/api/v2/missions":
            objectif = str(corps.get("objectif") or "").strip()
            contexte = str(corps.get("contexte") or "").strip()
            fournisseur = str(corps.get("fournisseur") or "auto")
            priorite = str(corps.get("priorite") or "P1")
            if not objectif:
                self._erreur(400, "objectif vide")
                return
            if len(objectif) > 500 or len(contexte) > 20_000:
                self._erreur(400, "objectif (500 caractères) ou contexte (20 000 caractères) trop long")
                return
            if fournisseur not in ("auto", "claude", "codex") or priorite not in ("P1", "P2", "P3"):
                self._erreur(400, "fournisseur ou priorité invalide")
                return
            # mission de cadrage L1 (analyse sans outils) : la politique s'applique côté moteur, rien d'externe ;
            # le contexte est une DONNÉE analysée, jamais une consigne
            document = f"Objectif : {objectif}\n\n{contexte}" if contexte else objectif
            mi = missions.creer_mission(org, objectif, [{"type": "analyse_document", "niveau": "L1", "capacites": ["analyse"],
                                                         "fournisseur": fournisseur, "travail": {"document": document}}],
                                        source="studio", demandeur="studio:humain")
            o = missions.board_ajouter(org, espace, "mission", "", auteur="studio", x=float(corps.get("x") or 0),
                                       y=float(corps.get("y") or 0), largeur=452, hauteur=362, priorite=priorite,
                                       mission_id=mi["mission_id"], analyser=False,
                                       meta={"description": contexte[:400]} if contexte else None)
            self._json(201, {"mission_id": mi["mission_id"], "taches": mi.get("taches", []), "objet_id": o["objet_id"]})
        else:
            self._erreur(404, "Route inconnue.")

    def do_HEAD(self):  # noqa: N802
        if urlsplit(self.path).path in STATIQUES:
            self.do_GET()
        else:
            self._erreur(405, "HEAD seulement sur les pages.")

    def log_message(self, *args):
        pass  # aucune URL journalisée : rien ne doit y traîner


class ServeurStudio(ThreadingHTTPServer):
    daemon_threads = False

    def server_close(self):
        if hasattr(self, "arret"):
            self.arret.set()
            from . import pilotage
            pilotage.arreter()
        super().server_close()


def serveur(port: int = PORT_DEFAUT) -> ThreadingHTTPServer:
    ThreadingHTTPServer.allow_reuse_address = True
    ThreadingHTTPServer.daemon_threads = True
    httpd = ServeurStudio(("127.0.0.1", port), Handler)
    httpd.arret = threading.Event()
    httpd.intervalle_flux = 0.5
    return httpd


def lien(port: int, valeur: str) -> str:
    return f"http://localhost:{port}/connexion#{valeur}"
