"""Service GPU résident du noeud Jetson : garde les modèles chargés et traite une file de travaux.

Il n'écoute que sur 127.0.0.1 : on ne l'atteint que par `jarvis_noeud.py`, lancé via la commande SSH forcée
de la clé de Jarvis. Il ne décide de rien et ne garde aucun état métier : un travail porte sur un fichier déjà
déposé dans la file d'entrée (désigné par son empreinte SHA-256), son résultat reste en mémoire une heure.
Bibliothèque standard pour le serveur ; le moteur (openai-whisper sur CUDA) n'est importé qu'au lancement réel.
"""
from __future__ import annotations

import hmac
import json
import os
import re
import shutil
import subprocess
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

PROTOCOLE = 1
TEXTE_MAX = 200_000
LANGUES = ("auto", "fr", "en", "es", "de", "it", "pt", "nl", "ar")
SHA = re.compile(r"[0-9a-f]{64}\Z")
TRAVAIL = re.compile(r"TR-[0-9a-f]{24}\Z")
CORPS_MAX = 4096
RESULTATS_MAX = 64
CONSERVATION_S = 3600


@dataclass(frozen=True)
class Reglages:
    jeton: str = ""
    modele: str = "small"
    port: int = 7741
    entree: str = ""
    duree_max_s: int = 1800

    def valider(self) -> None:
        if len(self.jeton) < 32:
            raise ValueError("Jeton privé de 32 caractères au moins requis (JARVIS_NOEUD_TOKEN).")
        if not re.fullmatch(r"[a-z0-9.-]{1,40}", self.modele):
            raise ValueError("Nom de modèle invalide.")
        if not 0 <= self.port <= 65535 or not 10 <= self.duree_max_s <= 7200:
            raise ValueError("Port ou durée hors bornes.")
        if not self.entree or not Path(self.entree).is_absolute():
            raise ValueError("Dossier d'entrée absolu requis (JARVIS_NOEUD_ENTREE).")

    @classmethod
    def environnement(cls) -> "Reglages":
        env = os.environ.get
        r = cls(jeton=env("JARVIS_NOEUD_TOKEN", ""), modele=env("JARVIS_NOEUD_MODELE", "small"),
                port=int(env("JARVIS_NOEUD_PORT", "7741")),
                entree=env("JARVIS_NOEUD_ENTREE", str(Path.home() / ".cache/jarvis-noeud/entree")),
                duree_max_s=int(env("JARVIS_NOEUD_MAX_S", "1800")))
        r.valider()
        return r


def duree_audio(chemin: Path) -> float | None:
    """Durée par ffprobe (fichier non fiable : aucune option du fichier n'est suivie), None si inconnue."""
    if not shutil.which("ffprobe"):
        return None
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(chemin)],
                           capture_output=True, text=True, timeout=20)
        return float(json.loads(r.stdout or "{}").get("format", {}).get("duration"))
    except (OSError, subprocess.SubprocessError, ValueError, TypeError):
        return None


def mesures() -> dict:
    """Mémoire et températures du noeud (lecture seule de /proc et /sys), pour la supervision."""
    sortie: dict = {}
    try:
        info = dict(l.split(":", 1) for l in Path("/proc/meminfo").read_text().splitlines() if ":" in l)
        sortie["memoire_totale_mo"] = int(info["MemTotal"].split()[0]) // 1024
        sortie["memoire_dispo_mo"] = int(info["MemAvailable"].split()[0]) // 1024
    except (OSError, KeyError, ValueError):
        pass
    for zone in sorted(Path("/sys/class/thermal").glob("thermal_zone*")):
        try:
            nom = (zone / "type").read_text().strip()
            if nom in ("gpu-thermal", "cpu-thermal", "tj-thermal"):
                sortie[nom.replace("-thermal", "") + "_c"] = int((zone / "temp").read_text()) // 1000
        except (OSError, ValueError):
            pass
    return sortie


