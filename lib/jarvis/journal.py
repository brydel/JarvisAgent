"""Journal d'audit : qui a décidé quoi, quand, et pourquoi (admissions, pauses, politique, budgets).

Fichier JSONL en ajout seul (journal.jsonl), distinct du fil d'activité (feed.jsonl) qui sert à
l'affichage. Chaque ligne porte un numéro, l'heure et l'empreinte SHA-256 de la ligne précédente :
une ligne modifiée ou supprimée après coup se détecte (« jarvis journal verifier »).

Limite honnête : le journal est écrit par le même utilisateur Linux que le chef et les agents. Il
rend une altération DÉTECTABLE, pas impossible. Une protection réelle demande un service séparé
(voir docs/autonomy/securite.md).
"""

from __future__ import annotations

import hashlib
import json
import time

from . import store

FILE = "journal.jsonl"
MAX_BYTES = 20_000_000
TYPES = ("admission", "pause", "politique", "budget", "reservation", "relance", "profil", "systeme", "proposition")


def _empreinte(ligne: str) -> str:
    return hashlib.sha256(ligne.encode("utf-8")).hexdigest()[:24]


def _derniere() -> tuple[int, str]:
    """(numéro, empreinte) de la dernière ligne, ou (0, "")."""
    path = store.state_path(FILE)
    try:
        with path.open("rb") as fh:
            fh.seek(0, 2)
            taille = fh.tell()
            fh.seek(max(0, taille - 4096))
            lignes = fh.read().decode("utf-8", errors="replace").strip().splitlines()
    except FileNotFoundError:
        return 0, ""
    for ln in reversed(lignes):
        try:
            ev = json.loads(ln)
            return int(ev.get("n", 0)), _empreinte(ln)
        except (json.JSONDecodeError, ValueError):
            continue
    return 0, ""


def ecrire(type_: str, *, acteur: str, objet: str, decision: str, raison: str = "", **extra) -> dict:
    """Ajoute une entrée. `acteur` : humain, chef, demon, cli… ; `decision` : admis, refuse, posee…"""
    if type_ not in TYPES:
        raise ValueError(f"type de journal inconnu « {type_} »")
    with store.locked(FILE):
        n, prev = _derniere()
        ev = {"n": n + 1, "ts": time.time(), "type": type_, "acteur": acteur, "objet": objet,
              "decision": decision, "raison": raison[:500], "prev": prev}
        ev.update({k: v for k, v in extra.items() if v is not None})
        path = store.state_path(FILE)
        if path.exists() and path.stat().st_size > MAX_BYTES:
            # Archive : le journal courant repart de zéro mais l'ancien reste lisible.
            path.rename(path.with_name(f"journal-{time.strftime('%Y%m%d-%H%M%S')}.jsonl"))
            ev["prev"] = ""
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(ev, ensure_ascii=False) + "\n")
    return ev


def lire(n: int = 50, type_: str | None = None) -> list[dict]:
    path = store.state_path(FILE)
    try:
        lignes = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return []
    out = []
    for ln in lignes:
        try:
            ev = json.loads(ln)
        except json.JSONDecodeError:
            continue
        if type_ and ev.get("type") != type_:
            continue
        out.append(ev)
    return out[-n:]


def verifier() -> tuple[bool, str]:
    """Contrôle la chaîne d'empreintes. (True, « n entrées, chaîne intacte ») ou (False, où ça casse)."""
    path = store.state_path(FILE)
    try:
        lignes = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return True, "journal vide"
    prev, n = "", 0
    for i, ln in enumerate(lignes, 1):
        try:
            ev = json.loads(ln)
        except json.JSONDecodeError:
            return False, f"ligne {i} illisible"
        if ev.get("prev", "") != prev:
            return False, f"chaîne rompue à la ligne {i} (entrée n°{ev.get('n')}) : une ligne a été modifiée ou retirée"
        if ev.get("n") != n + 1:
            return False, f"numérotation rompue à la ligne {i} (attendu {n + 1}, lu {ev.get('n')})"
        prev, n = _empreinte(ln), ev["n"]
    return True, f"{n} entrée(s), chaîne intacte"


def texte(entrees: list[dict] | None = None) -> str:
    entrees = lire() if entrees is None else entrees
    if not entrees:
        return "Journal vide."
    out = []
    for ev in entrees:
        quand = time.strftime("%d/%m %H:%M:%S", time.localtime(ev.get("ts", 0)))
        ligne = f"{quand}  {ev.get('type', ''):<11} {ev.get('decision', ''):<9} {ev.get('objet', '')}  [{ev.get('acteur', '')}]"
        if ev.get("raison"):
            ligne += f" — {ev['raison']}"
        out.append(ligne)
    return "\n".join(out)
