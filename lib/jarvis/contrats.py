"""Contrats JSON communs des agents, tâches et exécutions de Jarvis OS (version 1).

Les contrats décrivent une demande et ses bornes ; ils n'accordent aucun outil et ne prouvent ni disponibilité
ni authentification. Les appels au moteur de politique et au diagnostic restent nécessaires avant exécution.
Les validateurs refusent les champs inconnus et renvoient des copies avec les valeurs par défaut appliquées.
Un contrat ne transporte jamais de secret : les clés d'authentification n'appartiennent pas à ces schémas.

Valeurs par défaut : fournisseur automatique, modèle non imposé, aucun outil ni délégation, plafonds jetons/coût
inconnus (null) et 300 secondes au maximum. Une tâche utilise le moteur local et une seule tentative. Un budget
inconnu n'accorde rien et zéro ne signifie jamais « illimité » ; ce contrat ne rend pas les limites du vieux
runner effectives par sa seule présence. Les contrats existants ne sont pas automatiquement migrés.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import re

VERSION = 1
_DIALECTE = "https://json-schema.org/draft/2020-12/schema"
_ID = {"type": "string", "minLength": 1, "maxLength": 128,
       "pattern": r"^[A-Za-z0-9][A-Za-z0-9_.:/@-]*$"}
_REFERENCE = {"type": "string", "minLength": 1, "maxLength": 1000}


class ContratError(ValueError):
    """Contrat invalide. Le message nomme le champ, sans reproduire sa valeur."""


def _liste(item: dict, *, default: list | None = None, minimum: int = 0) -> dict:
    s = {"type": "array", "items": item, "minItems": minimum, "maxItems": 256, "uniqueItems": True}
    if default is not None:
        s["default"] = default
    return s


def _objet(properties: dict, required: list[str] | None = None, **extra) -> dict:
    return {"type": "object", "additionalProperties": False, "properties": properties,
            "required": required or [], **extra}


_AGENT = _objet({
    "version": {"type": "integer", "enum": [VERSION]},
    "id": _ID,
    "role": {"type": "string", "minLength": 1, "maxLength": 100},
    "profile": {"type": "string", "enum": ["documentaire", "outille", "code"]},
    "provider": {"type": "string", "minLength": 1, "maxLength": 200, "default": "auto",
                 "description": "Identifiant du registre fournisseur ; son existence et son accès restent à vérifier."},
    "model": {"type": "string", "maxLength": 200, "default": ""},
    "tools": _liste(_ID, default=[]),
    "required_capabilities": _liste(_ID, default=[]),
    "budget": _objet({
        "max_tokens": {"type": ["integer", "null"], "minimum": 0, "maximum": 1_000_000_000, "default": None},
        "max_cost_cents": {"type": ["integer", "null"], "minimum": 0, "maximum": 1_000_000_000, "default": None},
        "max_duration_s": {"type": ["integer", "null"], "minimum": 1, "maximum": 86_400, "default": 300},
    }, default={}),
    "delegation": _objet({
        "max_depth": {"type": "integer", "minimum": 0, "maximum": 16, "default": 0},
        "max_children": {"type": "integer", "minimum": 0, "maximum": 256, "default": 0},
    }, default={}),
}, ["version", "id", "role", "profile"], title="AgentSpec",
   description="Rôle, profil et limites demandés. Les outils restent à autoriser et à vérifier.",
   **{"$schema": _DIALECTE, "$id": "urn:jarvis:agent-spec:v1"})

_TACHE = _objet({
    "version": {"type": "integer", "enum": [VERSION]},
    "id": _ID,
    "agent_id": _ID,
    "objective": {"type": "string", "minLength": 1, "maxLength": 20_000},
    "project": {"type": "string", "maxLength": 200},
    "depends_on": _liste(_ID, default=[]),
    "inputs": _liste(_REFERENCE, default=[]),
    "acceptance": _liste({"type": "string", "minLength": 1, "maxLength": 4000}, minimum=1),
    "required_tools": _liste(_ID, default=[]),
    "mandate_id": {"type": ["string", "null"], "minLength": 1, "maxLength": 128, "default": None},
    "execution_engine": {"type": "string", "enum": ["local", "temporal"], "default": "local"},
    "max_attempts": {"type": "integer", "minimum": 1, "maximum": 100, "default": 1},
}, ["version", "id", "agent_id", "objective", "project", "acceptance"], title="TaskSpec",
   description="Objectif vérifiable et entrées d'une tâche ; les références sont résolues par le plan de contrôle.",
   **{"$schema": _DIALECTE, "$id": "urn:jarvis:task-spec:v1"})

_RUN = _objet({
    "version": {"type": "integer", "enum": [VERSION]},
    "id": _ID,
    "agent_id": _ID,
    "task_id": _ID,
    "status": {"type": "string", "enum": ["planned", "running", "blocked", "succeeded", "failed", "cancelled"]},
    "source": {"type": "string", "enum": ["board", "workmux", "cli"]},
    "session_ref": {"type": ["string", "null"], "minLength": 1, "maxLength": 1000, "default": None},
    "evidence": _liste(_REFERENCE, default=[]),
}, ["version", "id", "agent_id", "task_id", "status", "source"], title="RunSpec",
   description="État d'une exécution et références de preuves ; aucune réussite n'est déduite du seul contrat.",
   **{"$schema": _DIALECTE, "$id": "urn:jarvis:run-spec:v1"})

_SCHEMAS = {"agent": _AGENT, "task": _TACHE, "run": _RUN}


def schemas() -> dict:
    """Schémas JSON publiables et versionnés ; une copie évite qu'un appelant modifie la validation."""
    return {"version": VERSION, **copy.deepcopy(_SCHEMAS)}


