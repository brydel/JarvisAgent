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

m = charger("app/cache.py")
t = [100.0]
try:
    c = m.Cache(ttl=10, horloge=lambda: t[0])
except TypeError:
    verifier(False, "Cache(ttl=…, horloge=…) n'existe pas")
    fin()
c.set("a", 1)
t[0] = 105
verifier(c.get("a") == 1, "valeur encore valide perdue")
t[0] = 111
verifier(c.get("a") is None, "valeur expirée renvoyée")
s = m.Cache()
s.set("b", 2)
verifier(s.get("b") == 2, "cache sans expiration cassé")
fin()
