"""python3 -m controle_pg … (depuis services/controle_pg) : administration PostgreSQL de Jarvis Next.

  preparer [--base jarvis] [--nouveau-mot-de-passe]   base, rôle jarvis_app, schéma, RLS, droits (idempotent)
  dsn [--base jarvis]                                 DSN à mettre dans JARVIS_MISSIONS_PG (aucun secret dedans)
  migrer [--base jarvis] [--depuis CHEMIN]            copie vérifiée de missions.db (SQLite) vers PostgreSQL
  compte-creer COURRIEL NOM [--organisation ORG] [--role proprietaire|membre|lecteur]
  compte-tester COURRIEL                              vérifie un mot de passe, liste les organisations
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys
from pathlib import Path

from . import admin, comptes


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="controle_pg")
    ap.add_argument("action", choices=("preparer", "dsn", "migrer", "compte-creer", "compte-tester"))
    ap.add_argument("args", nargs="*")
    ap.add_argument("--base", default="jarvis")
    ap.add_argument("--nouveau-mot-de-passe", action="store_true")
    ap.add_argument("--depuis", default="")
    ap.add_argument("--organisation", default="ORG-personnel")
    ap.add_argument("--role", default="proprietaire")
    a = ap.parse_args(argv)
    try:
        if a.action == "preparer":
            dsn = admin.preparer(a.base, nouveau_mot_de_passe=a.nouveau_mot_de_passe)
            print(f"Base « {a.base} » prête (RLS active, rôle {admin.ROLE_APP}).\n"
                  f"Pour l'utiliser : export JARVIS_MISSIONS_PG=\"{dsn}\"")
        elif a.action == "dsn":
            print(admin.dsn_app(a.base))
        elif a.action == "migrer":
            etat = Path(os.environ.get("JARVIS_STATE_DIR") or Path.home() / ".local/state/jarvis")
            chemin = Path(a.depuis) if a.depuis else etat / "missions.db"
            if not chemin.exists():
                print(f"Rien à migrer : {chemin} n'existe pas.")
                return 0
            for table, n in admin.migrer_depuis_sqlite(chemin, a.base).items():
                print(f"  {table:<16} {n:>6} ligne(s) copiées et vérifiées")
            print(f"Migration terminée ; {chemin} n'a pas été modifié.")
        elif a.action == "compte-creer":
            if len(a.args) != 2:
                ap.error("compte-creer COURRIEL NOM")
            if not sys.stdin.isatty():
                print("Erreur : mot de passe à saisir dans un terminal interactif.", file=sys.stderr)
                return 4
            mdp = getpass.getpass("Mot de passe (12 caractères au moins) : ")
            if mdp != getpass.getpass("Confirme : "):
                print("Erreur : les deux saisies diffèrent.", file=sys.stderr)
                return 1
            cid = comptes.creer(admin.dsn_admin(a.base), a.args[0], a.args[1], mdp)
            comptes.adherer(admin.dsn_admin(a.base), cid, a.organisation, a.role)
            print(f"Compte {cid} créé, {a.role} de {a.organisation}.")
        elif a.action == "compte-tester":
            if len(a.args) != 1 or not sys.stdin.isatty():
                print("Erreur : compte-tester COURRIEL, dans un terminal interactif.", file=sys.stderr)
                return 4
            r = comptes.connexion(admin.dsn_app(a.base), a.args[0], getpass.getpass("Mot de passe : "))
            print(f"Connexion réussie : {r['nom']} ({r['id']}) — " +
                  ", ".join(f"{o['nom']} [{o['role']}]" for o in r["organisations"]))
        return 0
    except (comptes.CompteError, RuntimeError) as exc:
        print(f"Erreur : {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
