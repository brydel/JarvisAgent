"""Indexation explicite des fichiers du Board dans la bibliothèque de références."""
from __future__ import annotations

import json
import re
import shutil
import subprocess

from . import board, missions, references

TYPES = ("image", "capture", "audio", "video", "pdf", "document")
ROUTE = re.compile(r"/api/v2/fichiers/(BO-[0-9a-f]{12})/(indexer|memoire|contexte)")


def _carte(tenant: str, objet_id: str):
    c = missions._connecter(tenant)
    try:
        o = c.execute("SELECT id, type, meta, espace, asset_id FROM board_objets "
                      "WHERE tenant_id=? AND id=? AND supprime=0", (tenant, objet_id)).fetchone()
    finally:
        c.close()
    if not o or o["type"] not in TYPES:
        raise missions.MissionError("inconnue", "fichier introuvable sur le Board")
    return o


def _ref(tenant: str, o) -> str | None:
    reference = json.loads(o["meta"] or "{}").get("reference_id")
    if not isinstance(reference, str):
        return None
    with references._lire(tenant) as a:
        prete = a.c.execute("SELECT 1 FROM board_references WHERE tenant_id=? AND id=? AND statut='prete' AND supprime=0",
                            (tenant, reference)).fetchone()
    return reference if prete else None


def lire(tenant: str, objet_id: str, question: str = "") -> dict:
    ref = _ref(tenant, _carte(tenant, objet_id))
    passages = references.passages(tenant, [ref], question, par_reference=5) if ref else []
    if question.strip():
        passages = [p for p in passages if p["pertinence"] == "mots"]
    return {"reference_id": ref, "passages": passages}


def indexer(tenant: str, objet_id: str, extrait_local: str = "") -> dict:
    o = _carte(tenant, objet_id)
    if ref := _ref(tenant, o):
        return {"reference_id": ref, "texte_pdf": False}
    note = []
    texte_pdf = ""
    if o["asset_id"]:
        chemin, asset = board.fichier(tenant, o["asset_id"])
        note.append(f"Fichier original : {asset['nom']} · {asset['mime']} · {asset['taille']} octets")
        for cle in ("largeur", "hauteur", "duree"):
            if cle in asset["meta"]:
                note.append(f"{cle} : {asset['meta'][cle]}")
        if asset["mime"] == "application/pdf":
            texte_pdf = extrait_local.strip()
        if not texte_pdf and asset["mime"] == "application/pdf" and shutil.which("pdftotext"):
            try:
                extrait = subprocess.run(["pdftotext", "-f", "1", "-l", "24", "-enc", "UTF-8", str(chemin), "-"],
                                         capture_output=True, timeout=10)
                if extrait.returncode == 0:
                    texte_pdf = extrait.stdout[:23_000].decode("utf-8", errors="ignore").strip()
            except (OSError, subprocess.TimeoutExpired):
                pass
    if texte_pdf:
        note.append("\n## Extrait du PDF (24 premières pages au maximum)\n" + texte_pdf)
    fiche = references.ajouter(tenant, objet_id=objet_id, collection=o["espace"], note="\n".join(note),
                              auteur="studio:memoire", rattacher=True)
    return {"reference_id": fiche["id"], "texte_pdf": bool(texte_pdf)}
