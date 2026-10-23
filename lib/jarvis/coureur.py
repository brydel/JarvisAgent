"""Exécutant de missions (« runner ») : réclame une tâche, l'exécute avec un adaptateur, rend le résultat.

L'exécutant ne décide de rien : il reçoit une enveloppe (une donnée qu'il valide), travaille sous bail, renouvelle
ce bail par battements, et s'arrête si le plan de contrôle dit que la tâche n'est plus la sienne.

Pas de travail terminé dupliqué au redémarrage : le résultat est écrit dans un journal local AVANT d'être envoyé.
Un exécutant qui redémarre renvoie d'abord ses résultats non acquittés ; si son bail est encore valide, le résultat
est accepté sans réexécution ; s'il a expiré, le plan de contrôle l'a déjà replanifiée (essai suivant) et
l'ancien résultat est refusé comme périmé.

Arrêt local : une pause Jarvis active (`jarvis pause poser humain`) ou le fichier `coureur/STOP` empêche toute
nouvelle réclamation. Le transport d'aujourd'hui est local (même processus que la base) ; M3 ajoutera un
transport HTTPS sortant avec la même interface (docs/jarvis-next/RUNNER_PROTOCOL.md).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from typing import Callable

from . import adaptateurs as ad, config, missions, pauses, protocole_executant as proto
from .annulation import ControleExecution, ExecutionAnnulee, controle, executer_processus, verifier

EXTENSIONS = {"image/png": ".png", "image/jpeg": ".jpg", "image/gif": ".gif", "image/webp": ".webp",
              "application/pdf": ".pdf"}

_LECTURE_PAGE = """import json, sys
sys.path.insert(0, sys.argv[1])
from jarvis import apercus
try:
    print(json.dumps({"page": apercus.texte_page(sys.argv[2])}, ensure_ascii=False))
except apercus.ApercuRefuse as exc:
    print(json.dumps({"note": f"Page non lisible : {exc}. Analyse seulement l'adresse et ce que l'utilisateur a écrit."}, ensure_ascii=False))
