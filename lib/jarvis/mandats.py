"""Mandats personnels versionnés, révocables et limités par quotas.

``autoriser`` est un préflight sans effet : son résultat n'est pas une réservation. ``reserver`` vérifie
de nouveau le mandat et consomme atomiquement une action et son coût prévu. L'identifiant d'opération est
global au registre ; le rejouer ne consomme rien de plus et changer ses paramètres est refusé.

Le mandat ne donne aucun outil et n'assouplit aucune politique existante. Une passerelle devra vérifier les
capacités effectives et appeler ``reserver`` juste avant l'effet. Une réservation n'est pas un reçu d'envoi.
Les quotas réservés restent consommés après panne ou annulation : aucun remboursement implicite.

Limite : ``par`` décrit l'acteur authentifié par l'appelant, ce n'est pas une preuve d'identité. Le stockage
local partage l'utilisateur Linux du reste de Jarvis ; l'interface doit contrôler qui crée/révoque un mandat.
"""

from __future__ import annotations

import copy
import hashlib
import ipaddress
import json
import math
import re
import secrets
import sqlite3
import time

from . import store

FICHIER = "mandats.json"
VERSION = 1
_MAX_ENTIER = 2 ** 53 - 1
_SPEC = {"version", "owner", "project", "tools", "destinations", "expires_at", "max_cost_cents", "max_actions"}
_RECORD = _SPEC | {"id", "created_at", "created_by", "revoked_at", "revoked_by", "used_cost_cents", "used_actions"}
_TOOL = re.compile(r"[A-Za-z][A-Za-z0-9_.:-]{0,127}\Z")
_OPERATION = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:/-]{0,127}\Z")
_LOCAL_EMAIL = re.compile(r"[A-Za-z0-9.!#$%&'+/=?^_`{|}~-]+\Z")


class MandatError(ValueError):
    """Contrat invalide ou registre illisible : aucun droit n'est déduit d'un état incomplet."""


def _texte(v, champ: str, longueur: int = 200) -> str:
    if not isinstance(v, str) or not v.strip() or len(v) > longueur or not all(c.isprintable() for c in v):
        raise MandatError(f"{champ} : texte non vide de {longueur} caractères au plus attendu")
    return v.strip()


def _entier(v, champ: str, minimum: int = 0) -> int:
    if type(v) is not int or not minimum <= v <= _MAX_ENTIER:
        raise MandatError(f"{champ} : entier entre {minimum} et {_MAX_ENTIER} attendu")
    return v


def _date(v, champ: str) -> float:
    if type(v) not in (int, float):
        raise MandatError(f"{champ} : date numérique finie attendue")
    try:
        d = float(v)
    except (ValueError, OverflowError) as exc:
        raise MandatError(f"{champ} : date numérique finie attendue") from exc
    if not math.isfinite(d) or d < 0:
        raise MandatError(f"{champ} : date numérique finie et positive attendue")
    return d


def _maintenant(now) -> float:
    return _date(time.time() if now is None else now, "now")


def _hote(v: str) -> str:
    if any(c in v for c in ":/@*?#\\") or any(c.isspace() for c in v):
        raise MandatError("destination : hôte exact sans schéma, port, chemin ni joker attendu")
    try:
        h = v.rstrip(".").encode("idna").decode("ascii").lower()
    except UnicodeError as exc:
        raise MandatError("destination : hôte invalide") from exc
    if not h or len(h) > 253:
        raise MandatError("destination : hôte invalide")
    if re.fullmatch(r"[0-9.]+", h):
        try:
            return str(ipaddress.IPv4Address(h))
        except ipaddress.AddressValueError as exc:
            raise MandatError("destination : adresse IPv4 invalide") from exc
    for label in h.split("."):
        if len(label) > 63 or not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?", label):
            raise MandatError("destination : hôte invalide")
    return h


