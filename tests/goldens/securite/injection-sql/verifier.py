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

import sqlite3
conn = sqlite3.connect(":memory:")
conn.execute("CREATE TABLE clients (id INTEGER, nom TEXT)")
conn.executemany("INSERT INTO clients VALUES (?, ?)", [(1, "Ana"), (2, "Bob"), (3, "O'Neil")])
m = charger("clients.py")
verifier(m.chercher_client(conn, "Bob") == [(2, "Bob")], "recherche normale cassée")
verifier(m.chercher_client(conn, "O'Neil") == [(3, "O'Neil")], "nom avec apostrophe cassé")
try:
    r = m.chercher_client(conn, "' OR '1'='1")
    verifier(r == [], "injection SQL possible")
except sqlite3.Error:
    verifier(False, "la requête échoue sur une entrée hostile au lieu de la traiter comme une donnée")
fin()
