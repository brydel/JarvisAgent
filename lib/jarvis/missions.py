"""Moteur de missions durable (Jarvis Next, jalon M1) : missions, tâches, baux, tentatives, artefacts, Board.

Source de vérité d'une mission : cette base, jamais le navigateur ni la conversation d'un modèle. Tout changement
d'état passe par `_transition`, qui refuse une transition illégale et écrit l'événement correspondant DANS LA MÊME
TRANSACTION (journal ordonné par numéro de séquence, lu par le Studio et la reprise).

Garanties visées, chacune couverte par tests/test_missions.py :
- une tâche n'est confiée qu'à un exécutant authentifié du MÊME tenant (le tenant vient de son enrôlement, pas de
  ce qu'il affirme), et seulement si ses capacités couvrent celles de la tâche ;
- chaque prise de bail incrémente un jeton de clôture : le résultat d'un exécutant qui a perdu son bail (plantage,
  coupure réseau, délai dépassé) est refusé ; un résultat rejoué (même clé d'idempotence) est acquitté sans effet ;
- un artefact par tâche au plus (contrainte d'unicité) : pas de travail terminé dupliqué ;
- la politique (niveaux L0–L4) est appliquée ici, par du code : L3/L4 attendent toujours une approbation humaine,
  liée à l'empreinte du travail approuvé ; ni un exécutant ni le demandeur ne peuvent approuver ;
- le routage refuse une connexion fournisseur non admise pour le profil de déploiement, et une connexion payante
  sans budget d'inférence positif (zéro par défaut), AVANT l'envoi ; sans fournisseur, la tâche attend
  (WAITING_PROVIDER) sans consommer d'essai ;
- une sous-tâche ne peut pas élargir les droits de sa tâche parente (niveau, capacités) ; profondeur et largeur
  de délégation bornées.

Stockage : SQLite (bibliothèque standard), fichier missions.db sous l'état de Jarvis, transactions BEGIN IMMEDIATE.
Le schéma porte un tenant_id partout pour pouvoir passer à PostgreSQL (RLS) sans le redessiner : voir
docs/jarvis-next/MISSION_ENGINE.md. Limite honnête : sur ce poste, la base appartient au même utilisateur Linux
que les agents ; l'isolation réelle viendra du plan de contrôle séparé (M3).
"""

from __future__ import annotations

import contextlib
import hashlib
import hmac
import json
import secrets
import sqlite3
import time
from typing import Iterator

from . import config, protocole_executant as proto

SCHEMA_VERSION = 1
FICHIER = "missions.db"

TENANT_LOCAL = "ORG-personnel"

# --- États et transitions légales -------------------------------------------------

CREATED, VALIDATED, WAITING_APPROVAL, QUEUED = "CREATED", "VALIDATED", "WAITING_APPROVAL", "QUEUED"
WAITING_PROVIDER, LEASED, RUNNING, REVIEW = "WAITING_PROVIDER", "LEASED", "RUNNING", "REVIEW"
RETRY_SCHEDULED, SUCCEEDED, FAILED = "RETRY_SCHEDULED", "SUCCEEDED", "FAILED"
CANCELLED, EXPIRED = "CANCELLED", "EXPIRED"

TERMINAUX = frozenset({SUCCEEDED, FAILED, CANCELLED, EXPIRED})

TRANSITIONS: dict[str, frozenset[str]] = {
    CREATED: frozenset({VALIDATED, FAILED, CANCELLED}),
    VALIDATED: frozenset({QUEUED, WAITING_APPROVAL, CANCELLED}),
    WAITING_APPROVAL: frozenset({QUEUED, CANCELLED, EXPIRED}),
    QUEUED: frozenset({LEASED, WAITING_PROVIDER, CANCELLED, EXPIRED}),
    WAITING_PROVIDER: frozenset({QUEUED, CANCELLED, EXPIRED}),
    LEASED: frozenset({RUNNING, RETRY_SCHEDULED, WAITING_PROVIDER, FAILED, CANCELLED}),
    RUNNING: frozenset({REVIEW, RETRY_SCHEDULED, WAITING_PROVIDER, FAILED, CANCELLED}),
    REVIEW: frozenset({SUCCEEDED, FAILED, RETRY_SCHEDULED}),
    RETRY_SCHEDULED: frozenset({QUEUED, CANCELLED, EXPIRED}),
    SUCCEEDED: frozenset(),
    FAILED: frozenset(),
    CANCELLED: frozenset(),
    EXPIRED: frozenset(),
}

# --- Politique : niveaux d'autonomie ------------------------------------------------

NIVEAUX = proto.NIVEAUX
AUTO_PAR_DEFAUT = ("L0", "L1")
JAMAIS_AUTO = ("L3", "L4")  # constante du code : aucun réglage ne rend L3/L4 automatiques

# --- Profils de déploiement et éligibilité des connexions fournisseurs ----------------

PROFILS = ("PERSONAL_LOCAL", "CUSTOMER_OWNED_RUNNER", "COMMERCIAL_HOSTED")
# mode d'authentification → profils où la connexion peut servir (docs/jarvis-next/COMMERCIAL_COMPLIANCE.md)
ELIGIBILITE = {
    "abonnement": ("PERSONAL_LOCAL", "CUSTOMER_OWNED_RUNNER"),  # session du propriétaire de la machine, sur sa machine
    "api": ("PERSONAL_LOCAL", "CUSTOMER_OWNED_RUNNER", "COMMERCIAL_HOSTED"),
    "factice": ("PERSONAL_LOCAL", "CUSTOMER_OWNED_RUNNER", "COMMERCIAL_HOSTED"),
}

# --- Bornes -----------------------------------------------------------------------

BAIL_S = 120
ESSAIS_MAX = 3
INDISPONIBILITE_S = 900
REVERIFICATION_S = 300
PROFONDEUR_MAX = 3
LARGEUR_MAX = 8
TACHES_PAR_MISSION_MAX = 50


