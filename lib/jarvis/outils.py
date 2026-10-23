"""Passerelle d'outils sous mandat, journal d'opérations et absence de reprise aveugle.

Une opération prépare son identité avant la réservation, puis marque le départ avant le réseau. Après
un crash dans cette fenêtre, la reprise rend ``unknown`` et demande un rapprochement : elle ne rejoue
jamais une écriture. Les quotas réservés restent consommés. Aucune transaction SQL ne couvre le réseau.
"""

from __future__ import annotations

import hashlib
import json
import re
import time

from . import connexions, mandats, outils_http, store
from .annulation import ExecutionAnnulee

_OPERATION = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:/-]{0,127}\Z")
_REQUIS = {"operation_id", "mandat_id", "project", "tool", "arguments"}


class OutilError(ValueError):
    pass


def _db():
    c = connexions._base()
    c.execute("CREATE TABLE IF NOT EXISTS os_operations_outils (operation_id TEXT PRIMARY KEY, "
              "empreinte TEXT NOT NULL, project TEXT NOT NULL, tool TEXT NOT NULL, mandat_id TEXT NOT NULL, "
              "acteur TEXT NOT NULL, status TEXT NOT NULL, created_at REAL NOT NULL, updated_at REAL NOT NULL, "
              "resultat TEXT, erreur TEXT)")
    return c


def _texte(v, champ, maximum=200):
    if not isinstance(v, str) or not v.strip() or len(v) > maximum or any(ord(x) < 32 for x in v):
        raise OutilError(f"{champ} : texte non vide de {maximum} caractères au plus attendu.")
    return v.strip()


def catalogue() -> dict:
    """Catalogue local ; aucune connexion ni découverte réseau implicite."""
    tools = [{"id": "web.fetch", "nom": "Lire une page HTTPS", "effet": "lecture", "disponible": True,
              "inputSchema": {"type": "object", "properties": {"url": {"type": "string"},
                    "maximum": {"type": "integer", "minimum": 1, "maximum": 250000},
                    "timeout": {"type": "number", "minimum": 1, "maximum": 10}},
                    "required": ["url"], "additionalProperties": False}}]
    for connection in connexions.lister():
        for tool in connection["outils"]:
            if tool["autorise"]:
                tools.append({"id": f"mcp.{connection['id']}.{tool['name']}", "nom": tool["name"],
                              "description": tool["description"], "connexion_id": connection["id"],
                              "effet": "potentiellement_ecriture", "disponible": connection["active"] and connection["auth"]["configuree"]
                                and connection.get("stdio", {}).get("disponible", True),
                              "inputSchema": tool["inputSchema"]})
    from . import courriel
    tools.extend(courriel.catalogue())
    from . import outils_communaute
    tools.extend(outils_communaute.catalogue())
    return {"version": 1, "outils": tools, "note": "Un outil disponible exige encore un mandat et un périmètre exacts."}


def _normaliser(requete):
    if not isinstance(requete, dict) or not _REQUIS <= set(requete) <= _REQUIS | {"cost_cents"}:
        raise OutilError("operation_id, mandat_id, project, tool et arguments requis ; cost_cents facultatif.")
    if not isinstance(requete["operation_id"], str) or not _OPERATION.fullmatch(requete["operation_id"]):
        raise OutilError("operation_id invalide.")
    if not isinstance(requete["arguments"], dict):
        raise OutilError("arguments doit être un objet JSON.")
    cost = requete.get("cost_cents", 0)
    if type(cost) is not int or not 0 <= cost <= 2 ** 53 - 1:
        raise OutilError("cost_cents doit être un entier positif ou nul.")
    normalized = {"operation_id": requete["operation_id"], "mandat_id": _texte(requete["mandat_id"], "mandat_id", 128),
                  "project": _texte(requete["project"], "project"), "tool": _texte(requete["tool"], "tool", 128),
                  "arguments": requete["arguments"], "cost_cents": cost}
    try:
        encoded = json.dumps(normalized, allow_nan=False, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError, RecursionError) as exc:
        raise OutilError("Requête JSON invalide.") from exc
    if len(encoded.encode()) > 128000:
        raise OutilError("Requête trop volumineuse.")
    # La copie JSON empêche une mutation des arguments pendant une exécution concurrente.
    return json.loads(encoded), hashlib.sha256(encoded.encode()).hexdigest()


