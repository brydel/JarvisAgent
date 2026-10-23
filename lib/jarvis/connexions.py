"""Connexions MCP Streamable HTTP : secrets par référence et découverte réellement exécutée.

Le registre ne contient aucune valeur de credential. Une découverte ne lance aucun outil. Les appels
d'outils passent exclusivement par la passerelle et son mandat. Les droits restent des noms exacts.
"""

from __future__ import annotations

import copy
import json
import os
import re
import time
from urllib.parse import urlsplit

from . import outils_http, store

_IDENT = re.compile(r"[a-z][a-z0-9_-]{0,39}\Z")
_OUTIL = re.compile(r"[A-Za-z_][A-Za-z0-9_.-]{0,63}\Z")
_ENV = re.compile(r"[A-Z_][A-Z0-9_]{0,99}\Z")
_PROTOCOLES = {"2025-03-26", "2025-06-18", "2025-11-25"}


class ConnexionError(ValueError):
    pass


def _base():
    # La première ouverture WAL peut échouer entre deux nouveaux threads même avec busy_timeout.
    # Une transaction déjà ouverte ne prend pas ce verrou (ordre SQL -> fichier interdit).
    if getattr(store._local, "profondeur", 0) > 0:
        return store.connexion()
    with store.locked("os_sqlite_initialisation"):
        return store.connexion()


def _db():
    c = _base()
    c.execute("CREATE TABLE IF NOT EXISTS os_connexions (id TEXT PRIMARY KEY, spec TEXT NOT NULL, "
              "active INTEGER NOT NULL, created_at REAL NOT NULL, created_by TEXT NOT NULL, "
              "discovery TEXT, verified_at REAL)")
    return c


def _texte(v, champ, maximum=200):
    if not isinstance(v, str) or not v.strip() or len(v) > maximum or any(ord(x) < 32 for x in v):
        raise ConnexionError(f"{champ} : texte non vide de {maximum} caractères au plus attendu.")
    return v.strip()


def _spec(spec):
    base = {"id", "nom", "type", "outils_autorises"}
    if not isinstance(spec, dict) or not base <= set(spec):
        raise ConnexionError("Connexion : id, nom, type et outils_autorises requis.")
    if not isinstance(spec["id"], str) or not _IDENT.fullmatch(spec["id"]):
        raise ConnexionError("Identifiant de connexion invalide.")
    tools = spec["outils_autorises"]
    if (not isinstance(tools, list) or len(tools) > 128 or any(not isinstance(t, str) or not _OUTIL.fullmatch(t) for t in tools)
            or len(tools) != len(set(tools))):
        raise ConnexionError("outils_autorises : liste de noms exacts distincts requise.")
    resultat = {"id": spec["id"], "nom": _texte(spec["nom"], "nom"), "type": spec["type"], "outils_autorises": sorted(tools)}
    if spec["type"] == "mcp_stdio":
        from . import mcp_stdio
        requis = base | {"command", "args", "env_allowlist"}
        if not requis <= set(spec) <= requis | {"cwd"}:
            raise ConnexionError("Connexion stdio : commande absolue, arguments et noms de variables requis.")
        return resultat | mcp_stdio.valider_configuration({k: spec[k] for k in spec if k not in base}, verifier_fichiers=False)
    if spec["type"] != "mcp_http" or not base | {"url"} <= set(spec) <= base | {"url", "token_env"}:
        raise ConnexionError("Connexion MCP HTTP ou stdio attendue, avec leurs seuls champs de configuration.")
    outils_http.cible(spec["url"])
    if urlsplit(spec["url"]).query:
        raise ConnexionError("La connexion MCP ne doit pas contenir de paramètres d'URL.")
    ref = spec.get("token_env", "")
    if not isinstance(ref, str) or (ref and not _ENV.fullmatch(ref)):
        raise ConnexionError("token_env doit nommer une variable d'environnement, jamais sa valeur.")
    return resultat | {"url": spec["url"], "token_env": ref}


def _configuration(ident):
    if not isinstance(ident, str) or not _IDENT.fullmatch(ident):
        raise ConnexionError("Identifiant de connexion invalide.")
    row = _db().execute("SELECT spec,active,created_at,created_by,discovery,verified_at FROM os_connexions WHERE id=?", (ident,)).fetchone()
    if row is None:
        raise ConnexionError("Connexion inconnue.")
    try:
        spec = _spec(json.loads(row[0]))
        discovery = json.loads(row[4]) if row[4] else []
        if not isinstance(discovery, list):
            raise ValueError
        for tool in discovery:
            if (not isinstance(tool, dict) or set(tool) != {"name", "description", "inputSchema", "autorise"}
                    or not isinstance(tool["name"], str) or not _OUTIL.fullmatch(tool["name"])
                    or not isinstance(tool["description"], str) or not isinstance(tool["inputSchema"], dict)
                    or type(tool["autorise"]) is not bool
                    or tool["autorise"] != (tool["name"] in spec["outils_autorises"])):
                raise ValueError
    except (ValueError, TypeError) as exc:
        raise ConnexionError("Registre des connexions invalide ; aucun appel autorisé.") from exc
    return {**spec, "active": bool(row[1]), "created_at": row[2], "created_by": row[3],
            "outils": discovery, "verified_at": row[5]}


