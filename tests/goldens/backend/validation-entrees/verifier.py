"""Vérification cachée : lancée depuis le dossier du projet évalué. Code 0 = réussi."""
import importlib.util, os, subprocess, sys
from pathlib import Path

ECHECS = []
# Jeton aléatoire transmis par le harnais sur l'entrée standard, lu AVANT de charger le code évalué : un code qui
# imprime lui-même « VERDICT: OK » puis quitte ne le connaît pas, et le harnais exige le jeton.
JETON = "" if sys.stdin is None or sys.stdin.isatty() else sys.stdin.readline().strip()

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
    print(f"VERDICT: OK {JETON}".rstrip())
    sys.exit(0)

m = charger("app/utilisateurs.py")
verifier(m.creer_utilisateur(" Ana@Ex.com ", 30) == {"email": "ana@ex.com", "age": 30}, "cas valide modifié")
for email, age in (("sans-arobase", 30), ("", 30), ("a@b.c", -1), ("a@b.c", 151), ("a@b.c", "30"), ("a@b.c", True)):
    try:
        m.creer_utilisateur(email, age)
        verifier(False, f"accepté à tort : {email!r}, {age!r}")
    except ValueError:
        pass
fin()
