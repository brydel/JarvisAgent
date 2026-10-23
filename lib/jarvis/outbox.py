"""Intentions persistantes et acquittements du plan de contrôle.

Une intention est écrite dans la transaction métier. La remise se fait ensuite sous bail, sans transaction
ouverte pendant un appel réseau. Les projections locales sont rejouables ; une remise Telegram interrompue
reste « inconnue » jusqu'à réconciliation explicite, pour éviter une seconde écriture aveugle.
"""

from __future__ import annotations

import contextvars
import json
import time
from typing import Callable

CONTEXTE = contextvars.ContextVar("jarvis_effet", default=None)
BAIL_S = 60
ESSAIS_MAX = 5
SORTES_LOCALES = ("board.auto", "synchro.contextualisation", "synchro.livrable", "synchro.decision", "feed",
                  "social.tour")

SCHEMA_SQLITE = """
CREATE TABLE IF NOT EXISTS effets_outbox (
    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES organisations(id), cle TEXT NOT NULL,
    sorte TEXT NOT NULL, donnees TEXT NOT NULL, empreinte TEXT NOT NULL, statut TEXT NOT NULL,
    essais INTEGER NOT NULL DEFAULT 0, essais_max INTEGER NOT NULL DEFAULT 5,
    prochain REAL NOT NULL DEFAULT 0, bail_jeton TEXT, bail_expire REAL, erreur TEXT NOT NULL DEFAULT '',
    cree REAL NOT NULL, maj REAL NOT NULL, acquitte REAL,
    UNIQUE (tenant_id, cle));
CREATE INDEX IF NOT EXISTS effets_outbox_file ON effets_outbox (tenant_id, statut, prochain);
CREATE TABLE IF NOT EXISTS effets_inbox (
    tenant_id TEXT NOT NULL REFERENCES organisations(id), consommateur TEXT NOT NULL, cle TEXT NOT NULL,
    empreinte TEXT NOT NULL, resultat TEXT NOT NULL, recu REAL NOT NULL,
    PRIMARY KEY (tenant_id, consommateur, cle));
"""


class RemiseIncertaine(RuntimeError):
    """L'appel a pu agir : une répétition exige un rapprochement, pas seulement un délai."""


class Indisponible(RuntimeError):
    """Aucune remise n'a été tentée, une nouvelle tentative reste possible."""


def enregistrer(c, tenant_id: str, sorte: str, donnees: dict, *, cle: str, now: float | None = None) -> str:
    """Écrit dans LA connexion métier ; aucun COMMIT ni effet ici. Même clé/charge → même intention."""
    from . import missions as mi
    now = time.time() if now is None else now
    if sorte not in (*SORTES_LOCALES, "telegram", "chef"):
        raise mi.MissionError("outbox", "destination d'effet inconnue")
    charge = json.dumps(donnees, sort_keys=True, ensure_ascii=False, allow_nan=False)
    if not cle or len(cle) > 500 or len(charge) > 100_000:
        raise mi.MissionError("outbox", "clé ou charge d'effet hors bornes")
    empreinte = mi._empreinte({"sorte": sorte, "donnees": donnees})
    eid = mi._id("EF")
    c.execute("INSERT INTO effets_outbox (id, tenant_id, cle, sorte, donnees, empreinte, statut, cree, maj) "
              "VALUES (?,?,?,?,?,?,'en_attente',?,?) ON CONFLICT (tenant_id, cle) DO NOTHING",
              (eid, tenant_id, cle, sorte, charge, empreinte, now, now))
    ligne = c.execute("SELECT id, empreinte FROM effets_outbox WHERE tenant_id=? AND cle=?", (tenant_id, cle)).fetchone()
    if ligne["empreinte"] != empreinte:
        raise mi.MissionError("idempotence", "clé d'effet déjà utilisée avec une autre charge")
    return ligne["id"]