def _destination(v) -> str:
    d = _texte(v, "destination", 320)
    if d != v:
        raise MandatError("destination : espaces de bord interdits")
    if d.startswith("mcp:"):
        if not re.fullmatch(r"mcp:[a-z][a-z0-9_-]{0,39}", d):
            raise MandatError("destination : connexion MCP locale exacte attendue")
        return d
    if "@" in d:
        if d.count("@") != 1:
            raise MandatError("destination : adresse email invalide")
        local, domaine = d.split("@", 1)
        if (not _LOCAL_EMAIL.fullmatch(local) or len(local) > 64 or local.startswith(".")
                or local.endswith(".") or ".." in local or "*" in local):
            raise MandatError("destination : adresse email exacte attendue")
        return f"{local}@{_hote(domaine)}"
    return _hote(d)


def _liste(v, champ: str, normaliser, *, minimum: int = 0, maximum: int = 128) -> list[str]:
    if not isinstance(v, list) or not minimum <= len(v) <= maximum:
        raise MandatError(f"{champ} : liste de {minimum} à {maximum} éléments attendue")
    valeurs = [normaliser(x) for x in v]
    if len(set(valeurs)) != len(valeurs):
        raise MandatError(f"{champ} : doublon interdit")
    return sorted(valeurs)


def _outil(v) -> str:
    if not isinstance(v, str) or not _TOOL.fullmatch(v):
        raise MandatError("tool : identifiant exact sans joker attendu")
    return v


def _valider_spec(spec) -> dict:
    if not isinstance(spec, dict) or set(spec) != _SPEC:
        raise MandatError("mandat : champs requis version, owner, project, tools, destinations, expires_at, max_cost_cents, max_actions")
    if type(spec["version"]) is not int or spec["version"] != VERSION:
        raise MandatError("mandat : version 1 requise")
    return {"version": VERSION, "owner": _texte(spec["owner"], "owner"),
            "project": _texte(spec["project"], "project"),
            "tools": _liste(spec["tools"], "tools", _outil, minimum=1),
            "destinations": _liste(spec["destinations"], "destinations", _destination),
            "expires_at": _date(spec["expires_at"], "expires_at"),
            "max_cost_cents": _entier(spec["max_cost_cents"], "max_cost_cents"),
            "max_actions": _entier(spec["max_actions"], "max_actions", 1)}


def _demande(demande) -> dict:
    if not isinstance(demande, dict) or not {"project", "tool"} <= set(demande) <= {"project", "tool", "destination", "cost_cents"}:
        raise MandatError("demande : project et tool requis ; destination et cost_cents facultatifs")
    destination = demande.get("destination")
    return {"project": _texte(demande["project"], "project"), "tool": _outil(demande["tool"]),
            "destination": _destination(destination) if destination is not None else None,
            "cost_cents": _entier(demande.get("cost_cents", 0), "cost_cents")}