class MoteurWhisper:
    """openai-whisper sur CUDA ; chargé une fois (8 Go partagés CPU/GPU : un seul modèle à la fois)."""

    def __init__(self, modele: str):
        import torch
        import whisper
        self.nom = modele
        self.peripherique = "cuda" if torch.cuda.is_available() else "cpu"
        self._modele = whisper.load_model(modele, device=self.peripherique)

    def transcrire(self, chemin: Path, langue: str) -> dict:
        r = self._modele.transcribe(str(chemin), language=None if langue == "auto" else langue,
                                    fp16=self.peripherique == "cuda", condition_on_previous_text=False)
        return {"texte": str(r.get("text") or "").strip(), "langue": str(r.get("language") or langue),
                "segments": len(r.get("segments") or [])}


class File:
    """Travaux traités un par un par un fil unique. L'identifiant dépend du fichier, de la langue et du modèle :
    une seconde demande identique retrouve le même travail au lieu de relancer le GPU."""

    def __init__(self, reglages: Reglages, moteur):
        self.r, self.moteur = reglages, moteur
        self.travaux: OrderedDict[str, dict] = OrderedDict()
        self.verrou = threading.Condition()
        self.attente: list[str] = []
        threading.Thread(target=self._boucle, daemon=True).start()

    def _purger(self, maintenant: float) -> None:
        for ident in [i for i, t in self.travaux.items()
                      if t["statut"] in ("termine", "echec") and maintenant - t["fin"] > CONSERVATION_S]:
            del self.travaux[ident]
        while len(self.travaux) > RESULTATS_MAX:
            ident = next((i for i, t in self.travaux.items() if t["statut"] in ("termine", "echec")), None)
            if ident is None:
                break
            del self.travaux[ident]

    def soumettre(self, sha: str, langue: str) -> dict:
        ident = "TR-" + hmac.new(b"jarvis-noeud", f"{sha}:{langue}:{self.moteur.nom}".encode(), "sha256").hexdigest()[:24]
        with self.verrou:
            self._purger(time.time())
            t = self.travaux.get(ident)
            if t is None or t["statut"] == "echec":
                if not (Path(self.r.entree) / sha).is_file():
                    raise LookupError("Fichier absent de la file d'entrée : dépose-le d'abord.")
                if len(self.attente) >= 8:
                    raise OverflowError("File de travaux pleine.")
                t = {"id": ident, "sha": sha, "langue": langue, "statut": "en_attente", "fin": 0.0}
                self.travaux[ident] = t
                self.attente.append(ident)
                self.verrou.notify_all()
            return _public(t)

    def lire(self, ident: str, attente_s: float) -> dict:
        echeance = time.monotonic() + attente_s
        with self.verrou:
            while True:
                t = self.travaux.get(ident)
                if t is None:
                    raise LookupError("Travail inconnu ou expiré.")
                reste = echeance - time.monotonic()
                if t["statut"] in ("termine", "echec") or reste <= 0:
                    return _public(t)
                self.verrou.wait(reste)

    def occupe(self) -> bool:
        with self.verrou:
            return any(t["statut"] in ("en_attente", "en_cours") for t in self.travaux.values())

    def _boucle(self) -> None:
        while True:
            with self.verrou:
                while not self.attente:
                    self.verrou.wait()
                t = self.travaux.get(self.attente.pop(0))
                if t is None:
                    continue
                t["statut"] = "en_cours"
            chemin = Path(self.r.entree) / t["sha"]
            try:
                duree = duree_audio(chemin)
                if duree is not None and duree > self.r.duree_max_s:
                    raise ValueError(f"audio trop long ({duree:.0f} s, {self.r.duree_max_s} s au plus)")
                debut = time.monotonic()
                r = self.moteur.transcrire(chemin, t["langue"])
                maj = {"statut": "termine", "resultat": {
                    "texte": str(r.get("texte") or "").strip()[:TEXTE_MAX], "langue": str(r.get("langue") or "")[:8],
                    "segments": int(r.get("segments") or 0), "duree_audio_s": duree,
                    "duree_traitement_s": round(time.monotonic() - debut, 2), "modele": self.moteur.nom}}
            except ValueError as exc:
                maj = {"statut": "echec", "erreur": str(exc)[:200]}
            except Exception:  # noqa: BLE001 — un fichier illisible ne doit pas arrêter la file
                maj = {"statut": "echec", "erreur": "audio illisible ou transcription impossible"}
            finally:
                try:
                    chemin.unlink()  # aucun fichier conservé après traitement
                except OSError:
                    pass
            with self.verrou:
                t.update(maj, fin=time.time())
                self.verrou.notify_all()