"""


def outils_prepares(pieces: dict) -> list[dict]:
    """Ce que l'exécutant a fait lui-même avant l'appel au modèle : affiché sur le Board, tel quel."""
    if not pieces:
        return []
    sortie = []
    if pieces.get("fichier"):
        sortie.append({"outil": "copie isolée", "detail": pieces["fichier"]})
    if pieces.get("page"):
        sortie.append({"outil": "lecture web", "detail": f"{len(pieces['page'])} caractères lus"})
    if pieces.get("transcription"):
        sortie.append({"outil": "transcription (noeud GPU)", "detail": pieces.get("transcription_detail", "")[:200]})
    if pieces.get("vision"):
        sortie.append({"outil": "lecture d'image (noeud GPU)", "detail": pieces.get("vision_detail", "")[:200]})
    elif pieces.get("vision_note"):
        sortie.append({"outil": "lecture d'image (noeud GPU)", "detail": pieces["vision_note"]})
    if pieces.get("note"):
        sortie.append({"outil": "pièce indisponible", "detail": pieces["note"][:200]})
    return sortie


def preparer_pieces(env: dict, dossier: Path) -> dict:
    """Pièces d'une contextualisation, préparées par l'exécutant LOCAL (même machine que le Board) : copie du
    fichier seul dans `dossier`, texte de la page d'un lien (règles anti-SSRF). Une pièce manquante devient
    une note ; une annulation remonte au coureur. La lecture web est isolée pour interrompre aussi DNS/TLS."""
    verifier(env)
    travail, pieces = env["travail"], {"dossier": str(dossier), "fichier": None, "image": False, "page": "", "note": ""}
    if travail.get("type") != "contextualiser":
        return {}
    try:
        if travail.get("asset_id"):
            from . import board
            chemin, a = board.fichier(env["tenant_id"], travail["asset_id"])
            ext = EXTENSIONS.get(a["mime"])
            if ext:
                shutil.copyfile(chemin, dossier / f"piece{ext}")
                pieces.update(fichier=f"piece{ext}", image=a["mime"].startswith("image/"))
                if pieces["image"]:
                    _lire_image(env, pieces, chemin)
            else:
                m = a.get("meta") or {}
                metadonnees = (f"Fichier {a['mime']} « {a['nom']} », {a['taille']} octets"
                               + (f", durée {m['duree']:.0f} s" if isinstance(m.get('duree'), (int, float)) else ""))
                pieces["note"] = metadonnees + " : contenu non transmis (seuls les métadonnées sont connues)."
                if a["mime"].startswith("audio/"):
                    _transcrire(env, pieces, chemin, metadonnees)
        elif travail.get("url"):
            try:
                r = executer_processus([sys.executable, "-c", _LECTURE_PAGE, str(Path(__file__).resolve().parents[1]),
                                        travail["url"]], timeout=min(env["delai_s"], 30), annulation=controle(env))
                texte = json.loads(r.stdout) if r.returncode == 0 else {}
                if not isinstance(texte, dict) or not all(isinstance(v, str) for v in texte.values()):
                    texte = {}
                pieces["page"] = texte.get("page", "")[:15_000]
                pieces["note"] = texte.get("note", "")[:500]
                if not pieces["page"] and not pieces["note"]:
                    pieces["note"] = "Page non lisible : la lecture isolée n'a pas fourni de texte."
            except (ValueError, subprocess.TimeoutExpired):
                pieces["note"] = "Page non lisible : délai dépassé ou réponse de lecture invalide."
    except (missions.MissionError, OSError) as exc:
        pieces["note"] = f"Pièce indisponible : {exc}"
    verifier(env)
    return pieces


def _lire_image(env: dict, pieces: dict, chemin: Path) -> None:
    """Image du Board : texte visible et description par le modèle local du noeud, en plus de l'image elle-même.
    Facultatif : une panne laisse le modèle principal lire l'image seul, sans note d'erreur bloquante."""
    from . import noeud
    r = noeud.reglages()
    if not noeud.active(r)[0]:
        return
    r["delai_s"] = max(30, min(int(r.get("delai_s") or 900), int(env["delai_s"]) // 3))
    try:
        v = noeud.decrire_image(chemin, cle_operation=f"noeud-image:{env['tache_id']}:{env['tentative_id']}",
                                verifier=lambda: verifier(env), r=r)
    except (noeud.NoeudError, OSError) as exc:
        pieces["vision_note"] = f"lecture locale de l'image impossible ({exc})"[:200]
        return
    if v["texte"]:
        pieces.update(vision=v["texte"], vision_detail=" · ".join(x for x in (
            v["modele"] and f"modèle {v['modele']}",
            v["duree_traitement_s"] is not None and f"lu en {v['duree_traitement_s']:.0f} s",
            f"{len(v['texte'])} caractères") if x))


def _transcrire(env: dict, pieces: dict, chemin: Path, metadonnees: str) -> None:
    """Audio du Board : texte par le noeud GPU s'il est branché (outil MCP sous le mandat du Board). Une panne
    garde les métadonnées et le dit au modèle ; elle n'échoue jamais la tâche. Une annulation remonte."""
    from . import noeud
    r = noeud.reglages()
    if not noeud.active(r)[0]:
        return
    # la moitié du délai de la tâche au plus : le modèle doit encore pouvoir contextualiser
    r["delai_s"] = max(30, min(int(r.get("delai_s") or 900), int(env["delai_s"]) // 2))
    try:
        t = noeud.transcrire(chemin, cle_operation=f"noeud:{env['tache_id']}:{env['tentative_id']}",
                             verifier=lambda: verifier(env), r=r)
    except (noeud.NoeudError, OSError) as exc:
        pieces["note"] = f"{metadonnees} : transcription impossible ({exc}). Seules les métadonnées sont connues."
        return
    if not t["texte"]:
        pieces["note"] = f"{metadonnees} : transcription vide (aucune parole reconnue)."
        return
    pieces.update(transcription=t["texte"], note="", transcription_detail=" · ".join(x for x in (
        t["modele"] and f"modèle {t['modele']}", t["langue"] and f"langue {t['langue']}",
        t["duree_audio_s"] is not None and f"{t['duree_audio_s']:.0f} s d'audio",
        t["duree_traitement_s"] is not None and f"traité en {t['duree_traitement_s']:.0f} s",
        f"{len(t['texte'])} caractères") if x))


class TransportLocal:
    """Appels directs au moteur de missions (même machine). Interface du futur transport réseau."""

    def __init__(self, executant_id: str, secret: str):
        self.id, self._secret = executant_id, secret

    def reclamer(self):
        return missions.reclamer(self.id, self._secret)

    def demarrer(self, env):
        missions.demarrer(self.id, self._secret, env["tache_id"], env["tentative_id"], env["bail_jeton"])

    def battement(self, env):
        return missions.battement(self.id, self._secret, env["tache_id"], env["tentative_id"], env["bail_jeton"])

    def rendre(self, resultat):
        return missions.rendre_resultat(self.id, self._secret, resultat)


def _dossier():
    d = config.STATE_DIR / "coureur"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _ecrire_atomique(chemin, data) -> None:
    tmp = chemin.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, chemin)


def identite() -> dict | None:
    """Identité de l'exécutant enrôlé sur ce poste (jarvis mission enroler), ou None."""
    try:
        return json.loads((_dossier() / "identite.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def prendre_verrou(executant_id: str):
    """Un seul processus par identité d'exécutant (démon OU `jarvis mission executer`) : verrou exclusif non
    bloquant, tenu tant que l'objet renvoyé reste ouvert. None si un autre processus le tient déjà."""
    import fcntl
    fh = open(_dossier() / f"{executant_id}.lock", "w")  # noqa: SIM115 — ouvert pour la durée du processus
    try:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        fh.close()
        return None
    return fh


def arret_local() -> str:
    if (_dossier() / "STOP").exists():
        return "fichier coureur/STOP présent"
    if pauses.active():
        return "pause Jarvis active"
    return ""


class Coureur:
    def __init__(self, transport, adaptateurs: dict[str, ad.Adaptateur], *,
                 avant_envoi: Callable[[dict], None] | None = None, intervalle_battement: float | None = None,
                 voie: int = 0, stop: threading.Event | None = None):
        self.transport, self.adaptateurs = transport, adaptateurs
        self.stop = stop
        self.avant_envoi = avant_envoi  # crochet de test : simuler un plantage entre exécution et envoi
        self.intervalle = min(intervalle_battement if intervalle_battement is not None else missions.BAIL_S / 3, 2.0)
        if self.intervalle <= 0:
            raise ValueError("intervalle de battement strictement positif attendu")
        # plusieurs voies d'une même identité (dans le même processus) : un journal chacune, jamais partagé
        self.journal = _dossier() / (f"{transport.id}.json" if voie == 0 else f"{transport.id}-v{voie}.json")

    def _arret_demande(self) -> str:
        if self.stop is not None and self.stop.is_set():
            return "arrêt du service exécutant demandé"
        return arret_local()

    # -- journal des résultats non acquittés --
    def _en_attente(self) -> list[dict]:
        try:
            return json.loads(self.journal.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []

    def _garder(self, resultat: dict) -> None:
        _ecrire_atomique(self.journal, [r for r in self._en_attente()
                                        if r["cle_idempotence"] != resultat["cle_idempotence"]] + [resultat])

    def _oublier(self, cle: str) -> None:
        _ecrire_atomique(self.journal, [r for r in self._en_attente() if r["cle_idempotence"] != cle])

    def vider_en_attente(self) -> list[dict]:
        """Renvoie les résultats déjà calculés mais non acquittés (redémarrage)."""
        sorties = []
        for r in self._en_attente():
            try:
                sorties.append(self.transport.rendre(r))
                self._oublier(r["cle_idempotence"])
            except missions.MissionError as exc:
                if exc.code in ("perime", "inconnue"):
                    self._oublier(r["cle_idempotence"])
                    sorties.append({"acquitte": False, "raison": str(exc)})
                else:
                    raise
        return sorties

    # -- un tour --
    def tour(self) -> dict:
        arret = self._arret_demande()
        if arret:
            return {"etat": "arret", "raison": arret}
        repris = self.vider_en_attente()
        arret = self._arret_demande()
        if arret:
            return {"etat": "arret", "raison": arret, "repris": repris}
        env = self.transport.reclamer()
        if env is None:
            return {"etat": "vide", "repris": repris}
        try:
            env = proto.valider_tache(env)
        except proto.EnveloppeInvalide as exc:
            # rien n'est exécuté ; le bail expirera et le plan de contrôle comptera l'essai
            return {"etat": "invalide", "raison": str(exc)}
        adaptateur = self.adaptateurs.get(env["fournisseur"])
        try:
            jeton = ControleExecution(expire=env["bail_expire"], interruption=self._arret_demande)
        except ValueError as exc:
            return {"etat": "invalide", "raison": str(exc)}
        enveloppe = env
        env = {**env, "_annulation": jeton}  # état local : jamais reçu d'un document ni transmis au modèle
        try:
            self.transport.demarrer(enveloppe)
        except missions.MissionError as exc:
            if exc.code in ("perime", "inconnue"):
                return {"etat": "perime", "tache_id": env["tache_id"], "raison": str(exc), "bail_perdu": True}
            raise
        fin = threading.Event()
        premier = threading.Event()

        def battre():
            while not fin.is_set():
                try:
                    jeton.verifier()
                    reponse = self.transport.battement(enveloppe)
                    if reponse.get("continuer") is not True:
                        jeton.annuler(reponse.get("raison") or "bail perdu ou tâche annulée")
                        return
                    if "bail_expire" in reponse:
                        jeton.renouveler(reponse["bail_expire"])
                except ExecutionAnnulee:
                    return
                except Exception as exc:  # noqa: BLE001 — fail closed, même si le transport échoue hors protocole
                    jeton.annuler(f"battement indisponible ({type(exc).__name__})")
                    return
                finally:
                    premier.set()
                if fin.wait(self.intervalle):
                    return

        fil = threading.Thread(target=battre, daemon=True)
        fil.start()
        sortie = None
        try:
            # Aucun appel d'outil avant la première confirmation d'autorité. Un transport bloqué ne peut
            # empêcher l'expiration locale du bail : cette attente vérifie le jeton toutes les 100 ms.
            while not premier.wait(0.1):
                jeton.verifier()
            jeton.verifier()
            if adaptateur is None:
                sortie = {"issue": "fournisseur_indisponible", "contenu": "",
                          "erreur": f"adaptateur « {env['fournisseur']} » absent de cet exécutant", "factice": False}
            else:
                try:
                    with tempfile.TemporaryDirectory(prefix="jarvis-pieces-") as d:
                        pieces = preparer_pieces(env, Path(d))
                        jeton.verifier()
                        sortie = adaptateur.executer({**env, "pieces": pieces} if pieces else env)
                        jeton.verifier()
                        sortie["outils"] = outils_prepares(pieces) + list(sortie.get("outils") or [])
                except ValueError as exc:
                    sortie = {"issue": "echec", "contenu": "", "erreur": str(exc), "factice": False}
        except ExecutionAnnulee:
            sortie = None
        finally:
            fin.set()
            fil.join(timeout=0.2)
        if sortie is None or jeton.raison:
            # Aucun résultat tardif n'entre dans le journal de réémission ou dans le plan de contrôle.
            return {"etat": "perime", "tache_id": env["tache_id"], "raison": jeton.raison,
                    "bail_perdu": True, "execution_arretee": True}
        resultat = proto.resultat(env, sortie["issue"], contenu=sortie.get("contenu", ""),
                                  erreur=sortie.get("erreur", ""), fournisseur=env["fournisseur"],
                                  factice=bool(sortie.get("factice")), outils=sortie.get("outils"))
        try:
            proto.valider_resultat(resultat)
        except proto.EnveloppeInvalide as exc:  # réponse vide, trop longue… : un échec, pas un résultat
            resultat.update(issue="echec", contenu="", erreur=str(exc))
        self._garder(resultat)  # écrit AVANT l'envoi : un plantage ici ne perd pas le travail
        if self.avant_envoi:
            self.avant_envoi(resultat)
        try:
            accuse = self.transport.rendre(resultat)
        except missions.MissionError as exc:
            if exc.code in ("perime", "inconnue"):
                self._oublier(resultat["cle_idempotence"])
                return {"etat": "perime", "tache_id": env["tache_id"], "raison": str(exc), "bail_perdu": True}
            raise
        self._oublier(resultat["cle_idempotence"])
        return {"etat": "fait", "tache_id": env["tache_id"], "accuse": accuse}