def _empreinte(demande: dict) -> str:
    texte = json.dumps(demande, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(texte.encode("utf-8")).hexdigest()


def _vide() -> dict:
    return {"version": VERSION, "mandats": {}, "operations": {}}


def _valider_etat(data) -> dict:
    if (not isinstance(data, dict) or set(data) != {"version", "mandats", "operations"}
            or type(data.get("version")) is not int or data["version"] != VERSION
            or not isinstance(data["mandats"], dict) or not isinstance(data["operations"], dict)):
        raise MandatError("registre de mandats invalide ; aucune autorisation accordée")
    totaux = {}
    for ident, m in data["mandats"].items():
        if not isinstance(m, dict) or set(m) != _RECORD or m.get("id") != ident:
            raise MandatError("registre de mandats invalide ; aucune autorisation accordée")
        _texte(ident, "id", 128)
        spec = _valider_spec({k: m[k] for k in _SPEC})
        if any(m[k] != v for k, v in spec.items()):
            raise MandatError("registre de mandats non canonique")
        _date(m["created_at"], "created_at")
        _texte(m["created_by"], "created_by")
        if (m["revoked_at"] is None) != (m["revoked_by"] is None):
            raise MandatError("révocation incohérente dans le registre")
        if m["revoked_at"] is not None:
            _date(m["revoked_at"], "revoked_at")
            _texte(m["revoked_by"], "revoked_by")
        _entier(m["used_actions"], "used_actions")
        _entier(m["used_cost_cents"], "used_cost_cents")
        if m["used_actions"] > m["max_actions"] or m["used_cost_cents"] > m["max_cost_cents"]:
            raise MandatError("quotas incohérents dans le registre")
        totaux[ident] = [0, 0]
    for ident, op in data["operations"].items():
        if (not isinstance(ident, str) or not _OPERATION.fullmatch(ident) or not isinstance(op, dict)
                or set(op) != {"mandat_id", "empreinte", "demande", "created_at"}
                or op["mandat_id"] not in totaux):
            raise MandatError("opération incohérente dans le registre")
        demande = _demande(op["demande"])
        if demande != op["demande"] or _empreinte(demande) != op["empreinte"]:
            raise MandatError("empreinte d'opération incohérente")
        _date(op["created_at"], "created_at")
        totaux[op["mandat_id"]][0] += 1
        totaux[op["mandat_id"]][1] += demande["cost_cents"]
    for ident, (actions, cout) in totaux.items():
        m = data["mandats"][ident]
        if (actions, cout) != (m["used_actions"], m["used_cost_cents"]):
            raise MandatError("compteurs et réservations incohérents")
    return data


def _lire() -> dict:
    absent = object()
    try:
        data = store.read_json(FICHIER, absent)
        if data is absent:
            if store.existe(FICHIER):
                raise MandatError("registre de mandats illisible ; état conservé sans autorisation")
            return _vide()
        return _valider_etat(data)
    except (OSError, UnicodeError, sqlite3.Error) as exc:
        raise MandatError("registre de mandats inaccessible ; aucune autorisation accordée") from exc


def _modifier(fn):
    initial = _vide()

    def appliquer(data):
        # read_json masque la corruption en renvoyant son défaut. Tester l'identité et l'existence
        # SOUS le verrou de update_json évite de recréer un registre vide au-dessus d'un registre cassé.
        if data is initial and store.existe(FICHIER):
            raise MandatError("registre de mandats illisible ; état conservé sans modification")
        _valider_etat(data)
        resultat = fn(data)
        _valider_etat(data)
        return copy.deepcopy(resultat)

    try:
        return store.update_json(FICHIER, initial, appliquer)
    except (OSError, UnicodeError, sqlite3.Error) as exc:
        raise MandatError("registre de mandats inaccessible ; modification refusée") from exc


def creer(spec: dict, *, par: str, now: float | None = None) -> dict:
    """Crée un mandat figé. L'appelant contrôle l'identité du propriétaire ; aucun élargissement en place."""
    spec = _valider_spec(spec)
    par, now = _texte(par, "par"), _maintenant(now)
    if spec["expires_at"] <= now:
        raise MandatError("expires_at : le mandat doit expirer dans le futur")

    def ajouter(data):
        ident = "MA-" + secrets.token_hex(12)
        while ident in data["mandats"]:
            ident = "MA-" + secrets.token_hex(12)
        m = {**spec, "id": ident, "created_at": now, "created_by": par,
             "revoked_at": None, "revoked_by": None, "used_cost_cents": 0, "used_actions": 0}
        data["mandats"][ident] = m
        return m

    return _modifier(ajouter)


def lister() -> list[dict]:
    """Mandats complets, expirés/révoqués compris ; les lire ne crée pas de registre."""
    return copy.deepcopy(sorted(_lire()["mandats"].values(), key=lambda m: (m["created_at"], m["id"])))


def get(mandat_id: str) -> dict | None:
    mandat_id = _texte(mandat_id, "mandat_id", 128)
    return copy.deepcopy(_lire()["mandats"].get(mandat_id))


def revoquer(mandat_id: str, *, par: str, now: float | None = None) -> dict:
    mandat_id, par, now = _texte(mandat_id, "mandat_id", 128), _texte(par, "par"), _maintenant(now)

    def retirer(data):
        m = data["mandats"].get(mandat_id)
        if m is None:
            raise MandatError("mandat inconnu")
        if m["revoked_at"] is None:
            m.update(revoked_at=now, revoked_by=par)
        return m

    return _modifier(retirer)


def _decision(m: dict | None, demande: dict, now: float, *, quotas: bool = True) -> dict:
    raison = "autorisé par le mandat"
    if m is None:
        raison = "mandat inconnu"
    elif m["revoked_at"] is not None:
        raison = "mandat révoqué"
    elif now >= m["expires_at"]:
        raison = "mandat expiré"
    elif demande["project"] != m["project"]:
        raison = "projet hors mandat"
    elif demande["tool"] not in m["tools"]:
        raison = "outil hors mandat"
    elif (demande["destination"] is None and m["destinations"]) or (
            demande["destination"] is not None and demande["destination"] not in m["destinations"]):
        raison = "destination hors mandat ou manquante"
    elif quotas and m["used_actions"] >= m["max_actions"]:
        raison = "quota d'actions épuisé"
    elif quotas and m["used_cost_cents"] + demande["cost_cents"] > m["max_cost_cents"]:
        raison = "budget du mandat dépassé"
    admis = raison == "autorisé par le mandat"
    return {"admis": admis, "raison": raison, "mandat_id": m["id"] if m else None,
            "reservee": False, "doublon": False,
            "remaining_actions": m["max_actions"] - m["used_actions"] if m else 0,
            "remaining_cost_cents": m["max_cost_cents"] - m["used_cost_cents"] if m else 0}


def autoriser(mandat_id: str, demande: dict, *, now: float | None = None) -> dict:
    """Préflight sans consommation. Une destination absente convient seulement à un mandat sans destination."""
    mandat_id = _texte(mandat_id, "mandat_id", 128)
    return _decision(_lire()["mandats"].get(mandat_id), _demande(demande), _maintenant(now))


def reserver(mandat_id: str, operation_id: str, demande: dict, *, now: float | None = None) -> dict:
    """Réserve une action et son coût prévu sous verrou. Rejouer après révocation reste refusé.

    La réservation n'exécute rien. Le futur exécuteur doit encore contrôler la révocation au départ de l'effet
    et rapprocher les opérations déjà parties : aucun appel externe n'est annulé rétroactivement ici.
    """
    mandat_id = _texte(mandat_id, "mandat_id", 128)
    if not isinstance(operation_id, str) or not _OPERATION.fullmatch(operation_id):
        raise MandatError("operation_id : identifiant stable de 1 à 128 caractères attendu")
    demande, now = _demande(demande), _maintenant(now)
    empreinte = _empreinte(demande)

    def prendre(data):
        m = data["mandats"].get(mandat_id)
        precedent = data["operations"].get(operation_id)
        decision = _decision(m, demande, now, quotas=precedent is None)
        decision["operation_id"] = operation_id
        if not decision["admis"]:
            return decision
        if precedent is not None:
            if precedent["mandat_id"] != mandat_id or precedent["empreinte"] != empreinte:
                decision.update(admis=False, raison="operation_id déjà réservé avec un autre mandat ou d'autres paramètres")
                return decision
            decision.update(reservee=True, doublon=True, raison="réservation existante, quotas inchangés")
            return decision
        data["operations"][operation_id] = {"mandat_id": mandat_id, "empreinte": empreinte,
                                            "demande": demande, "created_at": now}
        m["used_actions"] += 1
        m["used_cost_cents"] += demande["cost_cents"]
        decision.update(reservee=True, raison="réservation enregistrée",
                        remaining_actions=m["max_actions"] - m["used_actions"],
                        remaining_cost_cents=m["max_cost_cents"] - m["used_cost_cents"])
        return decision

    return _modifier(prendre)