def _public(config):
    if config["type"] == "mcp_stdio":
        from . import mcp_stdio
        return {k: copy.deepcopy(config[k]) for k in ("id", "nom", "type", "active", "created_at", "outils_autorises", "verified_at", "outils")} | {
            "hote": "mcp:" + config["id"], "auth": {"mode": "processus_local", "configuree": True},
            "etat": "revoquee" if not config["active"] else "decouverte_verifiee" if config["verified_at"] else "configuree_non_verifiee",
            "stdio": mcp_stdio.metadata(_spec_stdio(config))}
    ref = config["token_env"]
    return {k: copy.deepcopy(config[k]) for k in ("id", "nom", "type", "active", "created_at", "outils_autorises", "verified_at")} | {
        "hote": outils_http.cible(config["url"])[0],
        "auth": {"mode": "bearer_env" if ref else "aucune", "configuree": bool(os.environ.get(ref)) if ref else True},
        "outils": copy.deepcopy(config["outils"]),
        "etat": "revoquee" if not config["active"] else ("decouverte_verifiee" if config["verified_at"] else "configuree_non_verifiee")}


def enregistrer(spec: dict, *, par: str) -> dict:
    """L'appelant doit authentifier le propriétaire. Un identifiant existant est immuable."""
    spec, par = _spec(spec), _texte(par, "par")
    if spec["type"] == "mcp_stdio":
        from . import mcp_stdio
        mcp_stdio.valider_configuration(_spec_stdio(spec))
    _db()
    with store.transaction() as c:
        if c.execute("SELECT 1 FROM os_connexions WHERE id=?", (spec["id"],)).fetchone():
            raise ConnexionError("Identifiant déjà utilisé ; révoquer puis choisir un nouvel identifiant.")
        c.execute("INSERT INTO os_connexions(id,spec,active,created_at,created_by) VALUES(?,?,1,?,?)",
                  (spec["id"], json.dumps(spec, ensure_ascii=False), time.time(), par))
    return get(spec["id"])


def lister() -> list[dict]:
    return [get(row[0]) for row in _db().execute("SELECT id FROM os_connexions ORDER BY created_at,id").fetchall()]


def get(ident: str) -> dict:
    return _public(_configuration(ident))


def _spec_stdio(config):
    return {k: config[k] for k in ("command", "args", "env_allowlist", "cwd") if k in config}


def revoquer(ident: str, *, par: str) -> dict:
    _texte(par, "par")
    _configuration(ident)
    with store.transaction() as c:
        c.execute("UPDATE os_connexions SET active=0 WHERE id=?", (ident,))
    return get(ident)


def configurer_outils(ident: str, noms: list[str], *, par: str) -> dict:
    """Sélection propriétaire parmi les outils découverts ; le mandat reste exigé pour tout appel."""
    _texte(par, "par")
    _db()
    with store.transaction() as c:
        config = _configuration(ident)
        if not config["active"]:
            raise ConnexionError("Connexion révoquée.")
        known = {t["name"] for t in config["outils"]}
        if (not isinstance(noms, list) or any(not isinstance(n, str) or n not in known for n in noms)
                or len(noms) != len(set(noms))):
            raise ConnexionError("Sélectionner uniquement des noms exacts déjà découverts, sans doublon.")
        noms_spec = ("id", "nom", "type", "url", "token_env", "outils_autorises", "command", "args", "env_allowlist", "cwd")
        spec = _spec({k: config[k] for k in noms_spec if k in config})
        spec["outils_autorises"] = sorted(noms)
        discovery = [{**t, "autorise": t["name"] in noms} for t in config["outils"]]
        c.execute("UPDATE os_connexions SET spec=?,discovery=? WHERE id=?", (json.dumps(spec, ensure_ascii=False), json.dumps(discovery, ensure_ascii=False), ident))
    return get(ident)


def _masquer(v, secret):
    if isinstance(v, str):
        return v.replace(secret, "[SECRET]") if secret else v
    if isinstance(v, dict):
        return {(str(k).replace(secret, "[SECRET]") if secret else str(k)): _masquer(x, secret) for k, x in v.items()}
    if isinstance(v, list):
        return [_masquer(x, secret) for x in v]
    return v


