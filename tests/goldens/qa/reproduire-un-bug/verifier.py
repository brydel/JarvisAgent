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

import shutil, tempfile
CORRIGE = "from datetime import date\n\ndef lire_date(texte):\n    j, m, a = (int(x) for x in texte.split('/'))\n    return date(a, m, j)\n"
def lancer(src):
    with tempfile.TemporaryDirectory() as d:
        shutil.copytree("tests", Path(d) / "tests")
        Path(d, "dates.py").write_text(src)
        r = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", "."], cwd=d,
                           capture_output=True, text=True, timeout=60)
        return r.returncode, r.stderr
verifier(Path("tests/test_dates.py").is_file(), "tests/test_dates.py absent")
if not ECHECS:
    verifier("int(x) for x in texte.split" in Path("dates.py").read_text() and "a, b, annee" in Path("dates.py").read_text(),
             "dates.py a été modifié (le bug devait être reproduit, pas corrigé)")
    rc_bug, err = lancer(Path("dates.py").read_text())
    verifier(rc_bug != 0, "le test ne reproduit pas le bug (il passe sur le code bogué)")
    verifier("Ran 0 tests" not in err, "aucun test exécuté")
    verifier(lancer(CORRIGE)[0] == 0, "le test échoue aussi sur le code corrigé")
fin()