def appliquer_une_fois(c, tenant_id: str, consommateur: str, cle: str, donnees: dict, appliquer, *, now: float):
    """Inbox transactionnelle : le changement local et son reçu sont validés ou annulés ensemble."""
    from . import missions as mi
    empreinte = mi._empreinte(donnees)
    verrou = " FOR UPDATE" if mi.backend().nom == "postgres" else ""
    # Le producteur verrouille l'objet métier avant ceci ; la clé est de plus protégée par son unicité.
    ancien = c.execute("SELECT empreinte, resultat FROM effets_inbox WHERE tenant_id=? AND consommateur=? AND cle=?"
                       + verrou, (tenant_id, consommateur, cle)).fetchone()
    if ancien:
        if ancien["empreinte"] != empreinte:
            raise mi.MissionError("idempotence", "opération déjà reçue avec d'autres paramètres")
        return json.loads(ancien["resultat"])
    resultat = appliquer()
    c.execute("INSERT INTO effets_inbox (tenant_id, consommateur, cle, empreinte, resultat, recu) VALUES (?,?,?,?,?,?)",
              (tenant_id, consommateur, cle, empreinte, json.dumps(resultat, ensure_ascii=False), now))
    return resultat


def ajouter(tenant_id: str, sorte: str, donnees: dict, *, cle: str, now: float | None = None) -> str:
    from . import missions as mi
    with mi.transaction(tenant_id) as c:
        return enregistrer(c, tenant_id, sorte, donnees, cle=cle, now=now)


def _prendre(tenant_id: str, now: float, sortes: tuple[str, ...] | None):
    from . import missions as mi
    with mi.transaction(tenant_id) as c:
        # Une remise externe interrompue peut avoir réussi. Elle ne repart jamais automatiquement.
        c.execute("UPDATE effets_outbox SET statut='inconnu', erreur=?, maj=?, bail_jeton=NULL, bail_expire=NULL "
                  "WHERE tenant_id=? AND statut='en_cours' AND bail_expire<=? AND sorte='telegram'",
                  ("remise interrompue : vérifier le destinataire avant relance", now, tenant_id, now))
        c.execute("UPDATE effets_outbox SET statut=CASE WHEN essais>=essais_max THEN 'echec' ELSE 'en_attente' END, "
                  "bail_jeton=NULL, bail_expire=NULL, maj=? WHERE tenant_id=? AND statut='en_cours' "
                  "AND bail_expire<=? AND sorte<>'telegram'", (now, tenant_id, now))
        clause, params = "", []
        if sortes is not None:
            if not sortes:
                return None
            clause = " AND sorte IN (" + ",".join("?" for _ in sortes) + ")"
            params = list(sortes)
        e = c.execute("SELECT * FROM effets_outbox WHERE tenant_id=? AND statut='en_attente' AND prochain<=?"
                      + clause + " ORDER BY cree, CASE WHEN sorte='board.auto' THEN 0 ELSE 1 END, id LIMIT 1" + mi.backend().verrou_file,
                      (tenant_id, now, *params)).fetchone()
        if e is None:
            return None
        jeton = mi._id("BE")
        n = c.execute("UPDATE effets_outbox SET statut='en_cours', essais=essais+1, bail_jeton=?, bail_expire=?, maj=? "
                      "WHERE tenant_id=? AND id=? AND statut='en_attente'", (jeton, now + BAIL_S, now, tenant_id, e["id"])).rowcount
        if n != 1:
            return None
        return {**dict(e), "essais": e["essais"] + 1, "bail_jeton": jeton, "donnees": json.loads(e["donnees"])}