def _valider_schema(valeur, schema, profondeur=0):
    """Sous-ensemble JSON Schema explicite ; une contrainte inconnue est refusée avant le départ.

    Le fournisseur conserve sa validation complète. Aucun $ref distant ni expression régulière provenant
    d'un serveur n'est évalué localement. Cette première version favorise les schémas d'outils simples.
    """
    if profondeur > 20 or schema is False:
        raise OutilError("Arguments MCP refusés par le schéma ou profondeur excessive.")
    if schema is True:
        return
    annotations = {"title", "description", "default", "examples", "$schema", "$id", "$comment", "deprecated", "readOnly", "writeOnly"}
    supportes = {"type", "properties", "required", "additionalProperties", "items", "enum", "const",
                 "minimum", "maximum", "minLength", "maxLength", "minItems", "maxItems"}
    if not isinstance(schema, dict) or set(schema) - annotations - supportes:
        raise OutilError("Schéma MCP hors du sous-ensemble pris en charge ; appel refusé.")
    typ = schema.get("type")
    tests = {"object": lambda v: isinstance(v, dict), "array": lambda v: isinstance(v, list),
             "string": lambda v: isinstance(v, str), "integer": lambda v: type(v) is int,
             "number": lambda v: type(v) in (int, float), "boolean": lambda v: type(v) is bool,
             "null": lambda v: v is None}
    if typ is not None:
        types = typ if isinstance(typ, list) else [typ]
        if not types or any(not isinstance(t, str) or t not in tests for t in types) or not any(tests[t](valeur) for t in types):
            raise OutilError("Type d'argument MCP différent du schéma.")
    encode = lambda v: json.dumps(v, sort_keys=True, allow_nan=False, ensure_ascii=False)
    if "const" in schema and encode(valeur) != encode(schema["const"]):
        raise OutilError("Constante d'argument MCP différente du schéma.")
    if "enum" in schema:
        if not isinstance(schema["enum"], list) or encode(valeur) not in [encode(v) for v in schema["enum"]]:
            raise OutilError("Valeur d'argument MCP hors énumération.")
    if isinstance(valeur, dict):
        props, required = schema.get("properties", {}), schema.get("required", [])
        if not isinstance(props, dict) or not isinstance(required, list) or any(not isinstance(k, str) for k in required):
            raise OutilError("Schéma objet MCP invalide.")
        if any(k not in valeur for k in required):
            raise OutilError("Argument MCP obligatoire manquant.")
        for key, val in valeur.items():
            _valider_schema(val, props.get(key, schema.get("additionalProperties", True)), profondeur + 1)
    if isinstance(valeur, list):
        for val in valeur:
            _valider_schema(val, schema.get("items", True), profondeur + 1)
    if isinstance(valeur, (str, list)):
        prefix = "Length" if isinstance(valeur, str) else "Items"
        for name, comparer in (("min" + prefix, lambda a, b: a < b), ("max" + prefix, lambda a, b: a > b)):
            if name in schema and (type(schema[name]) is not int or schema[name] < 0 or comparer(len(valeur), schema[name])):
                raise OutilError("Taille d'argument MCP hors schéma.")
    if type(valeur) in (int, float):
        for name, comparer in (("minimum", lambda a, b: a < b), ("maximum", lambda a, b: a > b)):
            if name in schema and (type(schema[name]) not in (int, float) or comparer(valeur, schema[name])):
                raise OutilError("Valeur numérique MCP hors schéma.")


