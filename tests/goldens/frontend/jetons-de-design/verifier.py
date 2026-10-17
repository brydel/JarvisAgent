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
css = Path("styles.css").read_text(encoding="utf-8")
m = re.search(r":root\s*\{(.*?)\}", css, re.S)
verifier(m is not None, "pas de bloc :root")
racine = m.group(1) if m else ""
reste = css.replace(m.group(0), "") if m else css
verifier(len(re.findall(r"--couleur-[\w-]+\s*:", racine)) >= 4, "moins de 4 jetons --couleur- dans :root")
verifier(not re.search(r"#[0-9a-fA-F]{3,8}\b|rgba?\(", reste), "couleur en dur hors de :root")
verifier(reste.count("var(--couleur-") >= 7, "jetons non utilisés dans les composants")
for valeur in ("#10151c", "#4f8cff", "#19c37d", "#ff5c5c"):
    verifier(valeur.lower() in racine.lower(), f"valeur {valeur} perdue")
fin()
