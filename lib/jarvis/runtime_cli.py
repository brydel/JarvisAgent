"""Commandes du runtime outillé et de ses connexions, sans secret dans les arguments."""
from __future__ import annotations

import signal
import threading


def ajouter(sub):
    p = sub.add_parser("runtime", help="missions outillées, progression et revue")
    actions = p.add_subparsers(dest="commande", required=True)
    a = actions.add_parser("liste"); a.add_argument("--projet")
    for commande in ("voir", "executer", "pause", "reprendre", "annuler"):
        a = actions.add_parser(commande); a.add_argument("id")
    a = actions.add_parser("creer"); a.add_argument("fichier")
    a = actions.add_parser("evaluer"); a.add_argument("id")
    choix = a.add_mutually_exclusive_group(required=True)
    choix.add_argument("--accepter", action="store_true")
    choix.add_argument("--refuser", action="store_true")
    a.add_argument("--preuve", action="append", default=[])
    a.add_argument("--commentaire", required=True)
    p = sub.add_parser("modele", help="configuration API du modèle et vérification sans inférence")
    actions = p.add_subparsers(dest="commande", required=True)
    actions.add_parser("voir")
    actions.add_parser("verifier")
    a = actions.add_parser("configurer"); a.add_argument("fichier")
    p = sub.add_parser("oauth", help="connexion Google propriétaire par PKCE")
    actions = p.add_subparsers(dest="commande", required=True)
    actions.add_parser("liste")
    a = actions.add_parser("configurer"); a.add_argument("fichier")
    for commande in ("commencer", "revoquer"):
        a = actions.add_parser(commande); a.add_argument("id")


def executer(a):
    from . import agent_runtime, oauth, pilotage
    from .communaute_cli import auteur
    from .os_cli import _lire
    from .cli import _human_only
    par = auteur()
    if a.action in ("modele", "oauth"):
        if a.commande in ("configurer", "commencer", "revoquer"):
            refuse = _human_only("configurer ou autoriser une connexion de modèle/courriel")
            if refuse is not None:
                return refuse, None
        if a.action == "modele":
            if a.commande == "voir":
                return 0, pilotage.modele()
            if a.commande == "verifier":
                return 0, pilotage.verifier_modele()
            return 0, pilotage.configurer_modele(_lire(a.fichier), par=par)
        if a.commande == "liste":
            return 0, {"connexions": oauth.lister()}
        if a.commande == "configurer":
            return 0, oauth.configurer(_lire(a.fichier), par=par)
        return 0, (oauth.commencer if a.commande == "commencer" else oauth.revoquer)(a.id, par=par)
    if a.commande == "liste":
        return 0, {"runs": agent_runtime.lister(project=a.projet)}
    if a.commande == "voir":
        return 0, agent_runtime.voir(a.id)
    if a.commande == "creer":
        return 0, pilotage.creer_run(_lire(a.fichier), par=par, source="cli")
    if a.commande == "evaluer":
        return 0, agent_runtime.evaluer(a.id, par=par, accepte=a.accepter, preuves=a.preuve, commentaire=a.commentaire)
    if a.commande in ("pause", "annuler"):
        return 0, pilotage.commander(a.id, a.commande, par=par)
    precedents = {}

    def interrompre(*_):
        raise KeyboardInterrupt

    if threading.current_thread() is threading.main_thread():
        for sig in (signal.SIGTERM, signal.SIGHUP):
            precedents[sig] = signal.signal(sig, interrompre)
    try:
        pilotage.commander(a.id, a.commande, par=par)
        pilotage.attendre(a.id)
        resultat = agent_runtime.voir(a.id)
        return (0 if resultat["status"] in ("awaiting_review", "succeeded") else 2), resultat
    except KeyboardInterrupt:
        pilotage.arreter()
        return 130, agent_runtime.voir(a.id)
    finally:
        for sig, ancien in precedents.items():
            signal.signal(sig, ancien)
