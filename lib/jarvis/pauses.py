"""Pauses à causes indépendantes : humain, batterie, quota, ressources, incident, maintenance.

Avant, une seule pause (fichier « pause ») servait à tout : la batterie qui la posait pouvait la
lever alors que c'était toi qui l'avais demandée, ou l'inverse. Ici chaque cause a son propre état.
Jarvis est en pause tant qu'il reste AU MOINS une cause ; la disparition d'une cause ne lève jamais
les autres. Seul un humain lève la cause « humain » ; le démon gère batterie, quota et ressources ;
« incident » et « maintenance » se posent et se lèvent à la main (ou par « jarvis relancer »).

Compatibilité : l'ancien fichier « pause » est lu comme la cause « humain » et migré au premier accès.
"""

from __future__ import annotations

import time

from . import store

FILE = "pauses.json"
CAUSES = ("humain", "batterie", "quota", "ressources", "incident", "maintenance")
LIBELLES = {"humain": "pause demandée par ton humain", "batterie": "batterie faible, PC non branché",
            "quota": "jetons épuisés chez tous les fournisseurs", "ressources": "PC sous pression (mémoire ou processeur)",
            "incident": "incident en cours", "maintenance": "maintenance de Jarvis (mise à jour, relance)"}
# Qui peut lever quoi : le démon ne lève jamais une pause humaine, ni une maintenance.
AUTOMATIQUES = ("batterie", "quota", "ressources")


def _vide() -> dict:
    return {"causes": {}}


def _migrer(data: dict) -> dict:
    """L'ancien fichier « pause » (une seule pause globale) devient la cause « humain »."""
    ancien = store.state_path("pause")
    if ancien.exists():
        data["causes"].setdefault("humain", {"ts": ancien.stat().st_mtime, "note": "pause globale (ancienne version)",
                                             "par": "humain"})
        ancien.unlink(missing_ok=True)
    return data


def actives() -> dict[str, dict]:
    """{cause: {"ts", "note", "par"}} des causes en cours."""
    if store.state_path("pause").exists():
        store.update_json(FILE, _vide(), _migrer)
    return dict(store.read_json(FILE, _vide()).get("causes") or {})


def active() -> bool:
    return bool(actives())


def poser(cause: str, note: str = "", par: str = "") -> bool:
    """Pose une cause. Renvoie True si elle n'était pas déjà posée (événement à annoncer)."""
    if cause not in CAUSES:
        raise ValueError(f"cause de pause inconnue « {cause} » (valeurs : {', '.join(CAUSES)})")

    def _set(data):
        _migrer(data)
        if cause in data["causes"]:
            return False
        data["causes"][cause] = {"ts": time.time(), "note": note.strip()[:200], "par": par or cause}
        return True

    nouveau = store.update_json(FILE, _vide(), _set)
    if nouveau:
        store.feed_add("systeme", f"pause posée : {cause}" + (f" — {note}" if note else ""))
        try:
            from . import journal
            journal.ecrire("pause", acteur=par or cause, objet=cause, decision="posee", raison=note)
        except Exception:  # noqa: BLE001 — le journal est un plus, jamais un blocage
            pass
    return nouveau


def lever(cause: str, par: str = "") -> bool:
    """Lève UNE cause. Renvoie True si elle était posée. Les autres causes restent."""
    if cause not in CAUSES:
        raise ValueError(f"cause de pause inconnue « {cause} » (valeurs : {', '.join(CAUSES)})")

    def _unset(data):
        _migrer(data)
        return data["causes"].pop(cause, None) is not None

    levee = store.update_json(FILE, _vide(), _unset)
    if levee:
        restantes = actives()
        suite = f" (reste : {', '.join(sorted(restantes))})" if restantes else " : Jarvis peut relancer"
        store.feed_add("systeme", f"pause levée : {cause}{suite}")
        try:
            from . import journal
            journal.ecrire("pause", acteur=par or cause, objet=cause, decision="levee", raison=suite.strip(" :()"))
        except Exception:  # noqa: BLE001
            pass
    return levee


def texte(causes: dict | None = None) -> str:
    causes = actives() if causes is None else causes
    if not causes:
        return "aucune pause"
    parts = []
    for c in CAUSES:
        if c in causes:
            info = causes[c]
            depuis = time.strftime("%H:%M", time.localtime(info.get("ts", 0)))
            parts.append(f"{c} (depuis {depuis}" + (f", {info['note']}" if info.get("note") else "") + ")")
    return "en pause : " + " ; ".join(parts)


def resume_court(causes: dict | None = None) -> str:
    """« PAUSE humain+batterie » pour les en-têtes."""
    causes = actives() if causes is None else causes
    return "PAUSE " + "+".join(c for c in CAUSES if c in causes) if causes else ""