def _public(t: dict) -> dict:
    return {k: t[k] for k in ("id", "statut", "resultat", "erreur") if k in t}


def serveur(reglages: Reglages, moteur) -> ThreadingHTTPServer:
    """`moteur` : objet avec .nom et .transcrire(chemin, langue) -> {texte, langue, segments}."""
    reglages.valider()
    Path(reglages.entree).mkdir(parents=True, exist_ok=True, mode=0o700)
    file = File(reglages, moteur)

    class Gestionnaire(BaseHTTPRequestHandler):
        server_version = "JarvisNoeud/1"
        protocol_version = "HTTP/1.0"

        def setup(self):
            super().setup()
            self.connection.settimeout(30)

        def log_message(self, *args):
            pass  # ni contenus ni jetons dans les journaux

        def repondre(self, code: int, data: dict):
            corps = json.dumps(data, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(corps)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            try:
                self.wfile.write(corps)
            except OSError:
                pass

        def autorise(self) -> bool:
            attendu = "Bearer " + reglages.jeton
            return (self.client_address[0] == "127.0.0.1" and not self.headers.get("Origin")
                    and hmac.compare_digest(self.headers.get("Authorization", "").encode(), attendu.encode()))

        def do_GET(self):  # noqa: N802
            if not self.autorise():
                return self.repondre(401, {"erreur": "Accès refusé."})
            url = urlsplit(self.path)
            if url.path == "/health":
                return self.repondre(200, {"protocole": PROTOCOLE, "modele": moteur.nom, "occupe": file.occupe(),
                                           "duree_max_s": reglages.duree_max_s, "mesures": mesures()})
            ident = url.path.removeprefix("/v1/travaux/")
            if ident == url.path or not TRAVAIL.fullmatch(ident):
                return self.repondre(404, {"erreur": "Route inconnue."})
            try:
                attente = min(max(float((parse_qs(url.query).get("attente") or ["0"])[0]), 0.0), 15.0)
            except ValueError:
                return self.repondre(400, {"erreur": "attente invalide."})
            try:
                self.repondre(200, file.lire(ident, attente))
            except LookupError as exc:
                self.repondre(404, {"erreur": str(exc)})

        def do_POST(self):  # noqa: N802
            if not self.autorise():
                return self.repondre(401, {"erreur": "Accès refusé."})
            if urlsplit(self.path).path != "/v1/travaux":
                return self.repondre(404, {"erreur": "Route inconnue."})
            try:
                longueur = int(self.headers.get("Content-Length", "0"))
                if not 1 <= longueur <= CORPS_MAX:
                    raise ValueError
                data = json.loads(self.rfile.read(longueur))
                if not isinstance(data, dict) or set(data) - {"fichier", "langue"}:
                    raise ValueError
                sha, langue = data.get("fichier"), data.get("langue", "fr")
                if not isinstance(sha, str) or not SHA.fullmatch(sha) or langue not in LANGUES:
                    raise ValueError
            except (ValueError, TypeError):
                return self.repondre(400, {"erreur": "Demande invalide : fichier (SHA-256) et langue."})
            try:
                self.repondre(202, file.soumettre(sha, langue))
            except LookupError as exc:
                self.repondre(404, {"erreur": str(exc)})
            except OverflowError as exc:
                self.repondre(429, {"erreur": str(exc)})

    httpd = ThreadingHTTPServer(("127.0.0.1", reglages.port), Gestionnaire)
    httpd.daemon_threads = True
    return httpd


if __name__ == "__main__":
    r = Reglages.environnement()
    print(f"Chargement du modèle « {r.modele} »…", flush=True)
    srv = serveur(r, MoteurWhisper(r.modele))
    print(f"Noeud GPU prêt sur 127.0.0.1:{r.port}.", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
