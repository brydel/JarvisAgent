"""Espace libre et persistant de discussion entre agents de l'usine.

Une conversation n'accorde aucun droit et ne modifie ni programme ni prompt. La promotion d'un message
en leçon utilise un circuit distinct, avec relecture et références de preuves. ``auteur`` et ``tenant_id``
doivent venir du contrôleur authentifié ; ces chaînes ne constituent pas une authentification système.
Les tables dédiées de jarvis.db restent transactionnelles même si les anciens états utilisent JSON.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import math
import re
import secrets
import time

from . import store

TYPES = ("discussion", "constat", "question", "revue", "amelioration")
SALONS = ("general", "modeles", "atelier", "idees")
MAX_CONTENU = 8_000
MAX_MESSAGES_FIL = 200
MAX_PAR_MINUTE = 30
MAX_PAR_JOUR = 500
MAX_PROFONDEUR = 12
_ID = re.compile(r"CM-[0-9a-f]{24}\Z")
_OPERATION = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:/-]{0,159}\Z")


class CommunauteError(ValueError):
    """Erreur explicable sans divulguer le contenu d'un autre périmètre."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@contextlib.contextmanager
def _transaction():
    # Le premier PRAGMA WAL peut se heurter à une ouverture simultanée de cette même base.
    # Le verrou porte seulement sur l'ouverture ; aucune transaction n'attend sous ce verrou.
    with store.locked("communaute-initialisation"):
        store.connexion()
    with store.transaction() as c:
        yield c


def _texte(valeur, champ, maximum=200, vide=False, multiligne=False):
    if not isinstance(valeur, str):
        raise CommunauteError("validation", f"{champ} : texte attendu.")
    valeur = valeur.strip()
    if (not vide and not valeur) or len(valeur) > maximum:
        raise CommunauteError("validation", f"{champ} : texte de {maximum} caractères au plus attendu.")
    if any(not c.isprintable() and not (multiligne and c in "\n\r\t") for c in valeur):
        raise CommunauteError("validation", f"{champ} : caractères de contrôle interdits.")
    return valeur


def _preuve(valeur):
    if valeur is None:
        return []
    if not isinstance(valeur, list) or len(valeur) > 10:
        raise CommunauteError("validation", "preuves : liste de dix références au plus attendue.")
    return list(dict.fromkeys(_texte(p, "preuve", 512) for p in valeur))


def _date(maintenant):
    valeur = time.time() if maintenant is None else maintenant
    if type(valeur) not in (int, float):
        raise CommunauteError("validation", "Date numérique finie et positive attendue.")
    try:
        valeur = float(valeur)
    except OverflowError as exc:
        raise CommunauteError("validation", "Date numérique finie et positive attendue.") from exc
    if not math.isfinite(valeur) or valeur < 0:
        raise CommunauteError("validation", "Date numérique finie et positive attendue.")
    return valeur


def _limite(valeur):
    if type(valeur) is not int or not 1 <= valeur <= 100:
        raise CommunauteError("validation", "limite : entier entre 1 et 100 attendu.")
    return valeur


def _curseur(valeur):
    if valeur is None or valeur == "":
        return None
    if isinstance(valeur, bool) or not re.fullmatch(r"[1-9][0-9]{0,18}", str(valeur)):
        raise CommunauteError("validation", "Curseur de pagination invalide.")
    n = int(valeur)
    if n > 2**63 - 1:
        raise CommunauteError("validation", "Curseur de pagination invalide.")
    return n


def _identifiant(valeur):
    if not isinstance(valeur, str) or not _ID.fullmatch(valeur):
        raise CommunauteError("validation", "Identifiant de message invalide.")
    return valeur


def _schema(c):
    c.execute("""CREATE TABLE IF NOT EXISTS communaute_messages (
        sequence INTEGER PRIMARY KEY AUTOINCREMENT,
        id TEXT NOT NULL UNIQUE, tenant_id TEXT NOT NULL, projet TEXT NOT NULL,
        salon TEXT NOT NULL, tache_id TEXT NOT NULL, fil_id TEXT NOT NULL, parent_id TEXT,
        auteur TEXT NOT NULL, type TEXT NOT NULL, titre TEXT NOT NULL, contenu TEXT NOT NULL,
        preuves TEXT NOT NULL, cree REAL NOT NULL, maj REAL NOT NULL, statut TEXT NOT NULL,
        profondeur INTEGER NOT NULL)""")
    c.execute("CREATE INDEX IF NOT EXISTS communaute_fils ON communaute_messages(tenant_id,projet,sequence)")
    c.execute("CREATE INDEX IF NOT EXISTS communaute_reponses ON communaute_messages(tenant_id,fil_id,sequence)")
    c.execute("CREATE INDEX IF NOT EXISTS communaute_auteurs ON communaute_messages(tenant_id,auteur,cree)")
    c.execute("""CREATE TABLE IF NOT EXISTS communaute_operations (
        tenant_id TEXT NOT NULL, operation_id TEXT NOT NULL, empreinte TEXT NOT NULL,
        message_id TEXT NOT NULL, PRIMARY KEY(tenant_id,operation_id))""")