def _preparer(requete, *, annulation=None, par=""):
    tool, args = requete["tool"], requete["arguments"]
    if tool == "web.fetch":
        if not {"url"} <= set(args) <= {"url", "maximum", "timeout"}:
            raise OutilError("web.fetch : url requise ; maximum et timeout facultatifs.")
        host = outils_http.cible(args["url"])[0]
        maximum, timeout = args.get("maximum", 64000), args.get("timeout", 10)
        if type(maximum) is not int or not 1 <= maximum <= 250000 or type(timeout) not in (int, float) or not 1 <= timeout <= 10:
            raise OutilError("web.fetch : limites de taille ou de délai invalides.")

        def appel(verifier):
            verifier()
            response = outils_http.requete(args["url"], timeout=timeout, maximum=maximum, annulation=annulation)
            if not 200 <= response["status"] < 300:
                raise OutilError("La destination HTTPS a renvoyé une erreur.")
            content_type = response["entetes"].get("content-type", "application/octet-stream").split(";", 1)[0].strip()
            if not (content_type.startswith("text/") or content_type in {"application/json", "application/xml", "application/xhtml+xml"}):
                raise OutilError("Type de contenu non textuel refusé.")
            return {"status_http": response["status"], "hote": host, "content_type": content_type,
                    "contenu": response["contenu"].decode("utf-8", errors="replace"),
                    "taille_octets": len(response["contenu"]), "source_non_fiable": True}
        return host, False, appel
    if tool.startswith("mcp."):
        try:
            _, ident, nom = tool.split(".", 2)
        except ValueError as exc:
            raise OutilError("Identifiant d'outil MCP invalide.") from exc
        connection = connexions.get(ident)
        if (not connection["active"] or not connection["auth"]["configuree"]
                or nom not in connection["outils_autorises"]
                or not any(t["name"] == nom for t in connection["outils"])):
            raise OutilError("Connexion ou outil MCP indisponible, révoqué ou non autorisé.")
        descriptor = next(t for t in connection["outils"] if t["name"] == nom)
        _valider_schema(args, descriptor["inputSchema"])
        return connection["hote"], True, lambda verifier: connexions._appeler(ident, nom, args, avant_effet=verifier, annulation=annulation)
    if tool.startswith("courriel."):
        from . import courriel
        return courriel.preparer(tool, args, requete["operation_id"], annulation=annulation)
    if tool.startswith("communaute."):
        from . import outils_communaute
        return outils_communaute.preparer(tool, args, requete["operation_id"], par=par)
    raise OutilError("Outil inconnu ; aucune capacité n'est déduite de son nom.")


def _record(row):
    if row is None:
        return None
    return {"operation_id": row[0], "project": row[1], "tool": row[2], "mandat_id": row[3], "acteur": row[4],
            "status": row[5], "created_at": row[6], "updated_at": row[7],
            "resultat": json.loads(row[8]) if row[8] else None, "erreur": row[9], "doublon": False}


_SELECT = "SELECT operation_id,project,tool,mandat_id,acteur,status,created_at,updated_at,resultat,erreur FROM os_operations_outils"


def operation(ident: str) -> dict | None:
    if not isinstance(ident, str) or not _OPERATION.fullmatch(ident):
        raise OutilError("operation_id invalide.")
    return _record(_db().execute(_SELECT + " WHERE operation_id=?", (ident,)).fetchone())


def operations(project: str | None = None, *, limite: int = 100) -> list[dict]:
    if type(limite) is not int or not 1 <= limite <= 200:
        raise OutilError("limite doit être entre 1 et 200.")
    params = []
    sql = _SELECT
    if project is not None:
        sql += " WHERE project=?"; params.append(_texte(project, "project"))
    return [_record(row) for row in _db().execute(sql + " ORDER BY created_at DESC,operation_id LIMIT ?", (*params, limite)).fetchall()]


def _terminer(ident, status, *, resultat=None, erreur=None):
    data = None if resultat is None else json.dumps(resultat, ensure_ascii=False, allow_nan=False)
    with store.transaction() as c:
        c.execute("UPDATE os_operations_outils SET status=?,updated_at=?,resultat=?,erreur=? WHERE operation_id=?",
                  (status, time.time(), data, erreur, ident))