def _valider(value: object, schema: dict, path: str) -> object:
    types = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
    ok = any((t == "object" and isinstance(value, dict))
             or (t == "array" and isinstance(value, list))
             or (t == "string" and isinstance(value, str))
             or (t == "integer" and type(value) is int)
             or (t == "null" and value is None) for t in types)
    if not ok:
        raise ContratError(f"{path} : type invalide ({', '.join(types)} attendu)")
    if "enum" in schema and value not in schema["enum"]:
        raise ContratError(f"{path} : valeur non prise en charge")
    if value is None:
        return None
    if isinstance(value, dict):
        if not all(isinstance(k, str) for k in value):
            raise ContratError(f"{path} : les clés doivent être du texte")
        properties = schema["properties"]
        if value.keys() - properties.keys():
            # Ne pas reproduire la valeur ni même le nom d'une clé fournie : elle pourrait contenir un secret.
            raise ContratError(f"{path} : champ inconnu (authentifiants interdits dans un contrat)")
        for key in schema.get("required", []):
            if key not in value:
                raise ContratError(f"{path}.{key} : champ obligatoire absent")
        result = {}
        for key, sub in properties.items():
            if key in value:
                result[key] = _valider(value[key], sub, f"{path}.{key}")
            elif "default" in sub:
                result[key] = _valider(copy.deepcopy(sub["default"]), sub, f"{path}.{key}")
        return result
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0) or len(value) > schema.get("maxItems", len(value)):
            raise ContratError(f"{path} : nombre d'éléments hors bornes")
        result = [_valider(x, schema["items"], f"{path}[{i}]") for i, x in enumerate(value)]
        # Les listes des trois contrats v1 contiennent uniquement des chaînes validées.
        if schema.get("uniqueItems") and len(result) != len(set(result)):
            raise ContratError(f"{path} : doublons interdits")
        return result
    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0) or len(value) > schema.get("maxLength", len(value)):
            raise ContratError(f"{path} : longueur hors bornes")
        if schema.get("minLength", 0) and not value.strip():
            raise ContratError(f"{path} : texte vide")
        if any(ord(c) < 32 and c not in "\n\t" for c in value) or "\x7f" in value:
            raise ContratError(f"{path} : caractère de contrôle interdit")
        if "pattern" in schema and re.fullmatch(schema["pattern"], value) is None:
            raise ContratError(f"{path} : identifiant invalide")
        return value
    if type(value) is int:
        if value < schema.get("minimum", value) or value > schema.get("maximum", value):
            raise ContratError(f"{path} : nombre hors bornes")
        return value
    raise ContratError(f"{path} : type non pris en charge")


def valider_agent(obj: object) -> dict:
    """Valide AgentSpec v1 ; les capacités demandées ne sont jamais présentées comme disponibles."""
    return _valider(obj, _AGENT, "agent")


def valider_tache(obj: object) -> dict:
    """Valide TaskSpec v1. Le contrôle des cycles entre plusieurs tâches appartient au planificateur."""
    tache = _valider(obj, _TACHE, "task")
    if tache["id"] in tache["depends_on"]:
        raise ContratError("task.depends_on : une tâche ne peut pas dépendre d'elle-même")
    return tache


def valider_run(obj: object) -> dict:
    """Valide RunSpec v1 sans inférer de session, de preuve ou de succès non observé."""
    return _valider(obj, _RUN, "run")


def _json_strict(value: object, depth: int = 0) -> None:
    if depth > 64:
        raise ContratError("empreinte : objet trop imbriqué")
    if value is None or type(value) in (str, bool, int):
        return
    if type(value) is float:
        if not math.isfinite(value):
            raise ContratError("empreinte : nombre non fini interdit")
        return
    if isinstance(value, dict):
        if not all(isinstance(k, str) for k in value):
            raise ContratError("empreinte : les clés doivent être du texte")
        for v in value.values():
            _json_strict(v, depth + 1)
        return
    if isinstance(value, list):
        for v in value:
            _json_strict(v, depth + 1)
        return
    raise ContratError("empreinte : une valeur non JSON est interdite")


def empreinte(obj: object) -> str:
    """SHA-256 d'un objet JSON canonique ; valider le contrat avant de figer sa version normalisée."""
    _json_strict(obj)
    try:
        data = json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise ContratError("empreinte : objet JSON invalide") from exc
    return hashlib.sha256(data).hexdigest()
