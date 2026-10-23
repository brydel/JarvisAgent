"""OAuth Google PKCE : jetons privés, état unique et révocation locale immédiate.

Le contrôleur authentifie le propriétaire avant configuration/lancement/révocation. Le callback est lié
à ce lancement par un état imprévisible et un vérificateur PKCE privé ; il n'accepte aucune configuration.
Le coffre local est protégé par les permissions Linux, sans prétendre isoler deux agents du même utilisateur.
"""
from __future__ import annotations

import base64
import hashlib
import json
import math
import os
import re
import secrets
import stat
import tempfile
import time
from pathlib import Path
from urllib.parse import urlencode, urlsplit

from . import config, mandats, outils_http, store
from .annulation import ExecutionAnnulee

SCOPES = {
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.send",
}
_ID = re.compile(r"[a-z][a-z0-9_-]{0,39}\Z")
_ENV = re.compile(r"[A-Z_][A-Z0-9_]{0,99}\Z")
_TOKEN_URL = "https://oauth2.googleapis.com/token"
_REVOKE_URL = "https://oauth2.googleapis.com/revoke"
_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_VERROU = "oauth_coffre"


class OAuthError(ValueError):
    """Erreur publique ; aucun code, état, jeton ou détail fournisseur n'est cité."""


class CoffreError(OAuthError):
    """Coffre indisponible ou altéré ; ne pas confondre avec une erreur de formulaire."""


def _texte(v, champ, maximum=200):
    if not isinstance(v, str) or not v.strip() or len(v) > maximum or any(ord(c) < 32 or ord(c) == 127 for c in v):
        raise OAuthError(f"{champ} : texte non vide sans caractères de contrôle attendu.")
    return v.strip()


def _date(v):
    if type(v) not in (int, float) or not math.isfinite(v) or v < 0:
        raise OAuthError("Date OAuth invalide.")
    return float(v)


def _ident(v):
    if not isinstance(v, str) or not _ID.fullmatch(v):
        raise OAuthError("Identifiant OAuth invalide.")
    return v


def _spec(v):
    requis = {"id", "nom", "provider", "client_id", "redirect_uri", "scopes"}
    if not isinstance(v, dict) or not requis <= set(v) <= requis | {"client_secret_env", "adresse_expediteur"}:
        raise OAuthError("Configuration OAuth : id, nom, provider, client_id, redirect_uri et scopes requis.")
    if v["provider"] != "google_gmail":
        raise OAuthError("Seul le fournisseur google_gmail est pris en charge.")
    scopes = v["scopes"]
    if (not isinstance(scopes, list) or not scopes or any(not isinstance(s, str) or s not in SCOPES for s in scopes)
            or len(set(scopes)) != len(scopes)):
        raise OAuthError("Scopes Gmail exacts et distincts requis.")
    ref = v.get("client_secret_env", "")
    if not isinstance(ref, str) or (ref and not _ENV.fullmatch(ref)):
        raise OAuthError("client_secret_env doit nommer une variable, jamais contenir un secret.")
    adresse = v.get("adresse_expediteur", "")
    if adresse:
        try:
            adresse = mandats._destination(adresse)
        except ValueError as exc:
            raise OAuthError("adresse_expediteur : adresse courriel unique exacte requise.") from exc
        if "@" not in adresse:
            raise OAuthError("adresse_expediteur : adresse courriel unique exacte requise.")
    elif not isinstance(adresse, str):
        raise OAuthError("adresse_expediteur : texte attendu.")
    redirect = _texte(v["redirect_uri"], "redirect_uri", 300)
    try:
        u = urlsplit(redirect)
        if (u.scheme != "http" or u.hostname not in {"localhost", "127.0.0.1"} or u.username or u.password
                or u.path != "/api/v2/oauth/callback" or u.query or u.fragment or not u.port or not 1 <= u.port <= 65535):
            raise ValueError
    except ValueError as exc:
        raise OAuthError("Retour OAuth HTTP loopback avec port et chemin /api/v2/oauth/callback requis.") from exc
    return {"id": _ident(v["id"]), "nom": _texte(v["nom"], "nom"), "provider": v["provider"],
            "client_id": _texte(v["client_id"], "client_id", 500), "client_secret_env": ref,
            "redirect_uri": redirect, "scopes": sorted(scopes), "adresse_expediteur": adresse}


def _chemin():
    dossier = config.STATE_DIR / "oauth_prive"
    dossier.mkdir(mode=0o700, parents=True, exist_ok=True)
    st = dossier.lstat()
    if not stat.S_ISDIR(st.st_mode) or st.st_mode & 0o077 or st.st_uid != os.getuid():
        raise CoffreError("Coffre OAuth : répertoire privé attendu, état conservé.")
    return dossier / "registre.json"


