"""Vérification cachée : lancée depuis le dossier du projet évalué. Code 0 = réussi."""
import importlib.util, os, subprocess, sys
from pathlib import Path

ECHECS = []

def verifier(cond, msg):
    if not cond:
        ECHECS.append(msg)

def charger(chemin, nom="m"):
    spec = importlib.util.spec_from_file_location(nom, Path(chemin).resolve())
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def fin():
    if ECHECS:
        print("ÉCHEC :\n- " + "\n- ".join(ECHECS))
        sys.exit(1)
    print("VERDICT: OK")
    sys.exit(0)

import re
f = Path("docs/note-version-1.3.md")
verifier(f.is_file(), "docs/note-version-1.3.md absent")
if f.is_file():
    t = f.read_text(encoding="utf-8")
    verifier(t.lstrip().startswith("#"), "pas de titre")
    mots = re.findall(r"[\wÀ-ÿ'’-]+", re.sub(r"^#.*$", "", t, flags=re.M))
    verifier(0 < len(mots) <= 150, f"{len(mots)} mots (150 au plus)")
    bas = t.lower()
    for sujet in ("alerte", "csv", "déconnexion"):
        verifier(sujet in bas, f"sujet absent : {sujet}")
    for jargon in ("pr ", "refactor", "endpoint", "backend", "commit", "api"):
        verifier(re.search(r"\b" + jargon.strip() + r"\b", bas) is None, f"jargon : {jargon.strip()}")
fin()
