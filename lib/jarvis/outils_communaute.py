"""Outils de discussion interne ; l'auteur vient de l'exécutant, jamais du modèle."""
from __future__ import annotations

from . import communaute, missions


def catalogue():
    commun = {"projet": {"type": "string"}, "salon": {"type": "string"}}
    return [
        {"id": "communaute.lire", "nom": "Lire le réseau de l'usine", "effet": "lecture", "disponible": True,
         "inputSchema": {"type": "object", "properties": commun | {"fil_id": {"type": "string"}}, "additionalProperties": False}},
        {"id": "communaute.publier", "nom": "Discuter librement dans l'usine", "effet": "publication_interne", "disponible": True,
         "inputSchema": {"type": "object", "properties": commun | {"contenu": {"type": "string", "maxLength": 8000}, "titre": {"type": "string"}},
                         "required": ["contenu"], "additionalProperties": False}},
        {"id": "communaute.repondre", "nom": "Répondre à un agent", "effet": "publication_interne", "disponible": True,
         "inputSchema": {"type": "object", "properties": {"projet": {"type": "string"}, "fil_id": {"type": "string"},
                         "contenu": {"type": "string", "maxLength": 8000}}, "required": ["fil_id", "contenu"], "additionalProperties": False}},
    ]


def preparer(outil, arguments, operation_id, *, par):
    descripteur = next((o for o in catalogue() if o["id"] == outil), None)
    if descripteur is None or not isinstance(arguments, dict):
        raise ValueError("Outil de communauté inconnu.")
    from .outils import _valider_schema
    _valider_schema(arguments, descripteur["inputSchema"])

    def appeler(verifier):
        verifier()
        tenant = missions.tenant_local()
        projet = arguments.get("projet", "")
        if outil == "communaute.lire":
            if arguments.get("fil_id"):
                return communaute.fil(projet, arguments["fil_id"], limite=30, tenant_id=tenant)
            return communaute.fils(projet, salon=arguments.get("salon"), limite=20, tenant_id=tenant)
        return communaute.publier(projet, arguments["contenu"], auteur=par,
            salon=arguments.get("salon", "general"), titre=arguments.get("titre", ""),
            parent_id=arguments.get("fil_id"), operation_id="outil:" + operation_id, tenant_id=tenant)

    return "usine", outil != "communaute.lire", appeler
