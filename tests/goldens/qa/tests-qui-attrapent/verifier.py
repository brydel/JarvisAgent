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

import shutil, tempfile
MUTANTS = {
    "borne": "def remise(prix, pct):\n    if not 0 <= pct <= 101:\n        raise ValueError('x')\n    return round(prix * (100 - pct) / 100, 2)\n",
    "arrondi": "def remise(prix, pct):\n    if not 0 <= pct <= 100:\n        raise ValueError('x')\n    return int(prix * (100 - pct) / 100)\n",
    "formule": "def remise(prix, pct):\n    if not 0 <= pct <= 100:\n        raise ValueError('x')\n    return round(prix * pct / 100, 2)\n",
}
def lancer(calcul_source):
    with tempfile.TemporaryDirectory() as d:
        shutil.copytree("tests", Path(d) / "tests")
        Path(d, "calcul.py").write_text(calcul_source)
        r = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", "."], cwd=d,
                           capture_output=True, text=True, timeout=60)
        return r.returncode, r.stderr
verifier(Path("tests/test_calcul.py").is_file(), "tests/test_calcul.py absent")
if not ECHECS:
    rc, err = lancer(Path("calcul.py").read_text())
    verifier(rc == 0, "les tests échouent sur le code correct : " + err.strip()[-200:])
    verifier("Ran 0 tests" not in err, "aucun test exécuté")
    for nom, src in MUTANTS.items():
        verifier(lancer(src)[0] != 0, f"régression « {nom} » non détectée")
fin()
