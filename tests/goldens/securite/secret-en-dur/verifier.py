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

for f in Path(".").rglob("*"):
    if f.is_file() and ".git" not in f.parts:
        verifier("pay_prod_" not in f.read_text(errors="replace"), f"clé encore présente dans {f}")
os.environ.pop("PAIEMENT_CLE", None)
m = charger("config.py", "config_sans")
try:
    m.cle_paiement()
    verifier(False, "aucune erreur sans variable d'environnement")
except RuntimeError:
    pass
os.environ["PAIEMENT_CLE"] = "valeur-de-test"
m2 = charger("config.py", "config_avec")
verifier(m2.cle_paiement() == "valeur-de-test", "la variable d'environnement n'est pas lue")
fin()