def _vide():
    return {"version": 1, "connexions": {}, "flux": {}}


def _lire():
    p = _chemin()
    try:
        st = p.lstat()
    except FileNotFoundError:
        return _vide()
    if not stat.S_ISREG(st.st_mode) or st.st_mode & 0o077 or st.st_uid != os.getuid() or st.st_size > 1_000_000:
        raise CoffreError("Coffre OAuth : fichier privé régulier requis, état conservé.")
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if (not isinstance(data, dict) or set(data) != {"version", "connexions", "flux"} or type(data["version"]) is not int
                or data["version"] != 1 or not isinstance(data["connexions"], dict) or not isinstance(data["flux"], dict)):
            raise ValueError
        for ident, record in data["connexions"].items():
            if (not isinstance(record, dict) or set(record) != {"spec", "generation", "active", "cree", "modifie", "par", "tokens", "revocation_distante"}
                    or _spec(record["spec"])["id"] != ident or type(record["generation"]) is not int
                    or record["generation"] < 1 or type(record["active"]) is not bool):
                raise ValueError
            _date(record["cree"]); _date(record["modifie"]); _texte(record["par"], "par")
            if record["revocation_distante"] not in (None, "confirmee", "non_confirmee"):
                raise ValueError
            t = record["tokens"]
            if t is not None:
                if (not isinstance(t, dict) or set(t) != {"access_token", "refresh_token", "expires_at", "scopes"}
                        or not isinstance(t["refresh_token"], str) or not isinstance(t["scopes"], list)
                        or not set(t["scopes"]) <= set(record["spec"]["scopes"])):
                    raise ValueError
                _texte(t["access_token"], "jeton", 16000)
                if t["refresh_token"]:
                    _texte(t["refresh_token"], "jeton", 16000)
                _date(t["expires_at"])
        for cle, flux in data["flux"].items():
            if (not re.fullmatch(r"[a-f0-9]{64}", cle) or not isinstance(flux, dict)
                    or set(flux) != {"id", "generation", "verifier", "expires_at", "used_at", "par"}
                    or flux["id"] not in data["connexions"] or type(flux["generation"]) is not int
                    or not isinstance(flux["verifier"], str) or not re.fullmatch(r"[A-Za-z0-9_-]{43,128}", flux["verifier"])):
                raise ValueError
            _date(flux["expires_at"])
            if flux["used_at"] is not None:
                _date(flux["used_at"])
        return data
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError) as exc:
        raise CoffreError("Coffre OAuth invalide ; aucun jeton utilisé, état conservé.") from exc


