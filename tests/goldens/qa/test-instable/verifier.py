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

import time as _t
src = Path("tests/test_session.py").read_text()
verifier("sleep" not in src, "le test dort encore")
verifier("DUREE = 1" not in src, "le test modifie la durée au lieu de simuler le temps")
m = charger("session.py")
t = [0.0]
try:
    s = m.Session(horloge=lambda: t[0])
    t[0] = 29 * 60
    verifier(not s.expiree(), "session expirée trop tôt")
    t[0] = 30 * 60
    verifier(s.expiree(), "session non expirée après 30 min")
except TypeError:
    verifier(False, "Session(horloge=…) n'existe pas")
debut = _t.monotonic()
for _ in range(5):
    r = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", "."], capture_output=True,
                       text=True, timeout=60)
    verifier(r.returncode == 0, "le test échoue : " + r.stderr.strip()[-200:])
verifier(_t.monotonic() - debut < 10, "le test reste lent")
fin()