def executer(requete: dict, *, par: str, annulation=None) -> dict:
    """Appelle une fois un outil contrôlé. Le contrôleur fournit l'acteur authentifié.

    Le coût est une réservation prévisionnelle, pas une preuve de facturation fournisseur. La passerelle
    bloque la reprise d'un départ incertain et n'accorde aucun outil à partir d'un texte de prompt.
    """
    if annulation is not None:
        annulation.verifier()
    req, empreinte = _normaliser(requete)
    par = _texte(par, "par")
    ident = req["operation_id"]
    _db()
    # Le verrou de fichier survit aux transactions et est libéré par le noyau après un crash.
    # Il empêche deux départs concurrents, y compris lorsque le registre des mandats est en JSON.
    with store.locked("outils/" + hashlib.sha256(ident.encode()).hexdigest()):
        old = _db().execute("SELECT empreinte,status FROM os_operations_outils WHERE operation_id=?", (ident,)).fetchone()
        if old:
            if old[0] != empreinte:
                raise OutilError("operation_id déjà utilisé avec d'autres paramètres.")
            if old[1] == "in_progress":
                _terminer(ident, "unknown", erreur="Départ précédent sans reçu durable ; rapprochement requis, aucun rejeu.")
            if old[1] != "prepared":
                return {**operation(ident), "doublon": True}
        # Valider le catalogue et la destination avant toute consommation de quota.
        try:
            destination, ecriture, appel = _preparer(req, annulation=annulation, par=par)
        except (ValueError, OSError) as exc:
            raise OutilError("Outil ou paramètres indisponibles ; aucun appel effectué.") from exc
        if old is None:
            now = time.time()
            with store.transaction() as c:
                c.execute("INSERT INTO os_operations_outils(operation_id,empreinte,project,tool,mandat_id,acteur,status,created_at,updated_at) "
                          "VALUES(?,?,?,?,?,?,'prepared',?,?)", (ident, empreinte, req["project"], req["tool"], req["mandat_id"], par, now, now))
        demande = {"project": req["project"], "tool": req["tool"], "destination": destination, "cost_cents": req["cost_cents"]}
        try:
            if annulation is not None:
                annulation.verifier()
            decision = mandats.reserver(req["mandat_id"], ident, demande)
            if not decision["admis"]:
                raise OutilError("Mandat refusé : " + decision["raison"])
            # Recontrôle après la réservation ; son rejeu vérifie expiration/révocation sans consommer plus.
            if not mandats.reserver(req["mandat_id"], ident, demande)["admis"]:
                raise OutilError("Mandat révoqué ou expiré avant le départ.")
        except ValueError as exc:
            _terminer(ident, "failed", erreur="Mandat refusé ; aucun appel effectué.")
            raise OutilError("Mandat refusé ; aucun appel effectué.") from exc
        _terminer(ident, "in_progress")
        def verifier():
            if annulation is not None:
                annulation.verifier()
            if not mandats.reserver(req["mandat_id"], ident, demande)["admis"]:
                raise OutilError("Mandat révoqué ou expiré avant l'effet.")

        try:
            resultat = appel(verifier)
            if isinstance(resultat, dict) and resultat.get("isError") is True:
                _terminer(ident, "unknown" if ecriture else "failed", resultat=resultat,
                          erreur="L'outil signale une erreur ; effet partiel possible, rapprochement requis." if ecriture else "L'outil signale une erreur.")
            else:
                _terminer(ident, "succeeded", resultat=resultat)
        except (ValueError, OSError, TimeoutError, ExecutionAnnulee) as exc:
            # Une erreur MCP peut être survenue après l'effet distant. Ne pas divulguer le texte du
            # fournisseur, une URL complète ou un credential via la réponse de contrôle.
            _terminer(ident, "unknown" if ecriture else "failed",
                      erreur="Résultat externe incertain ; aucun rejeu automatique." if ecriture else "Lecture HTTPS impossible ou réponse refusée.")
        return operation(ident)
