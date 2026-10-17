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

import re
t = Path("README.md").read_text(encoding="utf-8")
verifier("## Installation" in t, "section Installation absente")
sec = t.split("## Installation", 1)[-1]
verifier(re.search(r"Python 3\.11", sec) is not None, "prérequis Python absent")
blocs = "\n".join(re.findall(r"```(?:bash|sh)?\n(.*?)```", sec, re.S))
for cmd in ("python3 -m venv .venv", "source .venv/bin/activate", "pip install -r requirements.txt", "python3 -m app"):
    verifier(cmd in blocs, f"commande absente du bloc de code : {cmd}")
verifier(re.search(r"^\s*1\.", sec, re.M) is not None, "étapes non numérotées")
verifier("http://localhost:8000" in sec, "résultat attendu absent")
verifier(blocs.index("venv") < blocs.index("pip install") < blocs.index("-m app") if all(x in blocs for x in ("venv", "pip install", "-m app")) else False, "commandes dans le désordre")
fin()
