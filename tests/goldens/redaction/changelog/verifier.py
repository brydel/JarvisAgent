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
t = Path("CHANGELOG.md").read_text(encoding="utf-8")
versions = re.findall(r"^## \[(\d+\.\d+\.\d+)\] - (\d{4}-\d{2}-\d{2})", t, re.M)
verifier(versions[:2] == [("1.3.0", "2026-10-17"), ("1.2.0", "2026-09-30")], "1.3.0 absente, mal datée ou pas en tête")
bloc = t.split("## [1.2.0]")[0]
verifier("### Ajouté" in bloc and "### Corrigé" in bloc, "sections Ajouté / Corrigé manquantes")
for mot in ("alerte", "csv", "négatif", "déconnexion"):
    verifier(mot in bloc.lower(), f"changement « {mot} » absent")
for anglais in ("Added", "Fixed", "Changed"):
    verifier(anglais not in bloc, f"titre en anglais : {anglais}")
verifier("Graphiques en bougies" in t, "historique supprimé")
fin()