class _Client:
    def __init__(self, config, *, annulation=None):
        if not config["active"]:
            raise ConnexionError("Connexion révoquée.")
        self.config, self.session, self.protocole = config, "", ""
        self.secret = os.environ.get(config["token_env"], "") if config["token_env"] else ""
        if config["token_env"] and not self.secret:
            raise ConnexionError("Credential référencé absent de l'environnement.")
        if any(c in self.secret for c in "\r\n"):
            raise ConnexionError("Credential référencé invalide.")
        self.numero = 0
        self.echeance = time.monotonic() + 20
        self.annulation = annulation

    def _envoyer(self, message, notification=False):
        headers = {"Accept": "application/json, text/event-stream"}
        if self.secret:
            headers["Authorization"] = "Bearer " + self.secret
        if self.session:
            headers["Mcp-Session-Id"] = self.session
        if self.protocole:
            headers["MCP-Protocol-Version"] = self.protocole
        # Chaque POST recontrôle la révocation et résout/épingle sa destination à nouveau.
        actuelle = _configuration(self.config["id"])
        if not actuelle["active"]:
            raise ConnexionError("Connexion révoquée.")
        if message.get("method") == "tools/call":
            nom = (message.get("params") or {}).get("name")
            if nom not in actuelle["outils_autorises"] or not any(t["name"] == nom for t in actuelle["outils"]):
                raise ConnexionError("Outil retiré du périmètre de connexion avant l'appel.")
        restant = self.echeance - time.monotonic()
        if restant <= 0:
            raise ConnexionError("Délai total de session MCP dépassé.")
        response = outils_http.requete(self.config["url"], methode="POST", donnees=message, entetes=headers,
                                      timeout=min(10, restant), attendre_rpc_id=message.get("id"), annulation=self.annulation)
        if notification and response["status"] in (200, 202, 204):
            return None
        if response["status"] != 200:
            raise ConnexionError("Le serveur MCP a refusé la requête.")
        session = response["entetes"].get("mcp-session-id", "")
        if session:
            if len(session) > 200 or any(not c.isprintable() for c in session):
                raise ConnexionError("Session MCP invalide.")
            self.session = session
        try:
            text = response["contenu"].decode("utf-8")
            content_type = response["entetes"].get("content-type", "").split(";", 1)[0].strip()
            if content_type == "text/event-stream":
                candidats, parts = [], []
                for line in (text + "\n\n").splitlines():
                    if line.startswith("data:"):
                        parts.append(line[5:].lstrip(" "))
                    elif not line and parts:
                        candidats.append(json.loads("\n".join(parts))); parts = []
            elif content_type == "application/json":
                candidats = [json.loads(text)]
            else:
                raise ValueError
            matches = [x for x in candidats if isinstance(x, dict) and x.get("jsonrpc") == "2.0"
                       and type(x.get("id")) is int and x["id"] == message["id"]]
            if len(matches) != 1 or "error" in matches[0] or "result" not in matches[0]:
                raise ValueError
            return _masquer(matches[0]["result"], self.secret)
        except (ValueError, UnicodeError, KeyError, RecursionError) as exc:
            raise ConnexionError("Réponse MCP invalide ou erreur du fournisseur.") from exc

    def appel(self, methode, params=None):
        self.numero += 1
        message = {"jsonrpc": "2.0", "id": self.numero, "method": methode}
        if params is not None:
            message["params"] = params
        return self._envoyer(message)

    def initialiser(self):
        result = self.appel("initialize", {"protocolVersion": "2025-03-26", "capabilities": {},
                            "clientInfo": {"name": "JarvisOS", "version": "1"}})
        if not isinstance(result, dict) or result.get("protocolVersion") not in _PROTOCOLES:
            raise ConnexionError("Version MCP négociée non prise en charge.")
        self.protocole = result["protocolVersion"]
        self._envoyer({"jsonrpc": "2.0", "method": "notifications/initialized"}, notification=True)


