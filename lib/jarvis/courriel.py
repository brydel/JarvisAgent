"""Outils Gmail sous passerelle : MIME contrôlé, destinataire unique et reçus rapprochables.

Le Message-ID stable aide la recherche d'un résultat inconnu ; Gmail ne le traite pas comme une clé
d'idempotence. Aucune fonction de ce module ne répète un envoi ou un brouillon après une réponse perdue.
La passerelle fournit le mandat et journalise son identité d'opération avant le départ.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
import time
from email.message import EmailMessage
from email.policy import SMTP
from email.utils import formatdate
from urllib.parse import urlencode, quote

from . import mandats, oauth, outils_http

_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"
_READ = "https://www.googleapis.com/auth/gmail.readonly"
_COMPOSE = "https://www.googleapis.com/auth/gmail.compose"
_SEND = "https://www.googleapis.com/auth/gmail.send"
_OPERATION = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:/-]{0,127}\Z")
_MESSAGE = re.compile(r"[A-Za-z0-9_-]{1,200}\Z")


class CourrielError(ValueError):
    """Erreur publique expurgée ; aucune réponse brute fournisseur ni credential."""


def _texte(v, champ, maximum=500, multiligne=False):
    if (not isinstance(v, str) or not v.strip() or len(v) > maximum
            or any((ord(c) < 32 and (not multiligne or c not in "\r\n\t")) or ord(c) == 127 for c in v)):
        raise CourrielError(f"{champ} : texte non vide de taille limitée attendu.")
    return v.strip()


def _message_id(connexion_id: str, operation_id: str):
    if not isinstance(operation_id, str) or not _OPERATION.fullmatch(operation_id):
        raise CourrielError("Identité d'opération courriel invalide.")
    digest = hashlib.sha256((connexion_id + "\0" + operation_id).encode()).hexdigest()
    return f"<jarvis.{digest}@jarvis.invalid>"


def _ident_message(v):
    if not isinstance(v, str) or not _MESSAGE.fullmatch(v):
        raise CourrielError("Identifiant de message Gmail invalide.")
    return v


def _expurger(v, jeton):
    if isinstance(v, str):
        return v.replace(jeton, "[SECRET]") if jeton else v
    if isinstance(v, dict):
        return {str(k): _expurger(x, jeton) for k, x in v.items()}
    if isinstance(v, list):
        return [_expurger(x, jeton) for x in v]
    return v


def _json(response):
    if response["status"] < 200 or response["status"] >= 300:
        raise CourrielError("Gmail a refusé la demande ; réponse fournisseur non exposée.")
    try:
        d = json.loads(response["contenu"])
        if not isinstance(d, dict):
            raise ValueError
        return d
    except (ValueError, UnicodeError, TypeError, RecursionError) as exc:
        raise CourrielError("Réponse Gmail non exploitable ; ne pas répéter une écriture.") from exc


def _recu(d):
    ident = _ident_message(d.get("id"))
    thread = d.get("threadId")
    if thread is not None:
        _ident_message(thread)
    return {"message_id": ident, "thread_id": thread}


def _mime(expediteur, destinataire, objet, texte, message_id):
    m = EmailMessage(policy=SMTP)
    m["To"] = destinataire
    m["From"] = expediteur
    m["Subject"] = objet
    m["Message-ID"] = message_id
    m["Date"] = formatdate(time.time(), localtime=False, usegmt=True)
    # L'identité From vient uniquement de la configuration propriétaire ; Gmail contrôle compte/alias.
    m.set_content(texte)
    raw = m.as_bytes()
    if len(raw) > 90000:
        raise CourrielError("Courriel trop volumineux pour cette première intégration.")
    return base64.urlsafe_b64encode(raw).decode()


def _contenu_message(data):
    recu = _recu(data)
    payload = data.get("payload", {})
    if not isinstance(payload, dict):
        raise CourrielError("Structure de message Gmail invalide.")
    headers = payload.get("headers", [])
    utiles = {"from", "to", "subject", "date", "message-id"}
    if not isinstance(headers, list):
        raise CourrielError("En-têtes Gmail invalides.")
    publics = [{"nom": h["name"], "valeur": str(h["value"])[:1000]} for h in headers[:100]
               if isinstance(h, dict) and isinstance(h.get("name"), str) and h["name"].lower() in utiles and "value" in h]
    morceaux = []
    visites = 0

    def lire(p, profondeur=0):
        nonlocal visites
        visites += 1
        if visites > 50 or profondeur > 8 or not isinstance(p, dict):
            return
        if p.get("mimeType") == "text/plain":
            body = p.get("body", {})
            if isinstance(body, dict) and isinstance(body.get("data"), str) and len(body["data"]) <= 90000:
                try:
                    raw = base64.b64decode(body["data"] + "=" * (-len(body["data"]) % 4), altchars=b"-_", validate=True)
                    morceaux.append(raw.decode("utf-8", errors="replace")[:64000])
                except (ValueError, UnicodeError):
                    pass
        parts = p.get("parts", [])
        if isinstance(parts, list):
            for part in parts[:50]:
                lire(part, profondeur + 1)

    lire(payload)
    text = "\n".join(morceaux)
    return {**recu, "entetes": publics, "texte": text[:64000], "extrait": str(data.get("snippet", ""))[:1000],
            "tronque": len(text) > 64000 or visites > 50, "source": "gmail", "source_non_fiable": True}


def catalogue():
    descriptions = {
        "courriel.profile": ("Lire le profil Gmail", "lecture", ["connexion_id"], {}),
        "courriel.search": ("Rechercher des messages Gmail", "lecture", ["connexion_id", "requete"], {
            "requete": {"type": "string", "maxLength": 500}, "maximum": {"type": "integer", "minimum": 1, "maximum": 25}}),
        "courriel.read": ("Lire le texte d'un message Gmail", "lecture", ["connexion_id", "message_id"], {
            "message_id": {"type": "string", "maxLength": 200}}),
        "courriel.draft": ("Créer un brouillon Gmail", "ecriture", ["connexion_id", "destinataire", "objet", "texte"], {
            "destinataire": {"type": "string", "maxLength": 320}, "objet": {"type": "string", "maxLength": 500},
            "texte": {"type": "string", "maxLength": 40000}}),
        "courriel.send": ("Envoyer un courriel Gmail", "ecriture", ["connexion_id", "destinataire", "objet", "texte"], {
            "destinataire": {"type": "string", "maxLength": 320}, "objet": {"type": "string", "maxLength": 500},
            "texte": {"type": "string", "maxLength": 40000}}),
        "courriel.reconcile": ("Chercher le reçu d'un envoi Gmail incertain", "lecture", ["connexion_id", "operation_id"], {
            "operation_id": {"type": "string", "maxLength": 128}}),
    }
    connexions = oauth.lister()
    retour = []
    for ident, (nom, effet, requis, props) in descriptions.items():
        scope = _COMPOSE if ident == "courriel.draft" else _SEND if ident == "courriel.send" else _READ
        disponible = any(c["etat"] in ("connectee", "expiree") and scope in c["scopes_accordes"]
                         and (effet != "ecriture" or c["adresse_expediteur"])
                         and (c["etat"] == "connectee" or c["renouvelable"]) for c in connexions)
        retour.append({"id": ident, "nom": nom, "effet": effet, "disponible": disponible,
                       "inputSchema": {"type": "object", "properties": {"connexion_id": {"type": "string"}, **props},
                                       "required": requis, "additionalProperties": False}})
    return retour


def preparer(tool: str, arguments: dict, operation_id: str, *, annulation=None):
    """Retourne destination exacte, effet, appel contrôlé ; n'effectue aucun réseau ni réservation."""
    if not isinstance(arguments, dict):
        raise CourrielError("Arguments courriel : objet requis.")
    ident = arguments.get("connexion_id")
    autorises = {
        "courriel.profile": {"connexion_id"}, "courriel.search": {"connexion_id", "requete", "maximum"},
        "courriel.read": {"connexion_id", "message_id"},
        "courriel.draft": {"connexion_id", "destinataire", "objet", "texte"},
        "courriel.send": {"connexion_id", "destinataire", "objet", "texte"},
        "courriel.reconcile": {"connexion_id", "operation_id"},
    }
    if tool not in autorises or set(arguments) - autorises[tool]:
        raise CourrielError("Outil courriel ou champs non pris en charge.")
    scope = _COMPOSE if tool == "courriel.draft" else _SEND if tool == "courriel.send" else _READ
    public = oauth.verifier(ident, [scope])
    epoch = public["generation"]
    destination, ecriture = "gmail.googleapis.com", tool in {"courriel.send", "courriel.draft"}
    chemin, methode, body = "/profile", "GET", None
    message_id = None
    if tool == "courriel.search":
        q = _texte(arguments.get("requete"), "requete", 500)
        maximum = arguments.get("maximum", 10)
        if type(maximum) is not int or not 1 <= maximum <= 25:
            raise CourrielError("maximum doit être un entier de 1 à 25.")
        chemin = "/messages?" + urlencode({"q": q, "maxResults": maximum})
    elif tool == "courriel.read":
        chemin = "/messages/" + quote(_ident_message(arguments.get("message_id")), safe="") + "?format=full"
    elif ecriture:
        try:
            destination = mandats._destination(arguments.get("destinataire"))
        except ValueError as exc:
            raise CourrielError("Destinataire unique exact requis, sans nom d'affichage ni autre en-tête.") from exc
        if "@" not in destination:
            raise CourrielError("Une adresse courriel exacte est requise.")
        objet = _texte(arguments.get("objet"), "objet", 500)
        texte = _texte(arguments.get("texte"), "texte", 40000, multiligne=True)
        message_id = _message_id(ident, operation_id)
        if not public["adresse_expediteur"]:
            raise CourrielError("Adresse expéditrice propriétaire requise pour les brouillons et envois.")
        raw = _mime(public["adresse_expediteur"], destination, objet, texte, message_id)
        chemin, methode = ("/drafts" if tool == "courriel.draft" else "/messages/send"), "POST"
        body = {"message": {"raw": raw}} if tool == "courriel.draft" else {"raw": raw}
    elif tool == "courriel.reconcile":
        message_id = _message_id(ident, arguments.get("operation_id"))
        chemin = "/messages?" + urlencode({"q": "in:anywhere rfc822msgid:" + message_id[1:-1], "maxResults": 10})

    def appel(verifier):
        verifier()
        if annulation is not None:
            annulation.verifier()
        token = oauth.jeton_acces(ident, [scope], generation=epoch, annulation=annulation)
        fin = time.monotonic() + 20

        def demander(path, method="GET", donnees=None):
            verifier()
            oauth.verifier(ident, [scope], generation=epoch)
            if annulation is not None:
                annulation.verifier()
            restant = fin - time.monotonic()
            if restant <= 0:
                raise CourrielError("Délai total du connecteur Gmail dépassé.")
            return _json(outils_http.requete(_BASE + path, methode=method, donnees=donnees,
                         entetes={"Authorization": "Bearer " + token}, timeout=min(10, restant), maximum=300000,
                         annulation=annulation))

        data = demander(chemin, methode, body)
        if tool == "courriel.profile":
            adresse = data.get("emailAddress")
            try:
                adresse = mandats._destination(adresse)
            except ValueError as exc:
                raise CourrielError("Profil Gmail invalide.") from exc
            if "@" not in adresse:
                raise CourrielError("Profil Gmail invalide.")
            retour = {"adresse": adresse, "source": "gmail"}
        elif tool == "courriel.read":
            retour = _contenu_message(data)
        elif tool in {"courriel.send", "courriel.draft"}:
            message = data.get("message") if tool == "courriel.draft" else data
            if not isinstance(message, dict):
                raise CourrielError("Reçu d'écriture Gmail non exploitable.")
            retour = {**_recu(message), "message_id_rfc": message_id, "source": "gmail",
                      "envoi_confirme": tool == "courriel.send"}
            if tool == "courriel.draft":
                retour["draft_id"] = _ident_message(data.get("id"))
        else:
            messages = data.get("messages", [])
            if not isinstance(messages, list) or len(messages) > 25:
                raise CourrielError("Liste de messages Gmail invalide.")
            recus = [_recu(m) for m in messages if isinstance(m, dict)]
            if len(recus) != len(messages):
                raise CourrielError("Liste de messages Gmail invalide.")
            retour = {"messages": recus, "page_suivante": bool(data.get("nextPageToken")), "source": "gmail", "source_non_fiable": True}
            if tool == "courriel.reconcile":
                confirmes = []
                for recu in recus[:10]:
                    d = demander("/messages/" + quote(recu["message_id"], safe="") + "?format=metadata&metadataHeaders=Message-ID")
                    p = d.get("payload", {})
                    hs = p.get("headers", []) if isinstance(p, dict) else []
                    ids = [h.get("value", "").strip() for h in hs if isinstance(h, dict)
                           and isinstance(h.get("name"), str) and h["name"].lower() == "message-id"] if isinstance(hs, list) else []
                    if ids == [message_id] and isinstance(d.get("labelIds"), list) and "SENT" in d["labelIds"]:
                        confirmes.append(_recu(d))
                unique = len(confirmes) == 1 and not data.get("nextPageToken")
                retour.update(message_id_rfc=message_id, confirme=unique,
                              statut="envoi_confirme" if unique else "ambigu" if len(confirmes) > 1 or data.get("nextPageToken") else "non_confirme",
                              recus_confirmes=confirmes)
                if unique:
                    retour.update(confirmes[0])
        return _expurger(retour, token)

    return destination, ecriture, appel
