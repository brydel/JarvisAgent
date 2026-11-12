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

import hashlib, sqlite3
verifier(hashlib.sha256(Path("migrations/m001_initial.py").read_bytes()).hexdigest() == "615cdf7d10a85944c569655f59126f5cf5bc7c8e09f41d66a81b8a0020760f0e",
         "m001_initial.py a été modifié")
verifier(Path("migrations/m002_email_normalise.py").is_file(), "migrations/m002_email_normalise.py absent")
if not ECHECS:
    m1, m2 = charger("migrations/m001_initial.py", "m1"), charger("migrations/m002_email_normalise.py", "m2")
    conn = sqlite3.connect(":memory:")
    m1.monter(conn)
    conn.executemany("INSERT INTO clients (id, nom, email) VALUES (?, ?, ?)",
                     [(1, "Alice", "  Alice@Exemple.FR "), (2, "Bob", None), (3, "Chloé", "chloe@exemple.fr")])
    conn.commit()
    schema = lambda: [tuple(l[1:6]) for l in conn.execute("PRAGMA table_info(clients)")]
    index = lambda: sorted(l[1] for l in conn.execute("PRAGMA index_list(clients)"))
    lignes = lambda: list(conn.execute("SELECT id, nom, email FROM clients ORDER BY id"))
    avant = (schema(), index(), lignes())
    try:
        m2.monter(conn)
        m2.monter(conn)
        verifier([l[0] for l in schema()] == ["id", "nom", "email", "email_normalise"], "colonne email_normalise absente après la montée")
        if not ECHECS:
            valeurs = [l[0] for l in conn.execute("SELECT email_normalise FROM clients ORDER BY id")]
            verifier(valeurs == ["alice@exemple.fr", None, "chloe@exemple.fr"], f"email_normalise mal rempli : {valeurs}")
        verifier("ix_clients_email_normalise" in index(), "index ix_clients_email_normalise absent")
        verifier(lignes() == avant[2], "la montée a modifié des données existantes")
        m2.descendre(conn)
        m2.descendre(conn)
        verifier(schema() == avant[0], "le schéma après la descente n'est pas celui d'avant")
        verifier(index() == avant[1], "index encore présent après la descente")
        verifier(lignes() == avant[2], "la descente a perdu ou modifié des lignes")
        m2.monter(conn)
        verifier(conn.execute("SELECT email_normalise FROM clients WHERE id = 1").fetchone() == ("alice@exemple.fr",),
                 "la migration ne remonte pas après une descente")
    except Exception as exc:  # noqa: BLE001
        verifier(False, f"erreur pendant monter/descendre : {type(exc).__name__}: {exc}")
fin()
