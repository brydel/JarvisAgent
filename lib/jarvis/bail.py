"""Bail d'orchestrateur : un seul démon Jarvis actif à la fois.

Le démon prend le bail au démarrage et le renouvelle à chaque tour de surveillance. Un second démon est refusé
tant que le bail est valide. Le bail se reprend s'il a expiré (démon arrêté net, PC en veille trop longtemps)
ou si le processus titulaire, sur la même machine, n'existe plus. Chaque nouvelle prise incrémente un numéro
(« jeton de clôture ») : un ancien titulaire qui se réveille ne peut plus renouveler, il s'arrête.

Portée honnête : l'état vit sous ~/.local/state/jarvis (fichier ou SQLite local). Il protège contre deux démons
sur le même poste. Pour plusieurs machines, le bail devra vivre dans une base partagée (serveur) : conçu.
"""

from __future__ import annotations

import os
import socket
import time

from . import store

FILE = "bail.json"
DUREE = 120


def identite() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"


def _vide() -> dict:
    return {"numero": 0, "bail": None}


def _mort(b: dict) -> bool:
    """Le titulaire est sur ce poste et son processus n'existe plus."""
    if b.get("hote") != socket.gethostname():
        return False
    try:
        os.kill(int(b.get("pid") or 0), 0)
    except ProcessLookupError:
        return True
    except (PermissionError, ValueError, OSError):
        return False
    return int(b.get("pid") or 0) <= 0


def acquerir(titulaire: str | None = None, duree: int = DUREE, now: float | None = None) -> dict | None:
    """Prend (ou garde) le bail. None si un autre orchestrateur le tient encore."""
    titulaire = titulaire or identite()
    now = now or time.time()

    def _prendre(data):
        b = data.get("bail")
        a_nous = bool(b) and b["titulaire"] == titulaire and now < b["expire"]
        if b and not a_nous and now < b["expire"] and not _mort(b):
            return None
        if not a_nous:
            data["numero"] = int(data.get("numero", 0)) + 1
        hote, _, pid = titulaire.rpartition(":")
        data["bail"] = {"titulaire": titulaire, "hote": hote, "pid": int(pid) if pid.isdigit() else 0,
                        "numero": data["numero"], "depuis": b["depuis"] if a_nous else now, "expire": now + duree,
                        "renouvele": now}
        return dict(data["bail"])

    return store.update_json(FILE, _vide(), _prendre)


def renouveler(titulaire: str, numero: int, duree: int = DUREE, now: float | None = None) -> dict | None:
    """Prolonge le bail s'il est toujours le nôtre (même titulaire, même numéro). None : bail perdu."""
    now = now or time.time()

    def _prolonger(data):
        b = data.get("bail")
        if not b or b["titulaire"] != titulaire or int(b["numero"]) != int(numero):
            return None
        if now >= b["expire"]:
            return None  # expiré : un autre a pu le prendre entre-temps ; on repasse par acquerir
        b["expire"], b["renouvele"] = now + duree, now
        return dict(b)

    return store.update_json(FILE, _vide(), _prolonger)


def liberer(titulaire: str) -> bool:
    def _rendre(data):
        b = data.get("bail")
        if b and b["titulaire"] == titulaire:
            data["bail"] = None
            return True
        return False

    return bool(store.update_json(FILE, _vide(), _rendre))


def lire(now: float | None = None) -> dict | None:
    """Le bail en cours (valide), ou None."""
    now = now or time.time()
    b = store.read_json(FILE, _vide()).get("bail")
    if not b or now >= b["expire"] or _mort(b):
        return None
    return b