def _executer(e: dict):
    from . import missions as mi
    d, tenant = e["donnees"], e["tenant_id"]
    if e["sorte"] == "board.auto":
        try:
            return mi.decider_proposition(tenant, d["objet_id"], d["index"], "lancer", par="jarvis:auto",
                                          operation_id=e["id"], generation=d["generation"])
        except mi.MissionError as exc:
            if exc.code in ("conflit", "obsolete", "inconnue"):
                return {"ignore": exc.code}  # une décision humaine ou une nouvelle analyse a pris le relais
            raise
    if e["sorte"].startswith("synchro."):
        from . import synchro
        d = dict(d)
        auto_operation, auto_index = d.pop("auto_operation", None), d.pop("auto_index", None)
        if auto_operation:
            c = mi._connecter(tenant)
            try:
                auto = c.execute("SELECT statut FROM effets_outbox WHERE tenant_id=? AND id=?",
                                 (tenant, auto_operation)).fetchone()
                recu = c.execute("SELECT resultat FROM effets_inbox WHERE tenant_id=? AND consommateur='board.decision' AND cle=?",
                                 (tenant, auto_operation)).fetchone()
            finally:
                c.close()
            if auto and auto["statut"] in ("en_attente", "en_cours"):
                raise Indisponible("action préparatoire en attente avant notification")
            if recu and d.get("snapshot") is not None:
                # Enrichissement par le reçu immuable de CETTE génération, jamais par les métadonnées actuelles.
                snapshot = json.loads(json.dumps(d["snapshot"]))
                props = snapshot["meta"]["propositions"]
                if type(auto_index) is int and 0 <= auto_index < len(props):
                    props[auto_index].update(json.loads(recu["resultat"]), statut="lancee", par="jarvis:auto")
                d["snapshot"] = snapshot
        nom = {"synchro.contextualisation": "apres_contextualisation", "synchro.livrable": "apres_livrable",
               "synchro.decision": "apres_decision"}[e["sorte"]]
        return getattr(synchro, nom)(tenant, **d)
    if e["sorte"] == "social.tour":
        from . import vie_sociale
        vie_sociale.apres_tour(tenant, d["travail"], d["contenu"])  # publication idempotente (operation_id)
        return {"remis": True}
    if e["sorte"] == "feed":
        from . import store
        store.feed_add(d["type"], d["texte"], operation_id=e["id"])
        return {"remis": True}
    if e["sorte"] == "telegram":
        from . import notify
        from .telegram import TelegramError
        bot, chat = notify.bot_and_chat()
        if bot is None:
            raise Indisponible("Telegram non configuré : aucun envoi tenté")
        texte = str(d["args"][0])[:3900]
        boutons = d["args"][1] if len(d["args"]) > 1 else None
        try:
            recu = bot.send(chat, texte, boutons)
        except TelegramError:
            # L'exception réseau peut inclure une URL avec jeton : ne jamais la recopier au journal.
            raise RemiseIncertaine("échec de remise Telegram : vérifier le destinataire avant relance") from None
        return {"remis": True, "destination": "telegram", "message_id": (recu or {}).get("message_id")}
    if e["sorte"] == "chef":
        from . import agents
        if not agents.chef_inject(d["args"][0], message_id=e["id"]):
            raise Indisponible("chef absent : aucun message remis")
        return {"remis": True, "destination": "file_chef"}
    raise ValueError("destination d'effet inconnue")