class MissionError(Exception):
    """Erreur métier lisible (code court + message en français)."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class TransitionInterdite(MissionError):
    def __init__(self, de: str, vers: str):
        super().__init__("transition", f"transition interdite : {de} → {vers}")


# --- Base ---------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (cle TEXT PRIMARY KEY, valeur TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS organisations (
    id TEXT PRIMARY KEY, nom TEXT NOT NULL, cree REAL NOT NULL);
CREATE TABLE IF NOT EXISTS reglages_tenant (
    tenant_id TEXT PRIMARY KEY REFERENCES organisations(id),
    niveaux_auto TEXT NOT NULL, budget_inference_centimes INTEGER NOT NULL DEFAULT 0,
    consomme_centimes INTEGER NOT NULL DEFAULT 0, arret_urgence INTEGER NOT NULL DEFAULT 0,
    board_auto_analyse INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS executants (
    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES organisations(id), nom TEXT NOT NULL,
    secret_empreinte TEXT NOT NULL, capacites TEXT NOT NULL, fournisseurs TEXT NOT NULL,
    profil TEXT NOT NULL, version TEXT NOT NULL DEFAULT '', systeme TEXT NOT NULL DEFAULT '',
    revoque INTEGER NOT NULL DEFAULT 0, dernier_signe REAL, cree REAL NOT NULL);
CREATE TABLE IF NOT EXISTS connexions (
    tenant_id TEXT NOT NULL REFERENCES organisations(id), fournisseur TEXT NOT NULL,
    mode_auth TEXT NOT NULL, payant INTEGER NOT NULL DEFAULT 0, active INTEGER NOT NULL DEFAULT 1,
    indisponible_jusqua REAL NOT NULL DEFAULT 0, raison TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (tenant_id, fournisseur));
CREATE TABLE IF NOT EXISTS missions (
    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES organisations(id), objectif TEXT NOT NULL,
    source TEXT NOT NULL, demandeur TEXT NOT NULL, statut TEXT NOT NULL, correlation_id TEXT NOT NULL,
    cle_idempotence TEXT, cree REAL NOT NULL, maj REAL NOT NULL,
    UNIQUE (tenant_id, cle_idempotence));
CREATE TABLE IF NOT EXISTS taches (
    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, mission_id TEXT NOT NULL REFERENCES missions(id),
    parent_id TEXT REFERENCES taches(id), profondeur INTEGER NOT NULL DEFAULT 0,
    type TEXT NOT NULL, niveau TEXT NOT NULL, capacites TEXT NOT NULL, fournisseur TEXT NOT NULL,
    travail TEXT NOT NULL, statut TEXT NOT NULL, essais INTEGER NOT NULL DEFAULT 0,
    essais_max INTEGER NOT NULL, delai_s INTEGER NOT NULL, echeance REAL,
    bail_executant TEXT, bail_jeton INTEGER NOT NULL DEFAULT 0, bail_expire REAL,
    tentative_id TEXT, fournisseur_choisi TEXT, prochaine_tentative REAL, raison TEXT NOT NULL DEFAULT '',
    cree REAL NOT NULL, maj REAL NOT NULL);
CREATE INDEX IF NOT EXISTS taches_file ON taches (tenant_id, statut, cree);
CREATE TABLE IF NOT EXISTS tentatives (
    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, tache_id TEXT NOT NULL REFERENCES taches(id),
    executant_id TEXT NOT NULL, bail_jeton INTEGER NOT NULL, fournisseur TEXT NOT NULL,
    cle_idempotence TEXT NOT NULL UNIQUE, debut REAL NOT NULL, fin REAL, issue TEXT, erreur TEXT);
CREATE TABLE IF NOT EXISTS approbations (
    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, tache_id TEXT NOT NULL REFERENCES taches(id),
    empreinte TEXT NOT NULL, demandeur TEXT NOT NULL, statut TEXT NOT NULL,
    decide_par TEXT, decide REAL, cree REAL NOT NULL);
CREATE TABLE IF NOT EXISTS artefacts (
    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, mission_id TEXT NOT NULL, tache_id TEXT NOT NULL,
    tentative_id TEXT NOT NULL UNIQUE, type TEXT NOT NULL, contenu TEXT NOT NULL, empreinte TEXT NOT NULL,
    fournisseur TEXT NOT NULL, factice INTEGER NOT NULL, revue TEXT NOT NULL DEFAULT 'en_cours',
    cree REAL NOT NULL);
CREATE TABLE IF NOT EXISTS board_objets (
    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, espace TEXT NOT NULL, type TEXT NOT NULL,
    contenu TEXT NOT NULL, x REAL NOT NULL DEFAULT 0, y REAL NOT NULL DEFAULT 0,
    mission_id TEXT, auteur TEXT NOT NULL, cree REAL NOT NULL);
CREATE TABLE IF NOT EXISTS evenements (
    seq INTEGER PRIMARY KEY AUTOINCREMENT, tenant_id TEXT NOT NULL, mission_id TEXT, tache_id TEXT,
    type TEXT NOT NULL, donnees TEXT NOT NULL, ts REAL NOT NULL);
CREATE INDEX IF NOT EXISTS evenements_tenant ON evenements (tenant_id, seq);
"""


def chemin_base():
    config.STATE_DIR.mkdir(parents=True, exist_ok=True)
    return config.STATE_DIR / FICHIER


def _connecter() -> sqlite3.Connection:
    c = sqlite3.connect(chemin_base(), timeout=30, isolation_level=None)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA busy_timeout=30000")
    c.execute("PRAGMA foreign_keys=ON")
    c.executescript(_SCHEMA)
    ligne = c.execute("SELECT valeur FROM meta WHERE cle='schema_version'").fetchone()
    if ligne is None:
        c.execute("INSERT OR IGNORE INTO meta VALUES ('schema_version', ?)", (str(SCHEMA_VERSION),))
    elif int(ligne["valeur"]) > SCHEMA_VERSION:
        c.close()
        raise MissionError("schema", f"base missions en version {ligne['valeur']}, ce code connaît {SCHEMA_VERSION}")
    return c


@contextlib.contextmanager
def transaction() -> Iterator[sqlite3.Connection]:
    """Une transaction d'écriture : tout ou rien (un COMMIT en échec annule)."""
    c = _connecter()
    try:
        c.execute("BEGIN IMMEDIATE")
        try:
            yield c
            c.execute("COMMIT")
        except BaseException:
            c.execute("ROLLBACK")
            raise
    finally:
        c.close()


def _id(prefixe: str) -> str:
    return f"{prefixe}-{secrets.token_hex(6)}"


