"""Discussions libres de l'usine : identité locale issue du lanceur, sans auteur fourni par le texte."""
from __future__ import annotations

import os


def ajouter(sub) -> None:
    p = sub.add_parser("communaute", help="réseau libre des agents : usine, modèles, idées et projets")
    actions = p.add_subparsers(dest="commande", required=True)
    a = actions.add_parser("lire", help="lire les fils, ou les messages d'un fil")
    a.add_argument("id", nargs="?")
    a.add_argument("--projet", default="")
    a.add_argument("--salon")
    a.add_argument("--limite", type=int, default=30)
    for commande in ("publier", "repondre"):
        a = actions.add_parser(commande)
        if commande == "repondre":
            a.add_argument("id")
        a.add_argument("texte", nargs="+")
        a.add_argument("--projet", default="")
        a.add_argument("--salon", default="general")
        a.add_argument("--titre", default="")
        a.add_argument("--type", default="discussion")
        a.add_argument("--tache", default="")
        a.add_argument("--preuve", action="append", default=[])
        a.add_argument("--operation-id")
    a = actions.add_parser("evaluer", help="évaluer une amélioration, sans changer automatiquement le système")
    a.add_argument("id")
    a.add_argument("decision", choices=("evaluer", "retenir", "rejeter"))
    a.add_argument("texte", nargs="+")
    a.add_argument("--projet", default="")
    a.add_argument("--preuve", action="append", default=[])
    a.add_argument("--operation-id")
    a = actions.add_parser("lecons")
    a.add_argument("--projet", default="")


def auteur() -> str:
    if os.environ.get("JARVIS_ROLE") == "chef":
        return "chef"
    if os.environ.get("JARVIS_METIER"):
        from . import taches
        fiche = taches.par_chemin(os.getcwd())
        if fiche and fiche.get("role") == os.environ["JARVIS_METIER"]:
            return f"agent:{fiche['id']}"
        return f"agent:{os.environ['JARVIS_METIER']}"
    return "proprietaire"


def executer(a):
    from . import communaute, missions
    tenant = missions.tenant_local()
    if a.commande == "lire":
        if a.id:
            return communaute.fil(a.projet, a.id, limite=a.limite, tenant_id=tenant)
        return communaute.fils(a.projet, salon=a.salon, limite=a.limite, tenant_id=tenant)
    if a.commande == "lecons":
        return {"lecons": communaute.lecons(a.projet, tenant_id=tenant)}
    if a.commande == "evaluer":
        return communaute.evaluer(a.projet, a.id, auteur=auteur(), decision=a.decision,
                                  contenu=" ".join(a.texte), preuves=a.preuve,
                                  operation_id=a.operation_id, tenant_id=tenant)
    return communaute.publier(
        a.projet, " ".join(a.texte), auteur=auteur(), type=a.type, titre=a.titre,
        salon=a.salon, tache_id=a.tache, parent_id=a.id if a.commande == "repondre" else None,
        preuves=a.preuve, operation_id=a.operation_id, tenant_id=tenant)
