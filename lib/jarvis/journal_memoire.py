"""Journal de mémoire sourcé : une vue paginée des événements existants du projet."""
from __future__ import annotations

from contextlib import closing
import json

from . import board, memoire, missions

TITRES = {
    "blocage": "Blocage", "echec": "Échec", "refus": "Refus",
    "reprise": "Reprise", "resolution": "Résolution", "frustration": "Frustration déclarée",
}
LIMITE_MAX = 100
SEQ_MAX = 2**63 - 1


def _json(backend: str, colonne: str, cle: str) -> str:
    if backend == "postgres":
        return f"(CAST({colonne} AS jsonb) ->> '{cle}')"
    return f"json_extract({colonne}, '$.{cle}')"


def _nature(backend: str) -> str:
    de = _json(backend, "e.donnees", "de")
    vers = _json(backend, "e.donnees", "vers")
    raison = _json(backend, "e.donnees", "raison")
    decision = _json(backend, "e.donnees", "decision")
    return f"""CASE
      WHEN e.type='frustration_declaree' THEN 'frustration'
      WHEN e.type='tache_retenue' THEN 'blocage'
      WHEN e.type='approbation' AND {decision}='refusee' THEN 'refus'
      WHEN e.type='tache_etat' THEN CASE
        WHEN {vers} IN ('WAITING_APPROVAL', 'WAITING_PROVIDER') THEN 'blocage'
        WHEN {de}='REVIEW' AND {vers} IN ('FAILED', 'RETRY_SCHEDULED')
             AND {raison} LIKE 'revue refusée :%' THEN 'refus'
        WHEN {vers} IN ('FAILED', 'RETRY_SCHEDULED', 'EXPIRED') THEN 'echec'
        WHEN {vers}='QUEUED' AND {de} IN ('RETRY_SCHEDULED', 'WAITING_PROVIDER', 'WAITING_APPROVAL') THEN 'reprise'
        WHEN {vers}='LEASED' AND EXISTS (
          SELECT 1 FROM evenements b
          WHERE b.tenant_id=e.tenant_id AND b.mission_id=e.mission_id AND b.tache_id=e.tache_id AND b.type='tache_retenue' AND b.seq<e.seq
            AND b.seq>COALESCE((
              SELECT MAX(p.seq) FROM evenements p WHERE p.tenant_id=e.tenant_id AND p.mission_id=e.mission_id
                AND p.tache_id=e.tache_id AND p.type='tache_etat' AND p.seq<e.seq
            ), 0)
        ) THEN 'reprise'
        WHEN {vers}='SUCCEEDED' THEN 'resolution'
      END
    END"""


def _id(sequence: int) -> str:
    return f"memoire:{sequence}"


def _tentative(c, ligne, donnees: dict):
    identifiant = donnees.get("tentative_id")
    tache = ligne["tache_id"]
    if identifiant and tache:
        return c.execute("SELECT id, fournisseur FROM tentatives WHERE tenant_id=? AND tache_id=? AND id=?",
                         (ligne["tenant_id"], tache, identifiant)).fetchone()
    if not tache or ligne["type"] != "tache_etat" or ligne["nature"] not in ("echec", "refus", "resolution"):
        return None
    # Les anciennes transitions n'indiquent pas l'identifiant. Une clôture horodatée dans la même
    # transaction fournit une preuve exacte, seulement si elle désigne une tentative unique.
    candidats = c.execute("SELECT id, fournisseur FROM tentatives WHERE tenant_id=? AND tache_id=? AND fin=? LIMIT 2",
                          (ligne["tenant_id"], tache, ligne["ts"])).fetchall()
    return candidats[0] if len(candidats) == 1 else None


def _cause(c, ligne, backend: str):
    if not ligne["tache_id"] or ligne["nature"] not in ("reprise", "resolution"):
        return None
    reprise = ", 'reprise'" if ligne["nature"] == "resolution" else ""
    return c.execute(f"""
        SELECT seq FROM (
            SELECT e.seq,{_nature(backend)} AS nature FROM evenements e
            WHERE e.tenant_id=? AND e.mission_id=? AND e.tache_id=? AND e.seq<?
                AND e.type IN ('tache_retenue','tache_etat','approbation')
        ) causes WHERE nature IN ('blocage','echec','refus'{reprise})
        ORDER BY seq DESC LIMIT 1
    """, (ligne["tenant_id"], ligne["mission_id"], ligne["tache_id"], ligne["seq"])).fetchone()


