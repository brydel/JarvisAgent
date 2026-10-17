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

m = charger("app/pagination.py")
e = list(range(1, 11))
verifier(m.paginer(e, 1, 3) == [1, 2, 3], "page 1 incorrecte")
verifier(m.paginer(e, 4, 3) == [10], "dernière page incorrecte")
verifier(m.paginer(e, 5, 3) == [], "au-delà de la dernière page")
for p, t in ((0, 3), (1, 0), (-1, 2)):
    try:
        m.paginer(e, p, t)
        verifier(False, f"accepté à tort : page={p}, taille={t}")
    except ValueError:
        pass
fin()