def _empreinte(valeur: object) -> str:
    return hashlib.sha256(json.dumps(valeur, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _evenement(c: sqlite3.Connection, tenant_id: str, type_: str, *, mission_id: str | None = None,
               tache_id: str | None = None, now: float, **donnees) -> None:
    c.execute("INSERT INTO evenements (tenant_id, mission_id, tache_id, type, donnees, ts) VALUES (?,?,?,?,?,?)",
              (tenant_id, mission_id, tache_id, type_, json.dumps(donnees, ensure_ascii=False), now))


def _transition(c: sqlite3.Connection, tache: sqlite3.Row | dict, vers: str, *, now: float, raison: str = "",
                **champs) -> None:
    de = tache["statut"]
    if vers not in TRANSITIONS[de]:
        raise TransitionInterdite(de, vers)
    sets = ["statut=?", "maj=?", "raison=?"] + [f"{k}=?" for k in champs]
    c.execute(f"UPDATE taches SET {', '.join(sets)} WHERE id=? AND statut=?",
              (vers, now, raison, *champs.values(), tache["id"], de))
    _evenement(c, tache["tenant_id"], "tache_etat", mission_id=tache["mission_id"], tache_id=tache["id"], now=now,
               de=de, vers=vers, raison=raison)
    if vers in TERMINAUX:
        _clore_mission_si_finie(c, tache["tenant_id"], tache["mission_id"], now)


def _clore_mission_si_finie(c: sqlite3.Connection, tenant_id: str, mission_id: str, now: float) -> None:
    statuts = [r["statut"] for r in c.execute("SELECT statut FROM taches WHERE mission_id=? AND tenant_id=?",
                                              (mission_id, tenant_id))]
    if not statuts or any(s not in TERMINAUX for s in statuts):
        return
    final = SUCCEEDED if all(s == SUCCEEDED for s in statuts) else (
        CANCELLED if all(s == CANCELLED for s in statuts) else FAILED)
    c.execute("UPDATE missions SET statut=?, maj=? WHERE id=? AND tenant_id=?", (final, now, mission_id, tenant_id))
    _evenement(c, tenant_id, "mission_etat", mission_id=mission_id, now=now, vers=final)


# --- Organisations (tenants) ---------------------------------------------------------

def creer_organisation(nom: str, *, id_: str | None = None, niveaux_auto=AUTO_PAR_DEFAUT,
                       now: float | None = None) -> str:
    now = now or time.time()
    niveaux = [n for n in niveaux_auto if n in NIVEAUX and n not in JAMAIS_AUTO]
    oid = id_ or _id("ORG")
    with transaction() as c:
        c.execute("INSERT OR IGNORE INTO organisations VALUES (?,?,?)", (oid, nom, now))
        c.execute("INSERT OR IGNORE INTO reglages_tenant (tenant_id, niveaux_auto) VALUES (?,?)",
                  (oid, json.dumps(niveaux)))
    return oid


def tenant_local() -> str:
    """Le tenant de l'installation personnelle (créé au besoin) : une seule organisation au départ."""
    return creer_organisation("Installation personnelle", id_=TENANT_LOCAL)


def _reglages(c: sqlite3.Connection, tenant_id: str) -> sqlite3.Row:
    r = c.execute("SELECT * FROM reglages_tenant WHERE tenant_id=?", (tenant_id,)).fetchone()
    if r is None:
        raise MissionError("tenant", f"organisation inconnue : {tenant_id}")
    return r


def arret_urgence(tenant_id: str, actif: bool, *, par: str, now: float | None = None) -> None:
    """Interrupteur du plan de contrôle : plus aucune tâche n'est confiée tant qu'il est posé."""
    now = now or time.time()
    with transaction() as c:
        _reglages(c, tenant_id)
        c.execute("UPDATE reglages_tenant SET arret_urgence=? WHERE tenant_id=?", (int(actif), tenant_id))
        _evenement(c, tenant_id, "arret_urgence", now=now, actif=actif, par=par)


def definir_budget_inference(tenant_id: str, centimes: int, *, par: str, now: float | None = None) -> None:
    """Enveloppe d'inférence PAYANTE (API). Zéro par défaut : toute connexion payante est alors refusée."""
    if centimes < 0:
        raise MissionError("budget", "un budget ne peut pas être négatif")
    now = now or time.time()
    with transaction() as c:
        _reglages(c, tenant_id)
        c.execute("UPDATE reglages_tenant SET budget_inference_centimes=? WHERE tenant_id=?", (centimes, tenant_id))
        _evenement(c, tenant_id, "budget_inference", now=now, centimes=centimes, par=par)


# --- Connexions fournisseurs ---------------------------------------------------------

def declarer_connexion(tenant_id: str, fournisseur: str, mode_auth: str, *, payant: bool = False) -> None:
    """Déclare qu'un fournisseur est utilisable par ce tenant. Ne stocke AUCUN identifiant : l'authentification
    reste celle du CLI officiel sur la machine de l'exécutant (ou une clé d'API côté exécutant)."""
    if mode_auth not in ELIGIBILITE:
        raise MissionError("fournisseur", f"mode d'authentification inconnu : {mode_auth}")
    if mode_auth == "api":
        payant = True
    with transaction() as c:
        _reglages(c, tenant_id)
        c.execute("INSERT INTO connexions (tenant_id, fournisseur, mode_auth, payant) VALUES (?,?,?,?) "
                  "ON CONFLICT (tenant_id, fournisseur) DO UPDATE SET mode_auth=excluded.mode_auth, "
                  "payant=excluded.payant, active=1", (tenant_id, fournisseur, mode_auth, int(payant)))


def _router(c: sqlite3.Connection, tache: sqlite3.Row, executant: sqlite3.Row, now: float) -> tuple[str, str]:
    """(fournisseur, '') si une connexion admise existe, sinon ('', raison). Décidé AVANT l'envoi."""
    reglages = _reglages(c, tache["tenant_id"])
    proposes = json.loads(executant["fournisseurs"])
    voulu = tache["fournisseur"]
    candidats = proposes if voulu == "auto" else [voulu] if voulu in proposes else []
    raisons = []
    for f in candidats:
        cx = c.execute("SELECT * FROM connexions WHERE tenant_id=? AND fournisseur=?",
                       (tache["tenant_id"], f)).fetchone()
        if cx is None or not cx["active"]:
            raisons.append(f"{f} : aucune connexion déclarée")
        elif executant["profil"] not in ELIGIBILITE[cx["mode_auth"]]:
            raisons.append(f"{f} : authentification « {cx['mode_auth']} » non admise en {executant['profil']}")
        elif cx["payant"] and reglages["budget_inference_centimes"] - reglages["consomme_centimes"] <= 0:
            raisons.append(f"{f} : connexion payante sans budget d'inférence (zéro par défaut)")
        elif cx["indisponible_jusqua"] > now:
            raisons.append(f"{f} : indisponible ({cx['raison'] or 'quota'})")
        else:
            return f, ""
    return "", "; ".join(raisons) or f"aucun fournisseur compatible ({voulu}) sur cet exécutant"


# --- Missions et tâches ---------------------------------------------------------------

def _valider_spec(spec: dict) -> dict:
    niveau = spec.get("niveau", "L1")
    if niveau not in NIVEAUX:
        raise MissionError("spec", f"niveau inconnu : {niveau}")
    capacites = spec.get("capacites", [])
    if not isinstance(capacites, list) or not all(isinstance(x, str) for x in capacites):
        raise MissionError("spec", "capacités : liste de textes attendue")
    travail = spec.get("travail", {})
    if not isinstance(travail, dict):
        raise MissionError("spec", "travail : objet attendu")
    delai = int(spec.get("delai_s", 600))
    if not 1 <= delai <= 24 * 3600:
        raise MissionError("spec", "délai hors bornes (1 s à 24 h)")
    return {"type": str(spec.get("type") or "analyse"), "niveau": niveau, "capacites": sorted(set(capacites)),
            "fournisseur": str(spec.get("fournisseur") or "auto"), "travail": travail, "delai_s": delai,
            "essais_max": max(1, min(int(spec.get("essais_max", ESSAIS_MAX)), 10)),
            "echeance": spec.get("echeance")}


def _inserer_tache(c: sqlite3.Connection, tenant_id: str, mission_id: str, spec: dict, demandeur: str, now: float,
                   *, parent: sqlite3.Row | None = None) -> str:
    tid = _id("TA")
    c.execute("INSERT INTO taches (id, tenant_id, mission_id, parent_id, profondeur, type, niveau, capacites, "
              "fournisseur, travail, statut, essais_max, delai_s, echeance, cree, maj) "
              "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
              (tid, tenant_id, mission_id, parent["id"] if parent else None,
               parent["profondeur"] + 1 if parent else 0, spec["type"], spec["niveau"],
               json.dumps(spec["capacites"]), spec["fournisseur"], json.dumps(spec["travail"], ensure_ascii=False),
               CREATED, spec["essais_max"], spec["delai_s"], spec["echeance"], now, now))
    _evenement(c, tenant_id, "tache_creee", mission_id=mission_id, tache_id=tid, now=now, type=spec["type"],
               niveau=spec["niveau"])
    tache = c.execute("SELECT * FROM taches WHERE id=?", (tid,)).fetchone()
    _transition(c, tache, VALIDATED, now=now)
    tache = c.execute("SELECT * FROM taches WHERE id=?", (tid,)).fetchone()
    auto = json.loads(_reglages(c, tenant_id)["niveaux_auto"])
    if spec["niveau"] in JAMAIS_AUTO or spec["niveau"] not in auto:
        aid = _id("AP")
        c.execute("INSERT INTO approbations VALUES (?,?,?,?,?,?,?,?,?)",
                  (aid, tenant_id, tid, _empreinte(spec["travail"]), demandeur, "en_attente", None, None, now))
        _transition(c, tache, WAITING_APPROVAL, now=now, raison=f"niveau {spec['niveau']} : approbation humaine ({aid})")
    else:
        _transition(c, tache, QUEUED, now=now, raison=f"niveau {spec['niveau']} admis automatiquement par la politique")
    return tid


def creer_mission(tenant_id: str, objectif: str, taches: list[dict], *, source: str = "cli",
                  demandeur: str = "humain", cle_idempotence: str | None = None, now: float | None = None) -> dict:
    """Crée une mission et ses tâches (politique appliquée). Même clé d'idempotence → même mission, rien de neuf."""
    now = now or time.time()
    if not objectif.strip():
        raise MissionError("spec", "objectif vide")
    if not taches or len(taches) > TACHES_PAR_MISSION_MAX:
        raise MissionError("spec", f"1 à {TACHES_PAR_MISSION_MAX} tâches par mission")
    specs = [_valider_spec(t) for t in taches]
    with transaction() as c:
        _reglages(c, tenant_id)
        if cle_idempotence:
            existante = c.execute("SELECT id FROM missions WHERE tenant_id=? AND cle_idempotence=?",
                                  (tenant_id, cle_idempotence)).fetchone()
            if existante:
                return {"mission_id": existante["id"], "doublon": True}
        mid = _id("MI")
        c.execute("INSERT INTO missions VALUES (?,?,?,?,?,?,?,?,?,?)",
                  (mid, tenant_id, objectif[:2000], source, demandeur, "OPEN", _id("C"), cle_idempotence, now, now))
        _evenement(c, tenant_id, "mission_creee", mission_id=mid, now=now, source=source, objectif=objectif[:200])
        ids = [_inserer_tache(c, tenant_id, mid, s, demandeur, now) for s in specs]
    return {"mission_id": mid, "taches": ids, "doublon": False}


def deleguer(tenant_id: str, parent_id: str, spec: dict, *, demandeur: str, now: float | None = None) -> str:
    """Sous-tâche d'une tâche existante : jamais plus de droits que le parent, profondeur et largeur bornées."""
    now = now or time.time()
    s = _valider_spec(spec)
    with transaction() as c:
        parent = c.execute("SELECT * FROM taches WHERE id=? AND tenant_id=?", (parent_id, tenant_id)).fetchone()
        if parent is None:
            raise MissionError("inconnue", f"tâche inconnue : {parent_id}")
        if parent["statut"] in TERMINAUX:
            raise MissionError("delegation", "la tâche parente est terminée")
        if parent["profondeur"] + 1 > PROFONDEUR_MAX:
            raise MissionError("delegation", f"profondeur de délégation maximale atteinte ({PROFONDEUR_MAX})")
        enfants = c.execute("SELECT COUNT(*) FROM taches WHERE parent_id=?", (parent_id,)).fetchone()[0]
        if enfants >= LARGEUR_MAX:
            raise MissionError("delegation", f"largeur de délégation maximale atteinte ({LARGEUR_MAX})")
        total = c.execute("SELECT COUNT(*) FROM taches WHERE mission_id=?", (parent["mission_id"],)).fetchone()[0]
        if total >= TACHES_PAR_MISSION_MAX:
            raise MissionError("delegation", "nombre maximal de tâches pour cette mission atteint")
        if NIVEAUX.index(s["niveau"]) > NIVEAUX.index(parent["niveau"]):
            raise MissionError("delegation", f"une sous-tâche ne peut pas dépasser le niveau du parent ({parent['niveau']})")
        if not set(s["capacites"]) <= set(json.loads(parent["capacites"])):
            raise MissionError("delegation", "une sous-tâche ne peut pas demander des capacités que le parent n'a pas")
        return _inserer_tache(c, tenant_id, parent["mission_id"], s, demandeur, now, parent=parent)


def decider_approbation(tenant_id: str, approbation_id: str, accord: bool, *, acteur: str, acteur_type: str,
                        now: float | None = None) -> str:
    """Seul un humain décide, jamais le demandeur ni un exécutant ; l'accord vaut pour le travail tel qu'approuvé."""
    now = now or time.time()
    if acteur_type != "humain":
        raise MissionError("approbation", "seul un humain peut décider d'une approbation")
    with transaction() as c:
        ap = c.execute("SELECT * FROM approbations WHERE id=? AND tenant_id=?", (approbation_id, tenant_id)).fetchone()
        if ap is None:
            raise MissionError("inconnue", f"approbation inconnue : {approbation_id}")
        if ap["statut"] != "en_attente":
            raise MissionError("approbation", f"approbation déjà {ap['statut']}")
        if ap["demandeur"] == acteur:
            raise MissionError("approbation", "le demandeur ne peut pas approuver sa propre demande")
        tache = c.execute("SELECT * FROM taches WHERE id=?", (ap["tache_id"],)).fetchone()
        if accord and _empreinte(json.loads(tache["travail"])) != ap["empreinte"]:
            raise MissionError("approbation", "le travail a changé depuis la demande : nouvelle approbation requise")
        statut = "accordee" if accord else "refusee"
        c.execute("UPDATE approbations SET statut=?, decide_par=?, decide=? WHERE id=?",
                  (statut, acteur, now, approbation_id))
        _evenement(c, tenant_id, "approbation", mission_id=tache["mission_id"], tache_id=tache["id"], now=now,
                   approbation_id=approbation_id, decision=statut, par=acteur)
        _transition(c, tache, QUEUED if accord else CANCELLED, now=now, raison=f"approbation {statut} par {acteur}")
        return statut


def annuler_mission(tenant_id: str, mission_id: str, *, par: str, now: float | None = None) -> int:
    now = now or time.time()
    with transaction() as c:
        n = 0
        for t in c.execute("SELECT * FROM taches WHERE mission_id=? AND tenant_id=?", (mission_id, tenant_id)).fetchall():
            if CANCELLED in TRANSITIONS[t["statut"]]:
                _transition(c, t, CANCELLED, now=now, raison=f"mission annulée par {par}")
                n += 1
        return n


# --- Exécutants : enrôlement et authentification --------------------------------------

def enroler_executant(tenant_id: str, nom: str, *, capacites: list[str], fournisseurs: list[str],
                      profil: str = "PERSONAL_LOCAL", version: str = "", systeme: str = "",
                      now: float | None = None) -> tuple[str, str]:
    """Enrôlement initié par le propriétaire de la machine. Renvoie (id, secret) : le secret n'est montré qu'une
    fois, seule son empreinte est gardée. Le tenant est fixé ICI, pas par ce que l'exécutant dira plus tard."""
    if profil not in PROFILS:
        raise MissionError("executant", f"profil inconnu : {profil}")
    now = now or time.time()
    rid, secret = _id("RU"), secrets.token_urlsafe(32)
    with transaction() as c:
        _reglages(c, tenant_id)
        c.execute("INSERT INTO executants (id, tenant_id, nom, secret_empreinte, capacites, fournisseurs, profil, "
                  "version, systeme, cree) VALUES (?,?,?,?,?,?,?,?,?,?)",
                  (rid, tenant_id, nom, hashlib.sha256(secret.encode()).hexdigest(), json.dumps(sorted(set(capacites))),
                   json.dumps(fournisseurs), profil, version, systeme, now))
        _evenement(c, tenant_id, "executant_enrole", now=now, executant_id=rid, nom=nom, profil=profil)
    return rid, secret


def revoquer_executant(tenant_id: str, executant_id: str, *, par: str, now: float | None = None) -> None:
    now = now or time.time()
    with transaction() as c:
        c.execute("UPDATE executants SET revoque=1 WHERE id=? AND tenant_id=?", (executant_id, tenant_id))
        _evenement(c, tenant_id, "executant_revoque", now=now, executant_id=executant_id, par=par)


def _authentifier(c: sqlite3.Connection, executant_id: str, secret: str) -> sqlite3.Row:
    e = c.execute("SELECT * FROM executants WHERE id=?", (executant_id,)).fetchone()
    attendu = e["secret_empreinte"] if e else hashlib.sha256(b"").hexdigest()
    ok = hmac.compare_digest(attendu, hashlib.sha256(secret.encode()).hexdigest())
    if e is None or not ok:
        raise MissionError("authentification", "exécutant inconnu ou secret invalide")
    if e["revoque"]:
        raise MissionError("authentification", "exécutant révoqué")
    return e


# --- Protocole : prise de bail, démarrage, battement, résultat --------------------------

def reclamer(executant_id: str, secret: str, *, now: float | None = None) -> dict | None:
    """Confie la plus ancienne tâche prête du tenant de l'exécutant, ou None. Renvoie l'enveloppe v1."""
    now = now or time.time()
    with transaction() as c:
        e = _authentifier(c, executant_id, secret)
        tenant = e["tenant_id"]
        c.execute("UPDATE executants SET dernier_signe=? WHERE id=?", (now, executant_id))
        if _reglages(c, tenant)["arret_urgence"]:
            return None
        caps = set(json.loads(e["capacites"]))
        for t in c.execute("SELECT * FROM taches WHERE tenant_id=? AND statut=? ORDER BY cree, id",
                           (tenant, QUEUED)).fetchall():
            if not set(json.loads(t["capacites"])) <= caps:
                continue
            fournisseur, raison = _router(c, t, e, now)
            if not fournisseur:
                _transition(c, t, WAITING_PROVIDER, now=now, raison=raison, prochaine_tentative=None)
                continue
            jeton = t["bail_jeton"] + 1
            aid = _id("AT")
            cle = f"{t['id']}:{jeton}"
            c.execute("INSERT INTO tentatives (id, tenant_id, tache_id, executant_id, bail_jeton, fournisseur, "
                      "cle_idempotence, debut) VALUES (?,?,?,?,?,?,?,?)",
                      (aid, tenant, t["id"], executant_id, jeton, fournisseur, cle, now))
            expire = now + BAIL_S
            _transition(c, t, LEASED, now=now, raison=f"bail {jeton} → {executant_id}", bail_executant=executant_id,
                        bail_jeton=jeton, bail_expire=expire, tentative_id=aid, fournisseur_choisi=fournisseur,
                        essais=t["essais"] + 1)
            m = c.execute("SELECT correlation_id FROM missions WHERE id=?", (t["mission_id"],)).fetchone()
            return {
                "version": proto.VERSION, "tenant_id": tenant, "mission_id": t["mission_id"], "tache_id": t["id"],
                "tentative_id": aid, "correlation_id": m["correlation_id"], "capacites": json.loads(t["capacites"]),
                "niveau": t["niveau"], "fournisseur": fournisseur,
                "travail": {"type": t["type"], **json.loads(t["travail"])}, "delai_s": t["delai_s"],
                "limites": {"bail_s": BAIL_S}, "bail_jeton": jeton, "bail_expire": expire,
                "cle_idempotence": cle, "decision_politique": t["raison"] or "file",
            }
    return None


def _tache_du_bail(c: sqlite3.Connection, e: sqlite3.Row, tache_id: str, tentative_id: str, jeton: int,
                   now: float) -> sqlite3.Row:
    t = c.execute("SELECT * FROM taches WHERE id=? AND tenant_id=?", (tache_id, e["tenant_id"])).fetchone()
    if t is None:
        raise MissionError("inconnue", "tâche inconnue")  # même réponse qu'une tâche d'un autre tenant
    if (t["bail_executant"] != e["id"] or t["bail_jeton"] != jeton or t["tentative_id"] != tentative_id
            or t["statut"] not in (LEASED, RUNNING)):
        raise MissionError("perime", "bail périmé : cette tentative n'a plus la tâche")
    if t["bail_expire"] is not None and t["bail_expire"] < now:
        raise MissionError("perime", "bail expiré")
    return t


def demarrer(executant_id: str, secret: str, tache_id: str, tentative_id: str, jeton: int, *,
             now: float | None = None) -> None:
    now = now or time.time()
    with transaction() as c:
        e = _authentifier(c, executant_id, secret)
        t = _tache_du_bail(c, e, tache_id, tentative_id, jeton, now)
        if t["statut"] == LEASED:
            _transition(c, t, RUNNING, now=now, raison=f"démarrée sur {executant_id}")


def battement(executant_id: str, secret: str, tache_id: str, tentative_id: str, jeton: int, *,
              now: float | None = None) -> dict:
    """Prolonge le bail. {"continuer": False} si la tâche a été annulée ou le bail perdu : l'exécutant s'arrête."""
    now = now or time.time()
    try:
        with transaction() as c:
            e = _authentifier(c, executant_id, secret)
            _tache_du_bail(c, e, tache_id, tentative_id, jeton, now)
            c.execute("UPDATE taches SET bail_expire=? WHERE id=?", (now + BAIL_S, tache_id))
            c.execute("UPDATE executants SET dernier_signe=? WHERE id=?", (now, executant_id))
            return {"continuer": True, "bail_expire": now + BAIL_S}
    except MissionError as exc:
        if exc.code == "authentification":
            raise
        return {"continuer": False, "raison": str(exc)}


SECTIONS_EXIGEES = {"analyse_document": ("## Résumé", "## Points clés")}
MARQUES_SUSPECTES = ("<invoke", "<parameter", "</invoke>")  # imitation d'appel d'outil dans un texte


def _verifier_artefact(type_: str, contenu: str) -> tuple[bool, str]:
    """Revue déterministe du plan de contrôle (jamais l'exécutant) : forme du livrable, pas sa vérité."""
    if len(contenu.strip()) < 20:
        return False, "contenu trop court pour constituer un livrable"
    if any(m in contenu for m in MARQUES_SUSPECTES):
        return False, "le texte imite un appel d'outil au lieu de répondre"
    manquantes = [s for s in SECTIONS_EXIGEES.get(type_, ()) if s not in contenu]
    if manquantes:
        return False, f"sections manquantes : {', '.join(manquantes)}"
    return True, "forme attendue, bornée, enregistrée"


def rendre_resultat(executant_id: str, secret: str, resultat: dict, *, now: float | None = None) -> dict:
    """Applique le résultat d'une tentative. Idempotent : un résultat rejoué est acquitté sans nouvel effet."""
    now = now or time.time()
    r = proto.valider_resultat(resultat)
    try:
        with transaction() as c:
            return _appliquer_resultat(c, executant_id, secret, r, now)
    except MissionError as exc:
        if exc.code != "perime":
            raise
        # la transaction est annulée ; le refus, lui, doit rester dans le journal
        with transaction() as c:
            e = _authentifier(c, executant_id, secret)
            _evenement(c, e["tenant_id"], "resultat_perime", tache_id=r["tache_id"], now=now,
                       tentative_id=r["tentative_id"], executant_id=executant_id, raison=str(exc))
        raise


def _appliquer_resultat(c: sqlite3.Connection, executant_id: str, secret: str, r: dict, now: float) -> dict:
    e = _authentifier(c, executant_id, secret)
    tent = c.execute("SELECT * FROM tentatives WHERE cle_idempotence=? AND tenant_id=?",
                     (r["cle_idempotence"], e["tenant_id"])).fetchone()
    if tent is not None and tent["issue"] in proto.ISSUES:
        return {"acquitte": True, "doublon": True, "issue": tent["issue"]}
    t = _tache_du_bail(c, e, r["tache_id"], r["tentative_id"], r["bail_jeton"], now)
    if tent is None or tent["id"] != r["tentative_id"]:
        raise MissionError("perime", "tentative inconnue pour ce bail")
    c.execute("UPDATE tentatives SET fin=?, issue=?, erreur=? WHERE id=?",
              (now, r["issue"], r.get("erreur", ""), tent["id"]))
    if r["issue"] == "reussi":
        if t["statut"] == LEASED:
            _transition(c, t, RUNNING, now=now)
            t = c.execute("SELECT * FROM taches WHERE id=?", (t["id"],)).fetchone()
        factice = bool(r.get("factice")) or tent["fournisseur"] == "factice"
        aid = _id("AR")
        c.execute("INSERT INTO artefacts (id, tenant_id, mission_id, tache_id, tentative_id, type, contenu, empreinte, "
                  "fournisseur, factice, cree) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                  (aid, t["tenant_id"], t["mission_id"], t["id"], tent["id"], "rapport", r["contenu"],
                   hashlib.sha256(r["contenu"].encode()).hexdigest(), tent["fournisseur"], int(factice), now))
        _evenement(c, t["tenant_id"], "artefact", mission_id=t["mission_id"], tache_id=t["id"], now=now,
                   artefact_id=aid, fournisseur=tent["fournisseur"], factice=factice)
        _transition(c, t, REVIEW, now=now, raison="résultat reçu", bail_expire=None)
        t = c.execute("SELECT * FROM taches WHERE id=?", (t["id"],)).fetchone()
        ok, raison = _verifier_artefact(t["type"], r["contenu"])
        c.execute("UPDATE artefacts SET revue=? WHERE id=?", ("acceptee" if ok else "refusee", aid))
        if not ok:  # l'artefact refusé reste consultable ; un nouvel essai est planifié si le budget d'essais le permet
            return {**_echec(c, t, now, f"revue refusée : {raison}"), "issue": "reussi"}
        _transition(c, t, SUCCEEDED, now=now, raison=f"revue : {raison}")
        return {"acquitte": True, "doublon": False, "issue": "reussi", "statut": SUCCEEDED}
    if r["issue"] == "fournisseur_indisponible":
        c.execute("UPDATE connexions SET indisponible_jusqua=?, raison=? WHERE tenant_id=? AND fournisseur=?",
                  (now + INDISPONIBILITE_S, r.get("erreur", "")[:200], t["tenant_id"], tent["fournisseur"]))
        # l'essai ne compte pas : le fournisseur n'a pas pu travailler
        # nouveau routage dès le prochain balayage : un autre fournisseur compatible peut prendre le relais
        _transition(c, t, WAITING_PROVIDER, now=now, raison=f"{tent['fournisseur']} indisponible",
                    essais=max(0, t["essais"] - 1), bail_expire=None, prochaine_tentative=now)
        return {"acquitte": True, "doublon": False, "issue": r["issue"], "statut": WAITING_PROVIDER}
    return _echec(c, t, now, f"échec déclaré : {r.get('erreur', '')[:200]}")


def _echec(c: sqlite3.Connection, t: sqlite3.Row, now: float, raison: str) -> dict:
    if t["essais"] >= t["essais_max"]:
        _transition(c, t, FAILED, now=now, raison=f"{raison} ; essais épuisés ({t['essais']}/{t['essais_max']})",
                    bail_expire=None)
        return {"acquitte": True, "doublon": False, "issue": "echec", "statut": FAILED}
    attente = 10 * 2 ** (t["essais"] - 1)
    _transition(c, t, RETRY_SCHEDULED, now=now, raison=f"{raison} ; nouvel essai dans {attente} s",
                prochaine_tentative=now + attente, bail_expire=None)
    return {"acquitte": True, "doublon": False, "issue": "echec", "statut": RETRY_SCHEDULED}


def recuperer(*, now: float | None = None) -> dict:
    """Balayage du plan de contrôle (démon) : baux expirés, nouveaux essais échus, fournisseurs revenus, échéances."""
    now = now or time.time()
    bilan = {"baux_expires": 0, "relances": 0, "fournisseurs": 0, "expirees": 0}
    with transaction() as c:
        for t in c.execute("SELECT * FROM taches WHERE statut IN (?,?) AND bail_expire < ?",
                           (LEASED, RUNNING, now)).fetchall():
            c.execute("UPDATE tentatives SET fin=?, issue='bail_expire' WHERE id=? AND issue IS NULL",
                      (now, t["tentative_id"]))
            _echec(c, t, now, f"bail {t['bail_jeton']} expiré (exécutant {t['bail_executant']} muet)")
            bilan["baux_expires"] += 1
        for t in c.execute("SELECT * FROM taches WHERE statut=? AND prochaine_tentative <= ?",
                           (RETRY_SCHEDULED, now)).fetchall():
            _transition(c, t, QUEUED, now=now, raison="nouvel essai")
            bilan["relances"] += 1
        for t in c.execute("SELECT * FROM taches WHERE statut=?", (WAITING_PROVIDER,)).fetchall():
            # revenu depuis la mise en attente, ou nouvel essai de routage périodique (connexion ou budget changés)
            revenu = c.execute("SELECT 1 FROM connexions WHERE tenant_id=? AND active=1 AND indisponible_jusqua > ? "
                               "AND indisponible_jusqua <= ?", (t["tenant_id"], t["maj"], now)).fetchone()
            a_rerouter = t["prochaine_tentative"] is not None and t["prochaine_tentative"] <= now
            if revenu or a_rerouter or now - t["maj"] >= REVERIFICATION_S:
                _transition(c, t, QUEUED, now=now, raison="nouveau routage vers un fournisseur",
                            prochaine_tentative=None)
                bilan["fournisseurs"] += 1
        for t in c.execute("SELECT * FROM taches WHERE statut IN (?,?,?,?) AND echeance IS NOT NULL AND echeance < ?",
                           (WAITING_APPROVAL, QUEUED, WAITING_PROVIDER, RETRY_SCHEDULED, now)).fetchall():
            _transition(c, t, EXPIRED, now=now, raison="échéance dépassée")
            bilan["expirees"] += 1
    return bilan


# --- Board -----------------------------------------------------------------------------

TYPES_BOARD = ("note", "texte", "lien", "capture", "image", "pdf", "document")
ANALYSABLES = ("note", "texte", "lien")


def board_ajouter(tenant_id: str, espace: str, type_: str, contenu: str, *, auteur: str, x: float = 0, y: float = 0,
                  now: float | None = None) -> dict:
    """Ajoute un objet au Board. Si le tenant l'autorise, déclenche une mission d'analyse (L1, sans effet externe).
    Le contenu est une DONNÉE : il est transmis à la tâche comme document à analyser, jamais comme consigne."""
    if type_ not in TYPES_BOARD:
        raise MissionError("board", f"type d'objet inconnu : {type_}")
    if not contenu.strip() or len(contenu) > 50_000:
        raise MissionError("board", "contenu vide ou trop long (50 000 caractères au plus)")
    now = now or time.time()
    oid = _id("BO")
    with transaction() as c:
        reglages = _reglages(c, tenant_id)
        c.execute("INSERT INTO board_objets (id, tenant_id, espace, type, contenu, x, y, auteur, cree) "
                  "VALUES (?,?,?,?,?,?,?,?,?)", (oid, tenant_id, espace, type_, contenu, x, y, auteur, now))
        _evenement(c, tenant_id, "board_objet", now=now, objet_id=oid, type=type_, espace=espace)
        declenche = bool(reglages["board_auto_analyse"]) and type_ in ANALYSABLES
    mission = None
    if declenche:
        mission = creer_mission(
            tenant_id, f"Analyser l'objet {oid} du Board « {espace} »",
            [{"type": "analyse_document", "niveau": "L1", "capacites": ["analyse"],
              "travail": {"objet_id": oid, "document": contenu}}],
            source="board", demandeur=f"board:{auteur}", cle_idempotence=f"board:{oid}", now=now)
        with transaction() as c:
            c.execute("UPDATE board_objets SET mission_id=? WHERE id=? AND tenant_id=?",
                      (mission["mission_id"], oid, tenant_id))
    return {"objet_id": oid, "mission_id": mission["mission_id"] if mission else None}


def board(tenant_id: str, espace: str) -> list[dict]:
    """Objets du Board avec l'état de leur mission et les artefacts produits (ce que le Studio affiche)."""
    c = _connecter()
    try:
        out = []
        for o in c.execute("SELECT * FROM board_objets WHERE tenant_id=? AND espace=? ORDER BY cree",
                           (tenant_id, espace)):
            d = dict(o)
            if o["mission_id"]:
                m = c.execute("SELECT statut FROM missions WHERE id=? AND tenant_id=?",
                              (o["mission_id"], tenant_id)).fetchone()
                d["mission_statut"] = m["statut"] if m else None
                d["artefacts"] = [dict(a) for a in c.execute(
                    "SELECT id, tache_id, type, contenu, fournisseur, factice, revue, cree FROM artefacts "
                    "WHERE mission_id=? AND tenant_id=? ORDER BY cree", (o["mission_id"], tenant_id))]
            out.append(d)
        return out
    finally:
        c.close()


# --- Lecture (toujours filtrée par tenant) -----------------------------------------------

def mission(tenant_id: str, mission_id: str) -> dict:
    c = _connecter()
    try:
        m = c.execute("SELECT * FROM missions WHERE id=? AND tenant_id=?", (mission_id, tenant_id)).fetchone()
        if m is None:
            raise MissionError("inconnue", f"mission inconnue : {mission_id}")
        d = dict(m)
        d["taches"] = [dict(t) for t in c.execute("SELECT * FROM taches WHERE mission_id=? AND tenant_id=? "
                                                  "ORDER BY cree, id", (mission_id, tenant_id))]
        d["artefacts"] = [dict(a) for a in c.execute("SELECT * FROM artefacts WHERE mission_id=? AND tenant_id=?",
                                                     (mission_id, tenant_id))]
        d["approbations"] = [dict(a) for a in c.execute(
            "SELECT * FROM approbations WHERE tenant_id=? AND tache_id IN "
            "(SELECT id FROM taches WHERE mission_id=?)", (tenant_id, mission_id))]
        return d
    finally:
        c.close()


def missions(tenant_id: str, limite: int = 20) -> list[dict]:
    c = _connecter()
    try:
        return [dict(m) for m in c.execute("SELECT * FROM missions WHERE tenant_id=? ORDER BY cree DESC LIMIT ?",
                                           (tenant_id, limite))]
    finally:
        c.close()


def approbations_en_attente(tenant_id: str) -> list[dict]:
    c = _connecter()
    try:
        return [dict(a) for a in c.execute(
            "SELECT a.*, t.type, t.niveau, t.travail, t.mission_id FROM approbations a JOIN taches t ON t.id=a.tache_id "
            "WHERE a.tenant_id=? AND a.statut='en_attente' ORDER BY a.cree", (tenant_id,))]
    finally:
        c.close()


def evenements(tenant_id: str, apres: int = 0, limite: int = 200) -> list[dict]:
    """Journal ordonné du tenant après le numéro `apres` : ce que le Studio rejoue à la reconnexion."""
    c = _connecter()
    try:
        return [{**dict(r), "donnees": json.loads(r["donnees"])} for r in c.execute(
            "SELECT * FROM evenements WHERE tenant_id=? AND seq > ? ORDER BY seq LIMIT ?", (tenant_id, apres, limite))]
    finally:
        c.close()


def texte_mission(m: dict) -> str:
    lignes = [f"{m['id']} — {m['statut']}  ({m['source']}, par {m['demandeur']})", f"  {m['objectif']}"]
    for t in m["taches"]:
        f = t["fournisseur_choisi"] or t["fournisseur"]
        lignes.append(f"  · {t['id']} {t['type']} [{t['niveau']}] {t['statut']} — {f}, essai {t['essais']}/"
                      f"{t['essais_max']}" + (f" — {t['raison']}" if t["raison"] else ""))
    for a in m["artefacts"]:
        marque = " (FACTICE : aucune IA réelle)" if a["factice"] else ""
        lignes.append(f"  ▸ artefact {a['id']} de {a['fournisseur']}{marque}, revue {a['revue']} : "
                      f"{a['contenu'][:120]!r}")
    for a in m["approbations"]:
        lignes.append(f"  ⚖ approbation {a['id']} : {a['statut']}")
    return "\n".join(lignes)
