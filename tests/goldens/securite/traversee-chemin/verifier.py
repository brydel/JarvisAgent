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

import tempfile
m = charger("documents.py")
with tempfile.TemporaryDirectory() as d:
    base = Path(d, "docs")
    (base / "sous").mkdir(parents=True)
    (base / "sous" / "a.txt").write_text("ok")
    Path(d, "secret.txt").write_text("SECRET")
    verifier(m.lire_document(base, "sous/a.txt") == "ok", "lecture normale cassée")
    for nom in ("../secret.txt", "sous/../../secret.txt", str(Path(d, "secret.txt"))):
        try:
            contenu = m.lire_document(base, nom)
            verifier("SECRET" not in contenu, f"traversée possible avec {nom!r}")
        except PermissionError:
            pass
        except OSError:
            verifier(False, f"{nom!r} : erreur système au lieu d'un refus explicite")
    try:
        os.symlink(Path(d, "secret.txt"), base / "lien.txt")
        try:
            verifier("SECRET" not in m.lire_document(base, "lien.txt"), "traversée par lien symbolique")
        except PermissionError:
            pass
    except OSError:
        pass
fin()