def _entree(c, ligne, backend: str) -> dict:
    donnees = json.loads(ligne["donnees"])
    nature = ligne["nature"]
    tentative = _tentative(c, ligne, donnees)
    preuve = {"mission_id": ligne["mission_id"], "sequence": ligne["seq"]}
    if ligne["tache_id"]:
        preuve["tache_id"] = ligne["tache_id"]
    if ligne["type"] == "approbation" and donnees.get("approbation_id"):
        preuve["approbation_id"] = donnees["approbation_id"]
    factice = donnees.get("factice") is True
    if tentative is not None:
        preuve["tentative_id"] = tentative["id"]
        factice = factice or tentative["fournisseur"] == "factice"
        if not factice:
            artefact = c.execute("SELECT factice FROM artefacts WHERE tenant_id=? AND tentative_id=?",
                                 (ligne["tenant_id"], tentative["id"])).fetchone()
            factice = bool(artefact and artefact["factice"])
    cause = _cause(c, ligne, backend)
    detail = donnees.get("texte") if nature == "frustration" else donnees.get("raison")
    if not detail and nature == "refus":
        detail = "Approbation refusée."
    auteur = donnees.get("auteur") or (donnees.get("par") if ligne["type"] == "approbation" else None)
    return {
        "id": _id(ligne["seq"]), "nature": nature, "titre": TITRES[nature],
        "detail": memoire.expurger(detail or "")[:500], "date": ligne["ts"], "factice": factice,
        "mission_titre": memoire.expurger(ligne["objectif"])[:200], "preuve": preuve,
        **({"auteur": memoire.expurger(auteur)[:120]} if auteur else {}),
        **({"cause_id": _id(cause["seq"])} if cause is not None else {}),
    }


def lire(tenant_id: str, espace: str, *, avant: str | None = None, limite: int = 20, nature: str = "") -> dict:
    """Lit une page plus ancienne. L'événement original et son seq restent la source de vérité."""
    if type(limite) is not int or not 1 <= limite <= LIMITE_MAX:
        raise ValueError(f"limite attendue de 1 à {LIMITE_MAX}")
    if nature and nature not in TITRES:
        raise ValueError("nature inconnue")
    curseur = int(avant) if avant is not None else SEQ_MAX
    if not 0 < curseur <= SEQ_MAX:
        raise ValueError("curseur invalide")
    espace = board.nom_espace(espace)
    backend = missions.backend().nom
    # La carte (même retirée du Board) matérialise l'appartenance au projet. Un événement portant
    # déjà son espace n'apparaît que dans celui-ci. Les autres événements sans preuve de projet sont exclus.
    with closing(missions._connecter(tenant_id)) as c:
        lignes = c.execute(f"""
          WITH journal AS (
            SELECT e.seq,e.tenant_id,e.mission_id,e.tache_id,e.type,e.donnees,e.ts,m.objectif,{_nature(backend)} AS nature
            FROM evenements e JOIN missions m ON m.id=e.mission_id AND m.tenant_id=e.tenant_id
            WHERE e.tenant_id=? AND e.seq<? AND e.type IN ('tache_etat','tache_retenue','approbation','frustration_declaree')
              AND (e.espace=? OR (e.espace IS NULL AND EXISTS (
                SELECT 1 FROM board_objets o
                WHERE o.tenant_id=e.tenant_id AND o.mission_id=e.mission_id AND o.espace=?
              )))
          )
          SELECT * FROM journal WHERE nature IS NOT NULL
          {"AND nature=?" if nature else ""} ORDER BY seq DESC LIMIT ?
        """, (tenant_id, curseur, espace, espace, *((nature,) if nature else ()), limite + 1)).fetchall()
        return {
            "entrees": [_entree(c, e, backend) for e in lignes[:limite]],
            "avant": str(lignes[limite - 1]["seq"]) if len(lignes) > limite else None,
        }
