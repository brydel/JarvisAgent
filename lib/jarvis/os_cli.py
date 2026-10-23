"""Commandes du socle Jarvis OS : contrats, capacités et mandats, sans appel de modèle implicite."""

from __future__ import annotations

import argparse
import getpass
import json
import sys
from pathlib import Path


def _lire(chemin: str) -> dict:
    path = Path(chemin)
    if path.stat().st_size > 128_000:
        raise ValueError("Fichier JSON trop volumineux (128 Ko maximum).")
    valeur = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(valeur, dict):
        raise ValueError("Un objet JSON est attendu.")
    return valeur


def _json(valeur) -> None:
    print(json.dumps(valeur, ensure_ascii=False, indent=2, allow_nan=False))


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="jarvis os", description="Socle personnel : contrats, capacités réelles et mandats.")
    sub = p.add_subparsers(dest="action", required=True)
    sub.add_parser("schemas", help="schémas versionnés des contrats")
    s = sub.add_parser("valider", help="valider un contrat sans exécuter de tâche")
    s.add_argument("type", choices=("agent", "tache", "run"))
    s.add_argument("fichier")
    s = sub.add_parser("diagnostic", help="observer les capacités sans inférence facturable")
    s.add_argument("--reseau", action="store_true", help="sonder explicitement une destination HTTPS officielle fixe")
    s = sub.add_parser("preflight", help="contrôler les prérequis, sans réserver ni exécuter")
    s.add_argument("agent")
    s.add_argument("tache")
    s.add_argument("--destination", default="")
    s.add_argument("--cout-centimes", type=int, default=0)
    s = sub.add_parser("mandat", help="consulter ou administrer un mandat personnel")
    actions = s.add_subparsers(dest="commande", required=True)
    actions.add_parser("liste")
    a = actions.add_parser("voir"); a.add_argument("id")
    a = actions.add_parser("creer"); a.add_argument("fichier")
    a = actions.add_parser("revoquer"); a.add_argument("id")
    a = actions.add_parser("verifier"); a.add_argument("id"); a.add_argument("fichier")
    from . import communaute_cli
    communaute_cli.ajouter(sub)
    s = sub.add_parser("connexions", help="connecter et découvrir des outils MCP")
    actions = s.add_subparsers(dest="commande", required=True)
    actions.add_parser("liste")
    a = actions.add_parser("creer"); a.add_argument("fichier")
    a = actions.add_parser("decouvrir"); a.add_argument("id")
    a = actions.add_parser("revoquer"); a.add_argument("id")
    s = sub.add_parser("outils", help="catalogue, appels sous mandat et reçus d'opérations")
    actions = s.add_subparsers(dest="commande", required=True)
    actions.add_parser("liste")
    a = actions.add_parser("executer"); a.add_argument("fichier")
    a = actions.add_parser("operations"); a.add_argument("--projet")
    a = actions.add_parser("voir"); a.add_argument("id")
    from . import runtime_cli
    runtime_cli.ajouter(sub)
    return p


def main(argv=None) -> int:
    from . import capacites, contrats, mandats, specifications
    a = parser().parse_args(argv)
    try:
        if a.action == "schemas":
            _json(contrats.schemas())
        elif a.action == "valider":
            validateur = {"agent": contrats.valider_agent, "tache": contrats.valider_tache, "run": contrats.valider_run}[a.type]
            valeur = validateur(_lire(a.fichier))
            _json({"valide": True, "empreinte": contrats.empreinte(valeur), "contrat": valeur})
        elif a.action == "diagnostic":
            _json(capacites.collecter(sonder_reseau=a.reseau))
        elif a.action in ("runtime", "modele", "oauth"):
            from . import runtime_cli
            code, valeur = runtime_cli.executer(a)
            if valeur is not None:
                _json(valeur)
            return code
        elif a.action == "communaute":
            from . import communaute_cli
            _json(communaute_cli.executer(a))
        elif a.action == "connexions":
            from . import connexions
            if a.commande in ("creer", "revoquer"):
                from .cli import _human_only
                refuse = _human_only("administrer une connexion MCP")
                if refuse is not None:
                    return refuse
            if a.commande == "liste":
                _json({"connexions": connexions.lister()})
            elif a.commande == "decouvrir":
                _json(connexions.decouvrir(a.id))
            elif a.commande == "creer":
                _json(connexions.enregistrer(_lire(a.fichier), par=getpass.getuser()))
            else:
                _json(connexions.revoquer(a.id, par=getpass.getuser()))
        elif a.action == "outils":
            from . import outils
            if a.commande == "liste":
                _json(outils.catalogue())
            elif a.commande == "operations":
                _json({"operations": outils.operations(project=a.projet)})
            elif a.commande == "voir":
                _json(outils.operation(a.id))
            else:
                from .communaute_cli import auteur
                resultat = outils.executer(_lire(a.fichier), par=auteur())
                _json(resultat)
                return 0 if resultat["status"] == "succeeded" else 2
        elif a.action == "preflight":
            r = specifications.preflight(_lire(a.agent), _lire(a.tache), capacites.collecter(),
                                        destination=a.destination, cost_cents=a.cout_centimes)
            _json(r)
            return 0 if r["admis"] else 2
        elif a.action == "mandat":
            if a.commande in ("creer", "revoquer"):
                from .cli import _human_only
                refuse = _human_only(f"« jarvis os mandat {a.commande} »")
                if refuse is not None:
                    return refuse
            if a.commande == "liste":
                _json(mandats.lister())
            elif a.commande == "voir":
                r = mandats.get(a.id)
                if r is None:
                    raise ValueError("Mandat inconnu.")
                _json(r)
            elif a.commande == "creer":
                _json(mandats.creer(_lire(a.fichier), par=getpass.getuser()))
            elif a.commande == "revoquer":
                _json(mandats.revoquer(a.id, par=getpass.getuser()))
            elif a.commande == "verifier":
                r = mandats.autoriser(a.id, _lire(a.fichier))
                _json(r)
                return 0 if r["admis"] else 2
        return 0
    except (OSError, UnicodeError, ValueError) as exc:
        # Les parseurs ne renvoient pas les valeurs de champs de credentials ni le contenu du fichier.
        message = "JSON invalide." if isinstance(exc, json.JSONDecodeError) else str(exc)
        print(f"Erreur : {message}", file=sys.stderr)
        return 1