def traiter(*, tenant_id: str | None = None, limite: int = 20, now: float | None = None,
            sortes: tuple[str, ...] | None = None, interrompu: Callable[[], bool] | None = None) -> dict:
    """Un passage borné. Peut être appelé concurremment ; une tentative possède un jeton de clôture."""
    from . import missions as mi
    if type(limite) is not int or not 1 <= limite <= 200:
        raise ValueError("limite d'effets : entier de 1 à 200 attendu")
    fixe = now
    bilan = {"remis": 0, "replanifies": 0, "echecs": 0, "inconnus": 0, "traites": 0}
    tenants = [tenant_id] if tenant_id else mi.backend().tenants()
    for tenant in tenants:
        while bilan["traites"] < limite:
            if interrompu is not None and interrompu():
                return bilan
            instant = time.time() if fixe is None else fixe
            e = _prendre(tenant, instant, sortes)
            if e is None:
                break
            if interrompu is not None and interrompu():
                # Aucun appel n'est parti : rendre l'intention sans consommer d'essai ni produire d'incertitude.
                with mi.transaction(tenant) as c:
                    c.execute("UPDATE effets_outbox SET statut='en_attente', essais=essais-1, bail_jeton=NULL, "
                              "bail_expire=NULL, maj=? WHERE tenant_id=? AND id=? AND statut='en_cours' AND bail_jeton=?",
                              (instant, tenant, e["id"], e["bail_jeton"]))
                return bilan
            jeton = CONTEXTE.set(e)
            erreur, statut, resultat = "", "livre", {}
            try:
                resultat = _executer(e) or {}
            except RemiseIncertaine:
                erreur, statut = "remise externe incertaine : vérifier la destination avant relance", "inconnu"
            except Exception as exc:  # noqa: BLE001 — l'intention reste inspectable et la suite progresse
                # Ne pas conserver une exception fournisseur pouvant contenir un secret/URL privée.
                erreur = str(exc) if isinstance(exc, Indisponible) else f"remise échouée ({type(exc).__name__})"
                if e["sorte"] == "telegram" and not isinstance(exc, Indisponible):
                    # Même une erreur inattendue peut survenir après l'envoi (décodage, stockage du reçu…).
                    statut = "inconnu"
                else:
                    statut = "echec" if e["essais"] >= e["essais_max"] else "en_attente"
            finally:
                CONTEXTE.reset(jeton)
            with mi.transaction(tenant) as c:
                n = c.execute("UPDATE effets_outbox SET statut=?, erreur=?, prochain=?, bail_jeton=NULL, bail_expire=NULL, "
                              "maj=?, acquitte=? WHERE tenant_id=? AND id=? AND statut='en_cours' AND bail_jeton=?",
                              (statut, erreur[:300], instant + min(300, 2 ** e["essais"]), instant,
                               instant if statut == "livre" else None, tenant, e["id"], e["bail_jeton"])).rowcount
                if n and statut == "livre":
                    c.execute("INSERT INTO effets_inbox (tenant_id, consommateur, cle, empreinte, resultat, recu) "
                              "VALUES (?, 'outbox', ?, ?, ?, ?) ON CONFLICT (tenant_id, consommateur, cle) DO NOTHING",
                              (tenant, e["id"], e["empreinte"], json.dumps(resultat, ensure_ascii=False), instant))
            bilan["traites"] += 1
            if n:
                bilan[{"livre": "remis", "en_attente": "replanifies", "echec": "echecs", "inconnu": "inconnus"}[statut]] += 1
    return bilan


def etat(tenant_id: str, *, limite: int = 100) -> dict:
    """Descriptions sans contenu : un diagnostic ne divulgue pas les textes des messages."""
    from . import missions as mi
    limite = max(1, min(200, int(limite)))
    c = mi._connecter(tenant_id)
    try:
        comptes = {r["statut"]: r["n"] for r in c.execute(
            "SELECT statut, COUNT(*) AS n FROM effets_outbox WHERE tenant_id=? GROUP BY statut", (tenant_id,))}
        effets = [dict(r) for r in c.execute(
            "SELECT id, sorte, statut, essais, essais_max, prochain, bail_expire, erreur, cree, maj, acquitte "
            "FROM effets_outbox WHERE tenant_id=? ORDER BY cree DESC LIMIT ?", (tenant_id, limite))]
        return {"comptes": comptes, "effets": effets}
    finally:
        c.close()


def relancer(tenant_id: str, effet_id: str, *, par: str, confirmer_inconnu: bool = False,
             now: float | None = None) -> dict:
    """Relance explicite après diagnostic ; un résultat inconnu exige un rapprochement préalable."""
    from . import missions as mi
    now = time.time() if now is None else now
    with mi.transaction(tenant_id) as c:
        verrou = " FOR UPDATE" if mi.backend().nom == "postgres" else ""
        e = c.execute("SELECT * FROM effets_outbox WHERE tenant_id=? AND id=?" + verrou, (tenant_id, effet_id)).fetchone()
        if e is None:
            raise mi.MissionError("inconnue", "effet inconnu")
        if e["statut"] == "inconnu" and confirmer_inconnu is not True:
            raise mi.MissionError("incertain", "rapprocher l'effet externe avant de confirmer une relance")
        if e["statut"] not in ("echec", "inconnu", "en_attente"):
            raise mi.MissionError("conflit", "seul un effet en attente, échoué ou rapproché peut être relancé")
        c.execute("UPDATE effets_outbox SET statut='en_attente', essais=0, prochain=?, erreur='', maj=? "
                  "WHERE tenant_id=? AND id=?", (now, now, tenant_id, effet_id))
        mi._evenement(c, tenant_id, "outbox_relance", now=now, effet_id=effet_id, par=par,
                      inconnu_confirme=e["statut"] == "inconnu")
    return {"id": effet_id, "statut": "en_attente"}