def _ecrire(data):
    p = _chemin()
    encoded = json.dumps(data, ensure_ascii=False, allow_nan=False)
    if len(encoded.encode()) > 1_000_000:
        raise CoffreError("Coffre OAuth plein ; aucun écrasement effectué.")
    fd, nom = tempfile.mkstemp(prefix=".registre-", dir=p.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(encoded)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(nom, p)
        d = os.open(p.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(d)
        finally:
            os.close(d)
    finally:
        Path(nom).unlink(missing_ok=True)


def _record(data, ident):
    ident = _ident(ident)
    try:
        return data["connexions"][ident]
    except KeyError as exc:
        raise OAuthError("Connexion OAuth inconnue.") from exc


def _public(r, now=None):
    now = time.time() if now is None else now
    s, t = r["spec"], r["tokens"]
    etat = "revoquee" if not r["active"] else "configuree" if t is None else "connectee" if t["expires_at"] > now else "expiree"
    return {"id": s["id"], "nom": s["nom"], "provider": s["provider"], "scopes": list(s["scopes"]),
            "scopes_accordes": list(t["scopes"]) if t else [], "redirect_uri": s["redirect_uri"],
            "adresse_expediteur": s["adresse_expediteur"],
            "client_id_configure": True, "client_secret_configure": bool(os.environ.get(s["client_secret_env"])) if s["client_secret_env"] else False,
            "etat": etat, "generation": r["generation"], "expires_at": t["expires_at"] if t else None,
            "renouvelable": bool(t and t["refresh_token"]), "actualise_at": r["modifie"],
            "revocation_distante": r["revocation_distante"]}


def configurer(spec: dict, *, par: str):
    spec, par = _spec(spec), _texte(par, "par")
    with store.locked(_VERROU):
        data = _lire()
        if spec["id"] in data["connexions"]:
            raise OAuthError("Identifiant OAuth déjà utilisé ; configuration immuable.")
        if len(data["connexions"]) >= 64:
            raise OAuthError("Nombre maximal de connexions OAuth atteint.")
        now = time.time()
        record = {"spec": spec, "generation": 1, "active": True, "cree": now, "modifie": now,
                  "par": par, "tokens": None, "revocation_distante": None}
        data["connexions"][spec["id"]] = record
        _ecrire(data)
        return _public(record)


def lister():
    with store.locked(_VERROU):
        return [_public(r) for _, r in sorted(_lire()["connexions"].items())]


def etat(ident: str):
    with store.locked(_VERROU):
        return _public(_record(_lire(), ident))


def commencer(ident: str, *, par: str):
    par = _texte(par, "par")
    state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(64)
    now = time.time()
    with store.locked(_VERROU):
        data = _lire(); r = _record(data, ident)
        if r["spec"]["client_secret_env"] and not os.environ.get(r["spec"]["client_secret_env"]):
            raise OAuthError("Le secret client référencé est absent ; aucune connexion lancée.")
        # Un nouveau consentement propriétaire invalide les anciens flux et bloque les outils en attendant.
        r.update(generation=r["generation"] + 1, active=True, tokens=None, modifie=now, par=par, revocation_distante=None)
        data["flux"] = {k: v for k, v in data["flux"].items() if v["expires_at"] > now and v["id"] != ident}
        if len(data["flux"]) >= 128:
            raise OAuthError("Trop de consentements en attente.")
        data["flux"][hashlib.sha256(state.encode()).hexdigest()] = {
            "id": ident, "generation": r["generation"], "verifier": verifier,
            "expires_at": now + 600, "used_at": None, "par": par}
        _ecrire(data)
        spec = r["spec"].copy()
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    params = {"client_id": spec["client_id"], "redirect_uri": spec["redirect_uri"], "response_type": "code",
              "scope": " ".join(spec["scopes"]), "state": state, "code_challenge": challenge,
              "code_challenge_method": "S256", "access_type": "offline", "prompt": "consent",
              "include_granted_scopes": "false"}
    return {"id": ident, "authorization_url": _AUTH_URL + "?" + urlencode(params), "expires_at": now + 600}


def _formulaire(spec, champs):
    ref = spec["client_secret_env"]
    if ref:
        secret = os.environ.get(ref, "")
        if not secret or any(ord(c) < 32 for c in secret):
            raise OAuthError("Secret client référencé absent ou invalide.")
        return {**champs, "client_id": spec["client_id"], "client_secret": secret}
    return {**champs, "client_id": spec["client_id"]}


def _echanger(spec, champs, *, annulation=None, scopes_defaut=None):
    try:
        response = outils_http.requete(_TOKEN_URL, methode="POST", formulaire=_formulaire(spec, champs), timeout=20, maximum=64000,
                                      annulation=annulation)
        if response["status"] != 200:
            raise ValueError
        data = json.loads(response["contenu"])
        if not isinstance(data, dict) or str(data.get("token_type", "")).lower() != "bearer":
            raise ValueError
        access = _texte(data.get("access_token"), "jeton", 16000)
        refresh = data.get("refresh_token", "")
        if not isinstance(refresh, str):
            raise ValueError
        if refresh:
            refresh = _texte(refresh, "jeton", 16000)
        expires = data.get("expires_in")
        if type(expires) not in (int, float) or not math.isfinite(expires) or not 1 <= expires <= 86400:
            raise ValueError
        permis = spec["scopes"] if scopes_defaut is None else scopes_defaut
        scope = data.get("scope", " ".join(permis))
        if not isinstance(scope, str) or not scope.split() or not set(scope.split()) <= set(permis):
            raise ValueError
        return {"access_token": access, "refresh_token": refresh, "expires_at": time.time() + expires,
                "scopes": sorted(set(scope.split()))}
    except (ValueError, OSError, KeyError, TypeError, UnicodeError, RecursionError) as exc:
        raise OAuthError("Échange OAuth refusé ou non confirmé ; relancer le consentement si nécessaire.") from exc


def callback(state: str, code: str, *, annulation=None):
    if not isinstance(state, str) or not re.fullmatch(r"[A-Za-z0-9_-]{43}", state):
        raise OAuthError("Retour OAuth invalide ou expiré.")
    code = _texte(code, "code OAuth", 4096)
    now = time.time(); cle = hashlib.sha256(state.encode()).hexdigest()
    with store.locked(_VERROU):
        data = _lire(); flux = data["flux"].get(cle)
        if not flux or flux["used_at"] is not None or flux["expires_at"] <= now:
            raise OAuthError("Retour OAuth invalide, déjà utilisé ou expiré.")
        r = _record(data, flux["id"])
        if not r["active"] or r["generation"] != flux["generation"]:
            raise OAuthError("Consentement remplacé ou révoqué.")
        flux["used_at"] = now
        _ecrire(data)  # Code à usage unique : ne jamais répéter un échange après un résultat incertain.
        spec, generation, verifier = r["spec"].copy(), r["generation"], flux["verifier"]
    tokens = _echanger(spec, {"code": code, "grant_type": "authorization_code", "redirect_uri": spec["redirect_uri"], "code_verifier": verifier}, annulation=annulation)
    with store.locked(_VERROU):
        data = _lire(); r = _record(data, spec["id"])
        if not r["active"] or r["generation"] != generation:
            raise OAuthError("Consentement remplacé ou révoqué pendant l'échange.")
        r.update(tokens=tokens, modifie=time.time())
        _ecrire(data)
        return _public(r)


def verifier(ident: str, scopes: list[str], *, generation: int | None = None):
    if not isinstance(scopes, list) or any(s not in SCOPES for s in scopes):
        raise OAuthError("Scopes de l'outil OAuth invalides.")
    with store.locked(_VERROU):
        r = _record(_lire(), ident)
        if (not r["active"] or r["tokens"] is None or (generation is not None and r["generation"] != generation)
                or not set(scopes) <= set(r["spec"]["scopes"]) & set(r["tokens"]["scopes"])):
            raise OAuthError("Connexion OAuth inactive, remplacée ou scopes insuffisants.")
        return _public(r)


def jeton_acces(ident: str, scopes: list[str], *, generation: int | None = None, annulation=None) -> str:
    """Réservé au connecteur, jamais aux réponses HTTP ou au contexte du modèle."""
    ident = _ident(ident)
    with store.locked("oauth_refresh_" + ident):
        verifier(ident, scopes, generation=generation)
        with store.locked(_VERROU):
            r = _record(_lire(), ident); t = r["tokens"].copy()
            spec, epoch = r["spec"].copy(), r["generation"]
            if t["expires_at"] > time.time() + 30:
                return t["access_token"]
            if not t["refresh_token"]:
                raise OAuthError("Jeton expiré ou trop proche de l'expiration ; nouveau consentement requis.")
        nouveau = _echanger(spec, {"grant_type": "refresh_token", "refresh_token": t["refresh_token"]},
                           annulation=annulation, scopes_defaut=t["scopes"])
        if not set(scopes) <= set(nouveau["scopes"]):
            raise OAuthError("Le renouvellement n'accorde pas les scopes requis.")
        # Révocation indépendante du verrou de refresh : un reçu tardif ne réactive jamais la connexion.
        with store.locked(_VERROU):
            data = _lire(); r = _record(data, ident)
            if not r["active"] or r["generation"] != epoch or r["tokens"] is None:
                raise OAuthError("Connexion révoquée pendant le renouvellement.")
            if not nouveau["refresh_token"]:
                nouveau["refresh_token"] = t["refresh_token"]
            r.update(tokens=nouveau, modifie=time.time())
            _ecrire(data)
            return nouveau["access_token"]


def revoquer(ident: str, *, par: str, annulation=None):
    par = _texte(par, "par")
    with store.locked(_VERROU):
        data = _lire(); r = _record(data, ident)
        tokens = r["tokens"]
        secret = (tokens["refresh_token"] or tokens["access_token"]) if tokens else ""
        r.update(active=False, tokens=None, generation=r["generation"] + 1, modifie=time.time(), par=par,
                 revocation_distante="non_confirmee" if secret else None)
        generation = r["generation"]
        data["flux"] = {k: v for k, v in data["flux"].items() if v["id"] != ident}
        _ecrire(data)  # La frontière locale se ferme même si Google est indisponible.
    if secret:
        try:
            response = outils_http.requete(_REVOKE_URL, methode="POST", formulaire={"token": secret}, timeout=10, maximum=16000, annulation=annulation)
            confirme = response["status"] == 200
        except (ValueError, OSError, ExecutionAnnulee):
            confirme = False
        with store.locked(_VERROU):
            data = _lire(); r = _record(data, ident)
            if r["generation"] == generation:
                r["revocation_distante"] = "confirmee" if confirme else "non_confirmee"
                _ecrire(data)
    return etat(ident)