def decouvrir(ident: str, *, annulation=None) -> dict:
    """Initialise une session MCP puis parcourt tools/list ; aucun outil n'est invoqué."""
    config = _configuration(ident)
    if config["type"] == "mcp_stdio":
        from . import mcp_stdio
        def verifier():
            if not _configuration(ident)["active"]:
                raise ConnexionError("Connexion révoquée.")
        return _sauver_stdio(ident, mcp_stdio.decouvrir(_spec_stdio(config), verifier=verifier, annulation=annulation))
    client = _Client(config, annulation=annulation)
    client.initialiser()
    outils, cursor, vus = [], None, set()
    for _ in range(10):
        result = client.appel("tools/list", {"cursor": cursor} if cursor else {})
        if not isinstance(result, dict) or not isinstance(result.get("tools"), list):
            raise ConnexionError("Catalogue MCP invalide.")
        for tool in result["tools"]:
            if (not isinstance(tool, dict) or not isinstance(tool.get("name"), str)
                    or not _OUTIL.fullmatch(tool["name"]) or tool["name"] in vus
                    or not isinstance(tool.get("inputSchema"), dict)):
                raise ConnexionError("Outil MCP invalide ou dupliqué.")
            schema = tool["inputSchema"]
            if len(json.dumps(schema, allow_nan=False)) > 32_000:
                raise ConnexionError("Schéma d'outil MCP trop volumineux.")
            vus.add(tool["name"])
            outils.append({"name": tool["name"], "description": str(tool.get("description", ""))[:4000],
                           "inputSchema": schema, "autorise": tool["name"] in config["outils_autorises"]})
            if len(outils) > 128:
                raise ConnexionError("Catalogue MCP trop volumineux.")
        cursor = result.get("nextCursor")
        if not cursor:
            break
        if not isinstance(cursor, str) or len(cursor) > 2000:
            raise ConnexionError("Pagination MCP invalide.")
    else:
        raise ConnexionError("Pagination MCP trop longue.")
    with store.transaction() as c:
        actuelle = _configuration(ident)
        if not actuelle["active"]:
            raise ConnexionError("Connexion révoquée pendant la découverte.")
        outils = [{**tool, "autorise": tool["name"] in actuelle["outils_autorises"]} for tool in outils]
        c.execute("UPDATE os_connexions SET discovery=?,verified_at=? WHERE id=?", (json.dumps(outils, ensure_ascii=False, allow_nan=False), time.time(), ident))
    return get(ident)


def _sauver_stdio(ident, liste):
    if not isinstance(liste, list) or len(liste) > 128:
        raise ConnexionError("Catalogue MCP invalide ou trop volumineux.")
    outils, vus = [], set()
    for outil in liste:
        if (not isinstance(outil, dict) or not isinstance(outil.get("name"), str) or not _OUTIL.fullmatch(outil["name"])
                or outil["name"] in vus or not isinstance(outil.get("inputSchema"), dict)):
            raise ConnexionError("Outil MCP invalide ou dupliqué.")
        if len(json.dumps(outil["inputSchema"], allow_nan=False)) > 32000:
            raise ConnexionError("Schéma MCP trop volumineux.")
        vus.add(outil["name"])
        outils.append({"name": outil["name"], "description": str(outil.get("description", ""))[:4000],
                       "inputSchema": outil["inputSchema"]})
    with store.transaction() as c:
        config = _configuration(ident)
        if not config["active"]:
            raise ConnexionError("Connexion révoquée pendant la découverte.")
        outils = [{**o, "autorise": o["name"] in config["outils_autorises"]} for o in outils]
        c.execute("UPDATE os_connexions SET discovery=?,verified_at=? WHERE id=?",
                  (json.dumps(outils, allow_nan=False, ensure_ascii=False), time.time(), ident))
    return get(ident)


def _appeler(ident: str, nom: str, arguments: dict, *, avant_effet=None, annulation=None) -> dict:
    config = _configuration(ident)
    decouvert = {t["name"] for t in config["outils"]}
    if nom not in config["outils_autorises"] or nom not in decouvert:
        raise ConnexionError("Outil MCP absent du catalogue vérifié ou hors périmètre de connexion.")
    if config["type"] == "mcp_stdio":
        from . import mcp_stdio
        def verifier():
            actuelle = _configuration(ident)
            if (not actuelle["active"] or nom not in actuelle["outils_autorises"]
                    or not any(o["name"] == nom for o in actuelle["outils"])):
                raise ConnexionError("Connexion ou outil local révoqué avant l'appel.")
        result = mcp_stdio.appeler(_spec_stdio(config), nom, arguments, verifier=verifier,
                                   avant_effet=avant_effet, annulation=annulation)
        if not isinstance(result, dict) or not isinstance(result.get("content", []), list):
            raise ConnexionError("Résultat d'outil MCP invalide.")
        return result
    client = _Client(config, annulation=annulation)
    client.initialiser()
    if avant_effet is not None:
        avant_effet()
    result = client.appel("tools/call", {"name": nom, "arguments": arguments})
    if not isinstance(result, dict) or not isinstance(result.get("content", []), list):
        raise ConnexionError("Résultat d'outil MCP invalide.")
    return result