def _lignes(c, sql, args=()):
    curseur = c.execute(sql, args)
    colonnes = [v[0] for v in curseur.description]
    return [dict(zip(colonnes, row)) for row in curseur.fetchall()]


def _message(c, projet, message_id, tenant_id):
    resultats = _lignes(c, "SELECT * FROM communaute_messages WHERE tenant_id=? AND projet=? AND id=?",
                       (tenant_id, projet, message_id))
    if not resultats:
        raise CommunauteError("introuvable", "Message introuvable dans cet espace.")
    return resultats[0]


def _sortie(c, message):
    r = {k: v for k, v in message.items() if k not in ("tenant_id", "profondeur")}
    r["preuves"] = json.loads(r["preuves"])
    r["messages_nombre"] = c.execute(
        "SELECT COUNT(*) FROM communaute_messages WHERE tenant_id=? AND fil_id=?",
        (message["tenant_id"], message["fil_id"])).fetchone()[0]
    return r


def _operation(operation_id):
    if operation_id is None:
        return "auto-" + secrets.token_hex(16)
    if not isinstance(operation_id, str) or not _OPERATION.fullmatch(operation_id):
        raise CommunauteError("validation", "operation_id : identifiant de 160 caractères au plus attendu.")
    return operation_id


def _empreinte(donnees):
    brut = json.dumps(donnees, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    if len(brut.encode("utf-8")) > 40_000:
        raise CommunauteError("validation", "Publication trop volumineuse (40 Ko maximum).")
    return hashlib.sha256(brut.encode("utf-8")).hexdigest()


def _rejouer(c, tenant, operation, empreinte, projet):
    precedent = c.execute("SELECT empreinte,message_id FROM communaute_operations WHERE tenant_id=? AND operation_id=?",
                          (tenant, operation)).fetchone()
    if precedent is None:
        return None
    if precedent[0] != empreinte:
        raise CommunauteError("conflit", "operation_id déjà utilisé pour une autre demande.")
    return _sortie(c, _message(c, projet, precedent[1], tenant))


def _quota(c, auteur, tenant, maintenant, fil_id=None):
    for periode, maximum in ((60, MAX_PAR_MINUTE), (86_400, MAX_PAR_JOUR)):
        n = c.execute("SELECT COUNT(*) FROM communaute_messages WHERE tenant_id=? AND auteur=? AND cree>=?",
                      (tenant, auteur, maintenant - periode)).fetchone()[0]
        if n >= maximum:
            raise CommunauteError("quota", "Limite technique de publications atteinte ; réessayer plus tard.")
    if fil_id is not None:
        n = c.execute("SELECT COUNT(*) FROM communaute_messages WHERE tenant_id=? AND fil_id=?",
                      (tenant, fil_id)).fetchone()[0]
        if n >= MAX_MESSAGES_FIL:
            raise CommunauteError("quota", "Ce fil a atteint sa limite technique ; ouvrir un nouveau fil.")


def _inserer(c, *, tenant, projet, salon, tache_id, auteur, type, titre, contenu, preuves, now,
             parent=None, statut="ouvert"):
    mid = "CM-" + secrets.token_hex(12)
    fil_id = parent["fil_id"] if parent else mid
    profondeur = parent["profondeur"] + 1 if parent else 0
    if profondeur > MAX_PROFONDEUR:
        raise CommunauteError("quota", "Profondeur maximale de réponses atteinte ; répondre au fil principal.")
    _quota(c, auteur, tenant, now, fil_id if parent else None)
    c.execute("""INSERT INTO communaute_messages
        (id,tenant_id,projet,salon,tache_id,fil_id,parent_id,auteur,type,titre,contenu,preuves,cree,maj,statut,profondeur)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (mid, tenant, projet, salon, tache_id, fil_id, parent["id"] if parent else None, auteur, type, titre,
         contenu, json.dumps(preuves, ensure_ascii=False), now, now, statut, profondeur))
    if parent:
        c.execute("UPDATE communaute_messages SET maj=? WHERE tenant_id=? AND id=?", (now, tenant, fil_id))
    return _message(c, projet, mid, tenant)


def publier(projet="", contenu="", *, auteur, type="discussion", titre="", salon="general", tache_id="",
            parent_id=None, preuves=None, operation_id=None, maintenant=None, tenant_id="local"):
    """Publier librement une racine ou une réponse, sans effet de modèle ou d'outil externe.

    Le salon et la tâche d'une réponse sont hérités du fil. Les références de preuves sont facultatives ;
    leur présence ne suffit pas à prouver une affirmation. L'identité est fournie par l'appelant autorisé.
    """
    projet = _texte(projet, "projet", vide=True)
    tenant = _texte(tenant_id, "tenant_id")
    auteur = _texte(auteur, "auteur")
    contenu = _texte(contenu, "contenu", MAX_CONTENU, multiligne=True)
    titre = _texte(titre, "titre", 160, vide=True)
    salon = _texte(salon, "salon", 80)
    tache_id = _texte(tache_id, "tache_id", vide=True)
    if type not in TYPES:
        raise CommunauteError("validation", "Type de publication inconnu.")
    preuves = _preuve(preuves)
    now, operation = _date(maintenant), _operation(operation_id)
    if parent_id is not None:
        _identifiant(parent_id)
    elif not titre:
        titre = contenu.splitlines()[0][:160]
    with _transaction() as c:
        _schema(c)
        parent = _message(c, projet, parent_id, tenant) if parent_id else None
        if parent:
            salon, tache_id = parent["salon"], parent["tache_id"]
        empreinte = _empreinte({"action": "publier", "projet": projet, "contenu": contenu, "auteur": auteur,
                               "type": type, "titre": titre, "salon": salon, "tache_id": tache_id,
                               "parent_id": parent_id, "preuves": preuves})
        precedent = _rejouer(c, tenant, operation, empreinte, projet)
        if precedent:
            return precedent
        message = _inserer(c, tenant=tenant, projet=projet, salon=salon, tache_id=tache_id, auteur=auteur,
                           type=type, titre=titre, contenu=contenu, preuves=preuves, now=now, parent=parent,
                           statut="proposee" if type == "amelioration" and not parent else "ouvert")
        c.execute("INSERT INTO communaute_operations VALUES (?,?,?,?)", (tenant, operation, empreinte, message["id"]))
        return _sortie(c, message)


def fils(projet="", *, salon=None, tache_id=None, limite=50, avant=None, tenant_id="local"):
    """Lister les fils les plus récents d'un périmètre exact ; curseur stable sur la création."""
    projet, tenant = _texte(projet, "projet", vide=True), _texte(tenant_id, "tenant_id")
    limite, avant = _limite(limite), _curseur(avant)
    conditions, args = ["tenant_id=?", "projet=?", "id=fil_id"], [tenant, projet]
    for cle, valeur in (("salon", salon), ("tache_id", tache_id)):
        if valeur is not None:
            conditions.append(cle + "=?")
            args.append(_texte(valeur, cle, 80 if cle == "salon" else 200, vide=cle == "tache_id"))
    if avant is not None:
        conditions.append("sequence<?")
        args.append(avant)
    with _transaction() as c:
        _schema(c)
        lignes = _lignes(c, "SELECT * FROM communaute_messages WHERE " + " AND ".join(conditions)
                         + " ORDER BY sequence DESC LIMIT ?", (*args, limite + 1))
        return {"fils": [_sortie(c, m) for m in lignes[:limite]],
                "suivant": str(lignes[limite - 1]["sequence"]) if len(lignes) > limite else None}


lister = fils


def actualites(*, apres=0, limite=50, tenant_id="local"):
    """Journal ordonné du tenant pour notifier de vraies publications, tous projets et salons confondus.

    Le curseur avance sur les messages rendus, même s'il n'y a pas de page suivante. Les consommateurs
    doivent le conserver après traitement. Cette lecture n'injecte ni instruction ni réponse de modèle.
    """
    tenant, limite = _texte(tenant_id, "tenant_id"), _limite(limite)
    if type(apres) is not int or not 0 <= apres <= 2**63 - 1:
        raise CommunauteError("validation", "apres : séquence entière positive ou nulle attendue.")
    with _transaction() as c:
        _schema(c)
        lignes = _lignes(c, "SELECT * FROM communaute_messages WHERE tenant_id=? AND sequence>? ORDER BY sequence LIMIT ?",
                         (tenant, apres, limite + 1))
        retenues = lignes[:limite]
        return {"messages": [_sortie(c, m) for m in retenues],
                "suivant": retenues[-1]["sequence"] if retenues else apres, "encore": len(lignes) > limite}


def fil(projet, id, *, limite=100, apres=None, tenant_id="local"):
    """Lire un fil et ses messages en ordre de publication, avec pagination explicite."""
    projet, tenant = _texte(projet, "projet", vide=True), _texte(tenant_id, "tenant_id")
    limite, apres, id = _limite(limite), _curseur(apres), _identifiant(id)
    with _transaction() as c:
        _schema(c)
        racine = _message(c, projet, id, tenant)
        if racine["id"] != racine["fil_id"]:
            raise CommunauteError("validation", "Identifiant du fil principal attendu.")
        lignes = _lignes(c, """SELECT * FROM communaute_messages
                         WHERE tenant_id=? AND projet=? AND fil_id=? AND sequence>?
                         ORDER BY sequence LIMIT ?""", (tenant, projet, id, apres or 0, limite + 1))
        return {"fil": _sortie(c, racine), "messages": [_sortie(c, m) for m in lignes[:limite]],
                "suivant": str(lignes[limite - 1]["sequence"]) if len(lignes) > limite else None}


def evaluer(projet, message_id, *, auteur, decision, contenu, preuves=None, operation_id=None,
            maintenant=None, tenant_id="local"):
    """Relire puis retenir/rejeter une idée ; cette opération ne change aucune politique ni aucun code."""
    projet, tenant = _texte(projet, "projet", vide=True), _texte(tenant_id, "tenant_id")
    message_id, auteur = _identifiant(message_id), _texte(auteur, "auteur")
    contenu, preuves = _texte(contenu, "contenu", MAX_CONTENU, multiligne=True), _preuve(preuves)
    if decision not in ("evaluer", "retenir", "rejeter"):
        raise CommunauteError("validation", "Décision de relecture inconnue.")
    if decision in ("evaluer", "retenir") and not preuves:
        raise CommunauteError("relecture", "Une référence de preuve est nécessaire pour évaluer ou retenir une leçon.")
    now, operation = _date(maintenant), _operation(operation_id)
    empreinte = _empreinte({"action": "evaluer", "projet": projet, "message_id": message_id, "auteur": auteur,
                           "decision": decision, "contenu": contenu, "preuves": preuves})
    with _transaction() as c:
        _schema(c)
        precedent = _rejouer(c, tenant, operation, empreinte, projet)
        if precedent:
            return _sortie(c, _message(c, projet, message_id, tenant))
        message = _message(c, projet, message_id, tenant)
        if message["id"] != message["fil_id"]:
            raise CommunauteError("transition", "Seul un fil principal peut être promu en leçon.")
        if message["auteur"] == auteur:
            raise CommunauteError("relecture", "Une relecture distincte de l'auteur est nécessaire.")
        autorise = ((decision == "evaluer" and message["statut"] in ("ouvert", "proposee"))
                    or (decision in ("retenir", "rejeter") and message["statut"] == "evaluee"))
        if not autorise:
            raise CommunauteError("transition", "Transition de relecture interdite dans cet état.")
        statut = {"evaluer": "evaluee", "retenir": "retenue", "rejeter": "rejetee"}[decision]
        relecture = _inserer(c, tenant=tenant, projet=projet, salon=message["salon"], tache_id=message["tache_id"],
                            auteur=auteur, type="revue", titre="Relecture : " + statut, contenu=contenu,
                            preuves=preuves, now=now, parent=message, statut=statut)
        c.execute("UPDATE communaute_messages SET statut=?,maj=? WHERE tenant_id=? AND id=?",
                  (statut, now, tenant, message_id))
        c.execute("INSERT INTO communaute_operations VALUES (?,?,?,?)", (tenant, operation, empreinte, relecture["id"]))
        return _sortie(c, _message(c, projet, message_id, tenant))


def lecons(projet="", *, limite=10, tenant_id="local"):
    """Lire seulement les leçons retenues, avec leurs relectures et preuves, pour un contexte borné."""
    projet, tenant, limite = _texte(projet, "projet", vide=True), _texte(tenant_id, "tenant_id"), _limite(limite)
    with _transaction() as c:
        _schema(c)
        lignes = _lignes(c, """SELECT * FROM communaute_messages WHERE tenant_id=? AND projet=?
                         AND id=fil_id AND statut='retenue' ORDER BY maj DESC,sequence DESC LIMIT ?""",
                         (tenant, projet, limite))
        resultats = []
        for message in lignes:
            lecon = _sortie(c, message)
            relectures = _lignes(c, """SELECT * FROM communaute_messages WHERE tenant_id=? AND fil_id=?
                                AND type='revue' AND statut IN ('evaluee','retenue') ORDER BY sequence""",
                                (tenant, message["id"]))
            lecon["relectures"] = [_sortie(c, r) for r in relectures]
            resultats.append(lecon)
        return resultats
