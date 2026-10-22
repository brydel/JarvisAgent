"""Atelier des agents : lecture et propositions, jamais de nouveaux droits implicites.

Cette facade locale utilise les roles et le protocole de canari existants. Les roles
etant encore stockes hors tenant, l'atelier refuse tout tenant autre que le local.
Une verification structurelle n'est PAS une evaluation de la qualite d'un modele.
"""
from __future__ import annotations

import difflib
import threading
from . import config, missions, roles, versions_roles

_LOCK = threading.RLock()
MAX_BRIEF = 24000


def _local(tenant_id: str) -> None:
    if tenant_id != missions.tenant_local():
        raise missions.MissionError("interdit", "Atelier disponible uniquement pour le tenant local.")


def _role(name: str) -> dict:
    role = roles.get(name)
    if not role:
        raise missions.MissionError("inconnue", "Agent inconnu.")
    return role


def _candidate(p: dict) -> dict:
    # Ne pas transmettre les chemins locaux, les acteurs prives ou les champs futurs.
    keys = ("id", "role", "statut", "ts", "pourquoi", "base", "empreinte", "pct")
    return {k: p.get(k) for k in keys}


def catalogue(tenant_id: str) -> dict:
    _local(tenant_id)
    candidates = versions_roles.toutes()
    result = []
    for r in roles.tous().values():
        visible = {k: r[k] for k in ("nom", "titre", "court", "equipe", "sigle", "fournisseur", "niveau", "resume", "corps")}
        visible["empreinte"] = versions_roles.empreinte(r["corps"])
        visible["candidats"] = [_candidate(p) for p in candidates if p["role"] == r["nom"]][-12:]
        result.append(visible)
    settings = config.settings()
    return {"agents": result, "execution": missions.etat_execution(tenant_id),
            "politique": {"max_agents": settings["general"]["max_agents"],
                          "validation_plans": settings["plans"]["validation"],
                          "fournisseurs_defaut": ["claude", "codex"],
                          "model_bridge": "desactive", "portee": "personnelle_locale"}}


def _valider(tenant_id: str, name: str, body: dict) -> tuple[dict, str]:
    _local(tenant_id)
    r = _role(name)
    text = body.get("corps")
    if not isinstance(text, str) or not 80 <= len(text.strip()) <= MAX_BRIEF:
        raise missions.MissionError("validation", "Les consignes doivent contenir entre 80 et 24 000 caracteres.")
    if body.get("base") != versions_roles.empreinte(r["corps"]):
        raise missions.MissionError("conflit", "Les consignes ont change. Recharge l'agent avant de proposer.")
    header, clean = versions_roles._corps_seul(text)
    if header:
        raise missions.MissionError("interdit", "L'atelier ne modifie ni fournisseur, ni permissions, ni en-tete du role.")
    return r, clean


def verifier(tenant_id: str, name: str, body: dict) -> dict:
    r, text = _valider(tenant_id, name, body)
    reasons = versions_roles.controler(r["nom"], text)
    changed = versions_roles.empreinte(text) != versions_roles.empreinte(r["corps"])
    if not changed:
        reasons.append("Les consignes sont identiques a la version stable.")
    return {"valide": not reasons, "raisons": reasons, "evaluation": "structurelle_sans_inference",
            "diff": "\n".join(difflib.unified_diff(r["corps"].splitlines(), text.splitlines(),
                                                   "stable", "proposition", lineterm="")),
            "empreinte": versions_roles.empreinte(text), "base": versions_roles.empreinte(r["corps"]),
            "qualite_modele": None}


def proposer(tenant_id: str, name: str, body: dict) -> dict:
    with _LOCK:
        r, text = _valider(tenant_id, name, body)
        why = body.get("pourquoi")
        if not isinstance(why, str) or not 8 <= len(why.strip()) <= 800:
            raise missions.MissionError("validation", "Explique l'amelioration attendue (8 a 800 caracteres).")
        try:
            p = versions_roles.proposer(r["nom"], text, why.strip(), par="studio:humain", source="atelier")
        except versions_roles.VersionError as exc:
            raise missions.MissionError("conflit", str(exc)) from exc
        return {"candidat": _candidate(p), "actif": False}


def comparer(tenant_id: str, candidate_id: str) -> dict:
    _local(tenant_id)
    p = versions_roles.get(candidate_id)
    if p is None:
        raise missions.MissionError("inconnue", "Proposition inconnue.")
    try:
        text = versions_roles.corps_candidat(p)
        return {"candidat": _candidate(p), "corps": text, "diff": versions_roles.diff_complet(p)}
    except (versions_roles.VersionError, OSError) as exc:
        raise missions.MissionError("conflit", "Proposition illisible ou modifiee : approbation refusee.") from exc


def decider(tenant_id: str, candidate_id: str, body: dict) -> dict:
    _local(tenant_id)
    with _LOCK:
        p = versions_roles.get(candidate_id)
        if p is None:
            raise missions.MissionError("inconnue", "Proposition inconnue.")
        # Le clic est lie au contenu relu : aucune approbation d'un candidat remplace.
        if body.get("empreinte") != p["empreinte"]:
            raise missions.MissionError("conflit", "Relis la proposition actuelle avant de decider.")
        action = body.get("action")
        try:
            if action == "essayer":
                r = _role(p["role"])
                clean = versions_roles.corps_candidat(p)
                if versions_roles.controler(r["nom"], clean):
                    raise versions_roles.VersionError("La proposition ne respecte plus les regles du role.")
                result = versions_roles.decider(candidate_id, True, "studio:humain")
            elif action == "retirer":
                result = versions_roles.retirer(candidate_id, "studio:humain", "Retrait depuis l'atelier")
            else:
                raise missions.MissionError("interdit", "Action non autorisee. La promotion stable reste au terminal.")
        except (versions_roles.VersionError, OSError) as exc:
            raise missions.MissionError("conflit", str(exc)) from exc
        return {"candidat": _candidate(result)}
