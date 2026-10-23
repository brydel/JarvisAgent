"""Contrat du prototype : DAG borné d'appels à la passerelle, sans secret."""

from __future__ import annotations

import copy
import hashlib
import json
import re

IDENTIFIANT = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}\Z")
PHASES = {"plan", "recherche", "production", "revue"}
CLES_SECRETES = {"token", "secret", "password", "authorization", "cookie", "api_key", "apikey", "jeton"}


def _identifiant(valeur) -> str:
    if not isinstance(valeur, str) or not IDENTIFIANT.fullmatch(valeur):
        raise ValueError("Identifiant invalide (1 à 64 caractères alphanumériques, point, tiret, souligné).")
    return valeur


def _sans_secrets(valeur) -> None:
    if isinstance(valeur, dict):
        for cle, enfant in valeur.items():
            if not isinstance(cle, str) or cle.lower() in CLES_SECRETES:
                raise ValueError("Les secrets doivent rester dans la passerelle, hors de l'historique Temporal.")
            _sans_secrets(enfant)
    elif isinstance(valeur, list):
        for enfant in valeur:
            _sans_secrets(enfant)


def valider(spec: dict) -> dict:
    """Valide une copie stricte ; ne réclame aucune mission du moteur local."""
    if not isinstance(spec, dict) or set(spec) != {"version", "id", "engine", "project", "steps"}:
        raise ValueError("Champs attendus : version, id, engine, project, steps.")
    if type(spec["version"]) is not int or spec["version"] != 1:
        raise ValueError("Version de projet non prise en charge.")
    if spec["engine"] != "temporal_prototype":
        raise ValueError("Ce prototype n'est pas propriétaire des missions locales.")
    _identifiant(spec["id"])
    if not isinstance(spec["project"], str) or not spec["project"].strip() or len(spec["project"]) > 200:
        raise ValueError("Projet non vide attendu (200 caractères maximum).")
    if not isinstance(spec["steps"], list) or not 1 <= len(spec["steps"]) <= 32:
        raise ValueError("Un DAG contient de 1 à 32 étapes.")
    # Rejette aussi NaN, objets Python et entrées trop volumineuses avant leur enregistrement dans Temporal.
    try:
        encodage = json.dumps(spec, ensure_ascii=False, allow_nan=False)
    except (ValueError, TypeError, RecursionError) as exc:
        raise ValueError("Le projet doit être du JSON fini.") from exc
    if len(encodage.encode()) > 48_000:
        raise ValueError("Projet trop volumineux (48 Ko maximum).")
    _sans_secrets(spec)
    identifiants = set()
    for step in spec["steps"]:
        if not isinstance(step, dict) or set(step) != {"id", "phase", "depends_on", "operation", "timeout_s"}:
            raise ValueError("Étape attendue : id, phase, depends_on, operation, timeout_s.")
        sid = _identifiant(step["id"])
        if sid in identifiants:
            raise ValueError("Identifiant d'étape en double.")
        identifiants.add(sid)
        if not isinstance(step["phase"], str) or step["phase"] not in PHASES:
            raise ValueError("Phase inconnue.")
        deps = step["depends_on"]
        if not isinstance(deps, list) or len(deps) > 31 or any(not isinstance(d, str) for d in deps):
            raise ValueError("Liste de dépendances invalide.")
        if len(set(deps)) != len(deps) or sid in deps:
            raise ValueError("Dépendance en double ou sur l'étape elle-même.")
        if type(step["timeout_s"]) is not int or not 5 <= step["timeout_s"] <= 300:
            raise ValueError("Délai d'étape attendu entre 5 et 300 secondes.")
        op = step["operation"]
        if not isinstance(op, dict) or set(op) - {"tool", "arguments", "mandat_id", "cost_cents"}:
            raise ValueError("Opération invalide.")
        if not {"tool", "arguments", "mandat_id"} <= set(op):
            raise ValueError("L'opération exige tool, arguments et mandat_id.")
        for cle in ("tool", "mandat_id"):
            if not isinstance(op[cle], str) or not op[cle].strip() or len(op[cle]) > 200:
                raise ValueError("Outil et mandat non vides attendus.")
        if not isinstance(op["arguments"], dict):
            raise ValueError("Arguments d'outil JSON attendus.")
        if type(op.get("cost_cents", 0)) is not int or op.get("cost_cents", 0) < 0:
            raise ValueError("Coût prévu entier positif ou nul attendu.")
    for step in spec["steps"]:
        if set(step["depends_on"]) - identifiants:
            raise ValueError("Dépendance inconnue.")
    groupes(spec["steps"])
    return copy.deepcopy(spec)


def groupes(steps: list[dict]) -> list[list[dict]]:
    """Tri topologique stable ; les étapes indépendantes partagent une vague."""
    restant = list(steps)
    faits = set()
    vagues = []
    while restant:
        prets = [s for s in restant if set(s["depends_on"]) <= faits]
        if not prets:
            raise ValueError("Cycle détecté dans les dépendances.")
        vagues.append(prets)
        faits.update(s["id"] for s in prets)
        restant = [s for s in restant if s["id"] not in faits]
    return vagues


def workflow_id(spec: dict) -> str:
    return "jarvis-prototype-" + _identifiant(spec["id"])


def operation(spec: dict, step: dict) -> dict:
    # L'identité ne change ni avec la tentative d'activité, ni avec le redémarrage du worker.
    identite = f"{workflow_id(spec)}/{step['id']}".encode()
    return {**copy.deepcopy(step["operation"]), "project": spec["project"],
            "operation_id": "temporal-" + hashlib.sha256(identite).hexdigest()}
