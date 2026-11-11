"""Bibliothèque de références du Board : le premier RAG de Jarvis, local d'abord.

Une référence est un site capturé (captures d'écran, texte par sections, palette, polices, structure, liens), un
texte, ou une carte existante du Board. Tout reste sur le poste : base des missions (SQLite, ou PostgreSQL avec
RLS), fichiers dans le magasin d'assets du Board (dédoublonnés par sha256). Aucun fournisseur d'IA n'est requis :
- recherche par mots : BM25 de SQLite FTS5 (désaccentuée, préfixes), avec repli en Python pur si FTS5 manque ;
- recherche vectorielle OPTIONNELLE (interface `rag.Embarqueur`, Ollama local) ; absente ou en panne, la recherche
  continue en BM25 seul, sans erreur ; fusion des deux classements par RRF ;
- chaque fragment garde `modele / dimension / version_index` de son vecteur : tout se ré-indexe avec un autre modèle.

Sécurité : `tenant_id` sur chaque ligne et dans chaque requête ; le contenu capturé est une DONNÉE non fiable
(marquée comme telle dans chaque résultat), jamais une consigne ; la capture passe par capture_site.py (anti-SSRF).
États d'une référence : en_attente → capture → indexation → prete, ou echec (avec la raison).
"""

from __future__ import annotations

import json
import shutil
import tempfile
import threading
import time
from pathlib import Path

from . import apercus, capture_site, config, missions, rag
from .missions import MissionError

ETATS = ("en_attente", "capture", "indexation", "prete", "echec")
EN_COURS = ("en_attente", "capture", "indexation")
TYPES = ("site", "texte", "carte")
ROLES_FICHIERS = capture_site.FICHIERS
COLLECTION_MAX, ETIQUETTE_MAX, ETIQUETTES_MAX = 80, 40, 12
TEXTE_MAX = 300_000
CANDIDATS = 50              # fragments retenus par moteur avant fusion
VECTEURS_MAX = 5000         # fragments comparés par cosinus en Python pur (au-delà : les plus récents)
REPLI_MAX = 5000            # fragments parcourus par le BM25 de repli
FILE_MAX = 20               # captures en attente ou en cours, au plus
INTERROMPUE_S = 600         # une capture « en cours » plus vieille que cela a été interrompue (arrêt du Studio)
PANNE_S = 60                # après une panne de l'embarqueur, on ne le sollicite plus pendant ce délai
AVERTISSEMENT = capture_site.AVERTISSEMENT

_SCHEMA = (
    """CREATE TABLE IF NOT EXISTS board_references (
        id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, type TEXT NOT NULL, source TEXT NOT NULL,
        url_finale TEXT NOT NULL DEFAULT '', titre TEXT NOT NULL DEFAULT '', description TEXT NOT NULL DEFAULT '',
        collection TEXT NOT NULL DEFAULT '', etiquettes TEXT NOT NULL DEFAULT '[]', meta TEXT NOT NULL DEFAULT '{}',
        contenu TEXT NOT NULL DEFAULT '[]', statut TEXT NOT NULL, raison TEXT NOT NULL DEFAULT '',
        empreinte TEXT NOT NULL DEFAULT '', supprime INTEGER NOT NULL DEFAULT 0, version INTEGER NOT NULL DEFAULT 1,
        auteur TEXT NOT NULL, cree REAL NOT NULL, maj REAL NOT NULL, capture_le REAL)""",
    "CREATE INDEX IF NOT EXISTS board_references_tenant ON board_references (tenant_id, supprime, collection, cree)",
    """CREATE TABLE IF NOT EXISTS board_reference_fragments (
        id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, reference_id TEXT NOT NULL, position INTEGER NOT NULL,
        section TEXT NOT NULL DEFAULT '', niveau INTEGER NOT NULL DEFAULT 0, texte TEXT NOT NULL,
        texte_norm TEXT NOT NULL, zone TEXT, vecteur BLOB, modele TEXT NOT NULL DEFAULT '',
        dimension INTEGER NOT NULL DEFAULT 0, version_index INTEGER NOT NULL DEFAULT 1, cree REAL NOT NULL,
        actif INTEGER NOT NULL DEFAULT 1)""",
    "CREATE INDEX IF NOT EXISTS board_reference_fragments_ref ON board_reference_fragments (tenant_id, reference_id, position)",
    """CREATE TABLE IF NOT EXISTS board_reference_fichiers (
        tenant_id TEXT NOT NULL, reference_id TEXT NOT NULL, role TEXT NOT NULL, asset_id TEXT NOT NULL,
        sha256 TEXT NOT NULL, largeur INTEGER NOT NULL DEFAULT 0, hauteur INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (tenant_id, reference_id, role))""",
)
_FTS = ("CREATE VIRTUAL TABLE IF NOT EXISTS board_reference_fts USING fts5(texte, section, titre, "
        "fragment_id UNINDEXED, reference_id UNINDEXED, tenant_id UNINDEXED, "
        "tokenize='unicode61 remove_diacritics 2', prefix='2 3 4')")

FORCER_REPLI = False        # tests : se comporter comme si FTS5 manquait
_embarqueur_force: list = []    # tests : [embarqueur] remplace la configuration ([None] = désactivé)
_panne_jusqua = 0.0
_capture_verrou = threading.Semaphore(1)    # une seule capture (un seul Chromium) à la fois
_fils: list[threading.Thread] = []
_fils_verrou = threading.Lock()


# --- Base -----------------------------------------------------------------------------------------------

def _assurer(c) -> bool:
    """Crée les tables au premier usage (SQLite). Renvoie True si l'index FTS5 est utilisable.
    Sur PostgreSQL, les tables viennent de services/controle_pg/schema.sql et la recherche par mots passe par le
    repli Python (la colonne tsvector du schéma est prête pour une recherche native)."""
    if missions.backend().nom != "sqlite":
        return False
    presentes = {r["name"] for r in c.execute(
        "SELECT name FROM sqlite_master WHERE name IN ('board_references', 'board_reference_fts')")}
    if "board_references" not in presentes:
        for instruction in _SCHEMA:
            c.execute(instruction)
    if "board_reference_fts" in presentes:
        return not FORCER_REPLI
    if FORCER_REPLI:
        return False
    try:
        c.execute(_FTS)
    except Exception:  # noqa: BLE001 — SQLite compilé sans FTS5 : repli en Python, sans erreur
        return False
    # index créé après coup (base venue d'un Python sans FTS5) : on y verse les fragments existants
    c.execute("INSERT INTO board_reference_fts (texte, section, titre, fragment_id, reference_id, tenant_id) "
              "SELECT f.texte_norm, f.section, r.titre, f.id, f.reference_id, f.tenant_id "
              "FROM board_reference_fragments f JOIN board_references r ON r.id = f.reference_id WHERE f.actif=1")
    return True


class _Acces:
    def __init__(self, tenant_id: str, ecriture: bool):
        self.tenant_id, self.ecriture = tenant_id, ecriture

    def __enter__(self):
        if self.ecriture:
            self._tx = missions.transaction(self.tenant_id)
            self.c = self._tx.__enter__()
        else:
            self.c = missions._connecter(self.tenant_id)
        try:
            self.fts = _assurer(self.c)
        except BaseException as exc:
            self.__exit__(type(exc), exc, exc.__traceback__)
            raise
        return self

    def __exit__(self, *exc):
        if self.ecriture:
            return self._tx.__exit__(*exc)
        self.c.close()
        return False


def _ecrire(tenant_id: str) -> _Acces:
    return _Acces(tenant_id, True)


def _lire(tenant_id: str) -> _Acces:
    return _Acces(tenant_id, False)


def fts5_disponible(tenant_id: str) -> bool:
    with _lire(tenant_id) as a:
        return a.fts


# --- Embarqueur -----------------------------------------------------------------------------------------

def utiliser_embarqueur(*embarqueur) -> None:
    """Tests et intégrations : `utiliser_embarqueur(e)` l'impose, `utiliser_embarqueur(None)` le désactive,
    `utiliser_embarqueur()` revient à la configuration du propriétaire."""
    global _panne_jusqua
    _embarqueur_force[:] = list(embarqueur[:1])
    _panne_jusqua = 0.0


def embarqueur():
    return _embarqueur_force[0] if _embarqueur_force else rag.embarqueur_configure()


def etat_moteur(tenant_id: str) -> dict:
    """Ce qui sert réellement à la recherche, sans rien promettre de plus."""
    e = embarqueur()
    with _lire(tenant_id) as a:
        n = a.c.execute("SELECT COUNT(*) AS n FROM board_reference_fragments WHERE tenant_id=? AND actif=1 AND vecteur IS NOT NULL",
                        (tenant_id,)).fetchone()["n"]
    return {"mots": "fts5" if a.fts else "python", "vecteurs": bool(e), "modele": getattr(e, "modele", "") if e else "",
            "fragments_vectorises": n, "capture": capture_site.disponible()[0]}


# --- Valeurs propres ------------------------------------------------------------------------------------

def _court(v, n: int) -> str:
    return " ".join("".join(ch for ch in str(v or "") if ch.isprintable() or ch == " ").split())[:n]


def _etiquettes(v) -> list[str]:
    if isinstance(v, str):
        v = v.split(",")
    if not isinstance(v, (list, tuple)):
        return []
    propres = [_court(e, ETIQUETTE_MAX).lower() for e in v if isinstance(e, str)]
    return list(dict.fromkeys(e for e in propres if e))[:ETIQUETTES_MAX]


def _json(v, defaut):
    try:
        return json.loads(v) if v else defaut
    except (TypeError, ValueError):
        return defaut


def _ligne(c, tenant_id: str, reference_id: str, *, supprimees: bool = False):
    r = c.execute("SELECT * FROM board_references WHERE id=? AND tenant_id=?", (reference_id, tenant_id)).fetchone()
    if r is None or (r["supprime"] and not supprimees):
        raise MissionError("inconnue", f"référence inconnue : {reference_id}")
    return r


def _fichiers(c, tenant_id: str, ids: list[str]) -> dict[str, dict]:
    sortie: dict[str, dict] = {i: {} for i in ids}
    for i in range(0, len(ids), 400):
        lot = ids[i:i + 400]
        marques = ",".join("?" * len(lot))
        for f in c.execute(f"SELECT * FROM board_reference_fichiers WHERE tenant_id=? AND reference_id IN ({marques})",
                           (tenant_id, *lot)):
            sortie[f["reference_id"]][f["role"]] = {"asset_id": f["asset_id"], "url": f"/api/v2/fichiers/{f['asset_id']}",
                                                    "sha256": f["sha256"], "largeur": f["largeur"], "hauteur": f["hauteur"]}
    return sortie


def _publique(r, fichiers: dict, n_fragments: int | None = None) -> dict:
    meta = _json(r["meta"], {})
    vignette = fichiers.get("bureau_vue") or {}
    return {"id": r["id"], "type": r["type"], "source": r["source"], "url": r["url_finale"] or (r["source"] if r["type"] == "site" else ""),
            "titre": r["titre"] or (r["source"] if r["type"] == "site" else "Sans titre"), "description": r["description"],
            "collection": r["collection"], "etiquettes": _json(r["etiquettes"], []), "statut": r["statut"],
            "raison": r["raison"], "supprime": bool(r["supprime"]), "version": r["version"], "cree": r["cree"],
            "maj": r["maj"], "capture_le": r["capture_le"], "vignette_url": vignette.get("url"),
            "palette": meta.get("palette") or [], "polices": (meta.get("polices") or {}).get("roles") or {},
            **({"fragments": n_fragments} if n_fragments is not None else {})}


# --- Création -------------------------------------------------------------------------------------------

def ajouter(tenant_id: str, *, url: str = "", texte: str = "", objet_id: str = "", titre: str = "",
            collection: str = "", etiquettes=(), auteur: str, now: float | None = None) -> dict:
    """Crée une référence. Un site reste « en_attente » (la capture est lancée par `planifier` ou `traiter`) ;
    un texte ou une carte du Board est indexé tout de suite. Le même site dans la même collection n'est pas
    dupliqué : la référence existante est rendue avec `deja: True`."""
    now = now or time.time()
    collection, tags, titre = _court(collection, COLLECTION_MAX), _etiquettes(etiquettes), _court(titre, 200)
    fournis = [bool(url), bool(texte and texte.strip()), bool(objet_id)]
    if sum(fournis) != 1:
        raise MissionError("reference", "donne une adresse (url), un texte, ou une carte du Board (objet_id) — un seul")
    rid = missions._id("RF")
    if url:
        try:
            source = apercus.normaliser(str(url))
        except apercus.ApercuRefuse as exc:
            raise MissionError("reference", str(exc)) from exc
        with _ecrire(tenant_id) as a:
            existante = a.c.execute("SELECT id FROM board_references WHERE tenant_id=? AND type='site' AND source=? "
                                    "AND collection=? AND supprime=0", (tenant_id, source, collection)).fetchone()
            if existante:
                return {**voir(tenant_id, existante["id"], _acces=a), "deja": True}
            en_file = a.c.execute("SELECT COUNT(*) AS n FROM board_references WHERE tenant_id=? AND supprime=0 AND statut IN "
                                  "('en_attente','capture','indexation')", (tenant_id,)).fetchone()["n"]
            if en_file >= FILE_MAX:
                raise MissionError("conflit", f"{FILE_MAX} captures sont déjà en file : attends qu'elles se terminent")
            a.c.execute("INSERT INTO board_references (id, tenant_id, type, source, titre, collection, etiquettes, statut, "
                        "auteur, cree, maj) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                        (rid, tenant_id, "site", source, titre, collection, json.dumps(tags, ensure_ascii=False),
                         "en_attente", auteur, now, now))
            missions._evenement(a.c, tenant_id, "reference_etat", now=now, reference_id=rid, statut="en_attente")
        return voir(tenant_id, rid)
    asset = None
    if objet_id:
        with _lire(tenant_id) as a:
            o = a.c.execute("SELECT * FROM board_objets WHERE id=? AND tenant_id=? AND supprime=0",
                            (str(objet_id), tenant_id)).fetchone()
        if o is None:
            raise MissionError("inconnue", f"carte inconnue : {objet_id}")
        meta_o = _json(o["meta"], {})
        texte = "\n\n".join(x for x in (str(meta_o.get("description") or ""), o["contenu"] or "",
                                        str(meta_o.get("jarvis_resume") or "")) if x.strip())
        titre = titre or _court(meta_o.get("titre"), 200) or _court(o["contenu"], 80)
        source, type_, asset = f"board:{o['id']}", "carte", o["asset_id"]
        if not texte.strip():
            texte = titre
    else:
        source, type_ = "texte", "texte"
    if not texte.strip() or len(texte) > TEXTE_MAX:
        raise MissionError("reference", f"texte vide ou trop long ({TEXTE_MAX} caractères au plus)")
    sections = rag.sections_de_texte(texte)
    titre = titre or next((s["titre"] for s in sections if s["titre"]), "") or _court(texte, 80)
    with _ecrire(tenant_id) as a:
        a.c.execute("INSERT INTO board_references (id, tenant_id, type, source, titre, description, collection, etiquettes, "
                    "contenu, statut, auteur, cree, maj, capture_le, empreinte) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (rid, tenant_id, type_, source, titre, _court(texte, 300), collection,
                     json.dumps(tags, ensure_ascii=False), json.dumps(sections, ensure_ascii=False), "indexation",
                     auteur, now, now, now, missions._empreinte(sections)))
        if asset:
            ligne = a.c.execute("SELECT * FROM board_assets WHERE id=? AND tenant_id=?", (asset, tenant_id)).fetchone()
            if ligne is not None and str(ligne["mime"]).startswith("image/"):
                dims = _json(ligne["meta"], {})
                a.c.execute("INSERT INTO board_reference_fichiers (tenant_id, reference_id, role, asset_id, sha256, largeur, hauteur) "
                            "VALUES (?,?,?,?,?,?,?)",
                            (tenant_id, rid, "bureau_vue", asset, ligne["sha256"], int(dims.get("largeur") or 0),
                             int(dims.get("hauteur") or 0)))
        _indexer(a, tenant_id, rid, titre, sections, now)
        _etat(a.c, tenant_id, rid, "prete", now=now)
    _vectoriser(tenant_id, rid)
    return voir(tenant_id, rid)


def _etat(c, tenant_id: str, reference_id: str, statut: str, *, raison: str = "", now: float | None = None) -> None:
    now = now or time.time()
    c.execute("UPDATE board_references SET statut=?, raison=?, maj=?, version=version+1 WHERE id=? AND tenant_id=?",
              (statut, raison[:300], now, reference_id, tenant_id))
    missions._evenement(c, tenant_id, "reference_etat", now=now, reference_id=reference_id, statut=statut)


# --- Indexation -----------------------------------------------------------------------------------------

def _indexer(a: _Acces, tenant_id: str, reference_id: str, titre: str, sections: list[dict], now: float) -> int:
    """Remplace les fragments d'une référence (et leurs lignes d'index). Les vecteurs sont à recalculer."""
    c = a.c
    if missions.backend().nom == "sqlite":
        c.execute("DELETE FROM board_reference_fragments WHERE tenant_id=? AND reference_id=?", (tenant_id, reference_id))
    else:  # sur PostgreSQL le rôle applicatif ne supprime jamais : les anciens fragments sont désactivés
        c.execute("UPDATE board_reference_fragments SET actif=0, vecteur=NULL WHERE tenant_id=? AND reference_id=? AND actif=1",
                  (tenant_id, reference_id))
    if a.fts:
        c.execute("DELETE FROM board_reference_fts WHERE tenant_id=? AND reference_id=?", (tenant_id, reference_id))
    fragments = rag.decouper(sections)
    for f in fragments:
        fid = missions._id("FR")
        norme = rag.normaliser(f["texte"])
        c.execute("INSERT INTO board_reference_fragments (id, tenant_id, reference_id, position, section, niveau, texte, "
                  "texte_norm, zone, version_index, cree) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                  (fid, tenant_id, reference_id, f["position"], f["section"], f["niveau"], f["texte"], norme,
                   json.dumps(f["zone"]) if f["zone"] else None, rag.VERSION_INDEX, now))
        if a.fts:
            c.execute("INSERT INTO board_reference_fts (texte, section, titre, fragment_id, reference_id, tenant_id) "
                      "VALUES (?,?,?,?,?,?)", (norme, rag.normaliser(f["section"]), rag.normaliser(titre), fid,
                                               reference_id, tenant_id))
    return len(fragments)


def _vectoriser(tenant_id: str, reference_id: str) -> dict:
    """Calcule les vecteurs des fragments si un embarqueur est branché. Une panne n'empêche rien : la référence
    reste trouvable par mots, et `reindexer` rattrapera les vecteurs plus tard."""
    e = embarqueur()
    if e is None:
        return {"vecteurs": 0, "etat": "desactive"}
    with _lire(tenant_id) as a:
        lignes = a.c.execute("SELECT id, section, texte FROM board_reference_fragments WHERE tenant_id=? AND "
                             "reference_id=? AND actif=1 ORDER BY position", (tenant_id, reference_id)).fetchall()
    if not lignes:
        return {"vecteurs": 0, "etat": "vide"}
    try:
        vecteurs = e.embarquer([(f"{l['section']}\n{l['texte']}" if l["section"] else l["texte"]) for l in lignes])
        if len(vecteurs) != len(lignes) or len({len(v) for v in vecteurs}) != 1:
            raise rag.EmbarqueurIndisponible("nombre ou dimension de vecteurs inattendu")
    except Exception as exc:  # noqa: BLE001 — tout embarqueur enfichable peut échouer à sa façon
        return {"vecteurs": 0, "etat": "indisponible", "raison": str(exc)[:200]}
    with _ecrire(tenant_id) as a:
        for l, v in zip(lignes, vecteurs):
            a.c.execute("UPDATE board_reference_fragments SET vecteur=?, modele=?, dimension=? WHERE id=? AND tenant_id=?",
                        (rag.emballer(v), str(e.modele)[:120], len(v), l["id"], tenant_id))
    return {"vecteurs": len(vecteurs), "etat": "ok", "modele": e.modele, "dimension": len(vecteurs[0])}


def reindexer(tenant_id: str, reference_id: str | None = None) -> dict:
    """Redécoupe et ré-indexe (mots puis vecteurs) une référence, ou toutes. À lancer après un changement de modèle
    d'embarquement : les anciens vecteurs sont effacés, les nouveaux portent le nouveau modèle."""
    with _lire(tenant_id) as a:
        if reference_id:
            ids = [_ligne(a.c, tenant_id, reference_id)["id"]]
        else:
            ids = [r["id"] for r in a.c.execute("SELECT id FROM board_references WHERE tenant_id=? AND supprime=0 "
                                                "AND statut='prete' ORDER BY cree", (tenant_id,))]
    bilan = {"references": 0, "fragments": 0, "vecteurs": 0, "etat_vecteurs": "desactive"}
    for rid in ids:
        now = time.time()
        with _ecrire(tenant_id) as a:
            r = _ligne(a.c, tenant_id, rid)
            if r["statut"] in ("en_attente", "capture"):
                raise MissionError("conflit", "capture en cours : attends qu'elle se termine")
            if r["statut"] == "echec" and r["contenu"] in ("", "[]"):
                raise MissionError("reference", "rien à ré-indexer : relance la capture")
            bilan["fragments"] += _indexer(a, tenant_id, rid, r["titre"], _json(r["contenu"], []), now)
            _etat(a.c, tenant_id, rid, "prete", now=now)
        v = _vectoriser(tenant_id, rid)
        bilan["references"] += 1
        bilan["vecteurs"] += v["vecteurs"]
        bilan["etat_vecteurs"] = v["etat"] if v["etat"] != "vide" else bilan["etat_vecteurs"]
    return bilan


# --- Capture d'un site ----------------------------------------------------------------------------------

def traiter(tenant_id: str, reference_id: str, *, autoriser_prives: bool = False, exceptions=(), pilote=None) -> dict:
    """Capture puis indexe une référence de type site (appel bloquant). Ne lève pas pour un échec de capture :
    l'état passe à « echec » avec la raison. Renvoie la référence."""
    with _ecrire(tenant_id) as a:
        r = _ligne(a.c, tenant_id, reference_id)
        if r["type"] != "site":
            raise MissionError("reference", "seul un site se capture")
        if r["statut"] in ("capture", "indexation") and time.time() - r["maj"] < INTERROMPUE_S:
            raise MissionError("conflit", "capture déjà en cours")
        _etat(a.c, tenant_id, reference_id, "capture")
    dossier = Path(tempfile.mkdtemp(prefix="capture-", dir=_dossier_travail()))
    try:
        with _capture_verrou:
            capture = capture_site.capturer(r["source"], dossier, autoriser_prives=autoriser_prives,
                                            exceptions=exceptions, pilote=pilote)
        _enregistrer_capture(tenant_id, reference_id, r, capture)
    except capture_site.CaptureRefusee as exc:
        with _ecrire(tenant_id) as a:
            _etat(a.c, tenant_id, reference_id, "echec", raison=str(exc))
    except Exception as exc:  # noqa: BLE001 — un fil de capture ne doit jamais laisser une référence « en cours »
        with _ecrire(tenant_id) as a:
            _etat(a.c, tenant_id, reference_id, "echec", raison=f"erreur interne ({type(exc).__name__})")
    finally:
        shutil.rmtree(dossier, ignore_errors=True)
    return voir(tenant_id, reference_id, supprimees=True)


def _dossier_travail() -> Path:
    d = config.STATE_DIR / "board_assets" / "captures"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _enregistrer_capture(tenant_id: str, reference_id: str, r, capture: dict) -> None:
    from . import board
    fichiers = {}
    for role, f in capture["fichiers"].items():  # magasin d'assets du Board : dédoublonnage par sha256
        asset = board.enregistrer_fichier(tenant_id, f["chemin"], f"{role}-{reference_id}.jpg", auteur="reference")
        fichiers[role] = (asset["id"], f["sha256"], f["largeur"], f["hauteur"])
    page = fichiers.get("bureau_page", (None,))[0]
    sections = []
    if capture["titre"] or capture["description"]:
        sections.append({"titre": "Présentation", "niveau": 0,
                         "texte": "\n".join(x for x in (capture["titre"], capture["description"]) if x), "zone": None})
    for s in capture["sections"]:
        zone = {**s["zone"], "asset_id": page, "largeur": capture_site.GABARITS["bureau"][0]} if page else None
        sections.append({"titre": s["titre"], "niveau": s["niveau"], "texte": s["texte"], "zone": zone})
    meta = {k: capture[k] for k in ("palette", "couleurs_css", "polices", "structure", "liens", "langue",
                                    "statut_http", "bac_a_sable", "reseau")}
    meta["tronquee"] = any(f.get("tronquee") for f in capture["fichiers"].values())
    titre = r["titre"] or capture["titre"] or capture["url_finale"]
    now = time.time()
    with _ecrire(tenant_id) as a:
        a.c.execute("UPDATE board_references SET titre=?, description=?, url_finale=?, meta=?, contenu=?, empreinte=?, "
                    "capture_le=?, maj=? WHERE id=? AND tenant_id=?",
                    (titre, capture["description"], capture["url_finale"], json.dumps(meta, ensure_ascii=False),
                     json.dumps(sections, ensure_ascii=False),
                     missions._empreinte({"sections": sections, "fichiers": {k: v[1] for k, v in fichiers.items()}}),
                     capture["capture_le"], now, reference_id, tenant_id))
        for role, (asset_id, sha, largeur, hauteur) in fichiers.items():
            a.c.execute("INSERT INTO board_reference_fichiers (tenant_id, reference_id, role, asset_id, sha256, largeur, hauteur) "
                        "VALUES (?,?,?,?,?,?,?) ON CONFLICT (tenant_id, reference_id, role) DO UPDATE SET "
                        "asset_id=excluded.asset_id, sha256=excluded.sha256, largeur=excluded.largeur, hauteur=excluded.hauteur",
                        (tenant_id, reference_id, role, asset_id, sha, largeur, hauteur))
        _etat(a.c, tenant_id, reference_id, "indexation", now=now)
    with _ecrire(tenant_id) as a:
        _indexer(a, tenant_id, reference_id, titre, sections, now)
    _vectoriser(tenant_id, reference_id)
    with _ecrire(tenant_id) as a:
        _etat(a.c, tenant_id, reference_id, "prete")


def planifier(tenant_id: str, reference_id: str, **options) -> None:
    """Lance `traiter` hors du fil appelant (la requête HTTP répond tout de suite ; l'état se consulte)."""
    fil = threading.Thread(target=_traiter_sans_bruit, args=(tenant_id, reference_id), kwargs=options,
                           name=f"capture-{reference_id}", daemon=True)
    with _fils_verrou:
        _fils[:] = [f for f in _fils if f.is_alive()] + [fil]
    fil.start()


def _traiter_sans_bruit(tenant_id: str, reference_id: str, **options) -> None:
    try:
        traiter(tenant_id, reference_id, **options)
    except Exception:  # noqa: BLE001 — référence supprimée entre-temps, base fermée à l'arrêt : rien à signaler
        pass


def attendre(delai_s: float = 30.0) -> bool:
    """Attend la fin des captures planifiées (tests, arrêt propre). True si tout est fini."""
    fin = time.time() + delai_s
    with _fils_verrou:
        fils = list(_fils)
    for f in fils:
        f.join(max(0.0, fin - time.time()))
    return not any(f.is_alive() for f in fils)


def recapturer(tenant_id: str, reference_id: str) -> dict:
    """Remet un site en file pour une nouvelle capture (l'appelant enchaîne avec `planifier` ou `traiter`)."""
    with _ecrire(tenant_id) as a:
        r = _ligne(a.c, tenant_id, reference_id)
        if r["type"] != "site":
            raise MissionError("reference", "seul un site se recapture")
        if r["statut"] in ("capture", "indexation") and time.time() - r["maj"] < INTERROMPUE_S:
            raise MissionError("conflit", "capture déjà en cours")
        _etat(a.c, tenant_id, reference_id, "en_attente")
    return voir(tenant_id, reference_id)


def _clore_interrompues(c, tenant_id: str, now: float) -> None:
    for r in c.execute("SELECT id FROM board_references WHERE tenant_id=? AND statut IN ('en_attente','capture','indexation') "
                       "AND maj < ?", (tenant_id, now - INTERROMPUE_S)).fetchall():
        _etat(c, tenant_id, r["id"], "echec", raison="capture interrompue (Studio arrêté ?) : relance-la", now=now)


# --- Lecture --------------------------------------------------------------------------------------------

def lister(tenant_id: str, *, collection: str | None = None, etiquette: str | None = None, q: str = "",
           supprimees: bool = False, limite: int = 200) -> dict:
    """Références du tenant (les plus récentes d'abord) + facettes (collections, étiquettes) calculées sur tout."""
    now = time.time()
    with _lire(tenant_id) as a:
        perimees = a.c.execute("SELECT 1 FROM board_references WHERE tenant_id=? AND statut IN "
                               "('en_attente','capture','indexation') AND maj < ?", (tenant_id, now - INTERROMPUE_S)).fetchone()
    if perimees:
        with _ecrire(tenant_id) as a:
            _clore_interrompues(a.c, tenant_id, now)
    with _lire(tenant_id) as a:
        lignes = a.c.execute("SELECT * FROM board_references WHERE tenant_id=? AND supprime=? ORDER BY cree DESC, id",
                             (tenant_id, 1 if supprimees else 0)).fetchall()
        comptes = {r["reference_id"]: r["n"] for r in a.c.execute(
            "SELECT reference_id, COUNT(*) AS n FROM board_reference_fragments WHERE tenant_id=? AND actif=1 GROUP BY reference_id",
            (tenant_id,))}
        collections: dict[str, int] = {}
        tags: dict[str, int] = {}
        for r in lignes:
            collections[r["collection"]] = collections.get(r["collection"], 0) + 1
            for t in _json(r["etiquettes"], []):
                tags[t] = tags.get(t, 0) + 1
        filtre = rag.normaliser(q or "").strip()
        retenues = [r for r in lignes
                    if (collection is None or r["collection"] == collection)
                    and (not etiquette or etiquette.lower() in _json(r["etiquettes"], []))
                    and (not filtre or filtre in rag.normaliser(f"{r['titre']} {r['source']} {r['description']}"))]
        retenues = retenues[:max(1, min(500, int(limite)))]
        fichiers = _fichiers(a.c, tenant_id, [r["id"] for r in retenues])
    return {"references": [_publique(r, fichiers[r["id"]], comptes.get(r["id"], 0)) for r in retenues],
            "total": len(lignes),
            "collections": [{"nom": k, "n": v} for k, v in sorted(collections.items(), key=lambda kv: (kv[0] == "", kv[0].lower()))],
            "etiquettes": [{"nom": k, "n": v} for k, v in sorted(tags.items(), key=lambda kv: (-kv[1], kv[0]))]}


def voir(tenant_id: str, reference_id: str, *, supprimees: bool = False, _acces: _Acces | None = None) -> dict:
    """Fiche complète : sections (avec leur zone dans la capture), palette, polices, structure, liens, fichiers."""
    def lire(a: _Acces) -> dict:
        r = _ligne(a.c, tenant_id, reference_id, supprimees=supprimees)
        fichiers = _fichiers(a.c, tenant_id, [reference_id])[reference_id]
        v = a.c.execute("SELECT COUNT(*) AS n, SUM(CASE WHEN vecteur IS NULL THEN 0 ELSE 1 END) AS v, MAX(modele) AS modele, "
                        "MAX(dimension) AS dimension, MAX(version_index) AS version_index FROM board_reference_fragments "
                        "WHERE tenant_id=? AND reference_id=? AND actif=1", (tenant_id, reference_id)).fetchone()
        meta = _json(r["meta"], {})
        sections = [{"titre": s.get("titre") or "", "niveau": s.get("niveau") or 0, "zone": s.get("zone"),
                     "caracteres": len(s.get("texte") or ""), "extrait": (s.get("texte") or "")[:600]}
                    for s in _json(r["contenu"], [])]
        return {**_publique(r, fichiers, v["n"] or 0), "fichiers": fichiers, "sections": sections,
                "couleurs_css": meta.get("couleurs_css") or {}, "polices_declarees": (meta.get("polices") or {}).get("declarees") or [],
                "structure": meta.get("structure"), "liens": meta.get("liens") or [], "langue": meta.get("langue") or "",
                "tronquee": bool(meta.get("tronquee")), "empreinte": r["empreinte"], "auteur": r["auteur"],
                "index": {"fragments": v["n"] or 0, "vecteurs": v["v"] or 0, "modele": v["modele"] or "",
                          "dimension": v["dimension"] or 0, "version_index": v["version_index"] or 0},
                "reseau": meta.get("reseau"), "bac_a_sable": meta.get("bac_a_sable"), "nature": "donnee_non_fiable",
                "avertissement": AVERTISSEMENT if r["type"] == "site" else ""}
    if _acces is not None:
        return lire(_acces)
    with _lire(tenant_id) as a:
        return lire(a)


def modifier(tenant_id: str, reference_id: str, *, titre: str | None = None, collection: str | None = None,
             etiquettes=None) -> dict:
    champs: dict[str, str] = {}
    if titre is not None:
        if not _court(titre, 200):
            raise MissionError("reference", "titre vide")
        champs["titre"] = _court(titre, 200)
    if collection is not None:
        champs["collection"] = _court(collection, COLLECTION_MAX)
    if etiquettes is not None:
        champs["etiquettes"] = json.dumps(_etiquettes(etiquettes), ensure_ascii=False)
    if not champs:
        raise MissionError("reference", "rien à modifier")
    with _ecrire(tenant_id) as a:
        _ligne(a.c, tenant_id, reference_id)
        sets = ", ".join(f"{k}=?" for k in champs)
        a.c.execute(f"UPDATE board_references SET {sets}, version=version+1, maj=? WHERE id=? AND tenant_id=?",
                    (*champs.values(), time.time(), reference_id, tenant_id))
        if "titre" in champs and a.fts:
            a.c.execute("UPDATE board_reference_fts SET titre=? WHERE tenant_id=? AND reference_id=?",
                        (rag.normaliser(champs["titre"]), tenant_id, reference_id))
    return voir(tenant_id, reference_id)


def supprimer(tenant_id: str, reference_id: str, *, restaurer: bool = False, par: str) -> dict:
    """Suppression douce : la référence disparaît des listes et de la recherche ; `restaurer` la ramène."""
    now = time.time()
    with _ecrire(tenant_id) as a:
        _ligne(a.c, tenant_id, reference_id, supprimees=True)
        a.c.execute("UPDATE board_references SET supprime=?, version=version+1, maj=? WHERE id=? AND tenant_id=?",
                    (0 if restaurer else 1, now, reference_id, tenant_id))
        missions._evenement(a.c, tenant_id, "reference_supprimee" if not restaurer else "reference_restauree", now=now,
                            reference_id=reference_id, par=par)
    return {"id": reference_id, "supprime": not restaurer}


# --- Recherche hybride ----------------------------------------------------------------------------------

def _par_mots(a: _Acces, tenant_id: str, question: str, collection: str | None) -> list[str]:
    filtre = " AND r.collection=?" if collection is not None else ""
    params = (collection,) if collection is not None else ()
    if a.fts:
        requete = rag.requete_fts(question)
        if not requete:
            return []
        lignes = a.c.execute(
            "SELECT board_reference_fts.fragment_id AS id FROM board_reference_fts "
            "JOIN board_references r ON r.id = board_reference_fts.reference_id "
            "WHERE board_reference_fts MATCH ? AND board_reference_fts.tenant_id=? AND r.tenant_id=? AND r.supprime=0 "
            f"AND r.statut='prete'{filtre} ORDER BY bm25(board_reference_fts, 1.0, 2.0, 1.5) LIMIT ?",
            (requete, tenant_id, tenant_id, *params, CANDIDATS)).fetchall()
        return [l["id"] for l in lignes]
    lignes = a.c.execute(
        "SELECT f.id, f.texte_norm, f.section, r.titre FROM board_reference_fragments f "
        "JOIN board_references r ON r.id = f.reference_id WHERE f.tenant_id=? AND r.tenant_id=? AND r.supprime=0 "
        f"AND f.actif=1 AND r.statut='prete'{filtre} ORDER BY f.cree DESC LIMIT ?",
        (tenant_id, tenant_id, *params, REPLI_MAX)).fetchall()
    documents = [(l["id"], f"{l['texte_norm']} {rag.normaliser(l['section'])} {rag.normaliser(l['section'])} "
                           f"{rag.normaliser(l['titre'])}") for l in lignes]
    return [i for i, _ in rag.bm25_python(documents, question, limite=CANDIDATS)]


def _par_vecteurs(a: _Acces, tenant_id: str, question: str, collection: str | None) -> tuple[list[str], str]:
    """(classement, état). État : « desactive », « ok », « indisponible » (panne : BM25 seul), « vide »."""
    global _panne_jusqua
    e = embarqueur()
    if e is None:
        return [], "desactive"
    if time.time() < _panne_jusqua:
        return [], "indisponible"
    try:
        vecteur = e.embarquer([question])[0]
    except Exception:  # noqa: BLE001 — panne de l'embarqueur : la recherche continue par mots
        _panne_jusqua = time.time() + PANNE_S
        return [], "indisponible"
    filtre = " AND r.collection=?" if collection is not None else ""
    params = (collection,) if collection is not None else ()
    lignes = a.c.execute(
        "SELECT f.id, f.vecteur FROM board_reference_fragments f JOIN board_references r ON r.id = f.reference_id "
        "WHERE f.tenant_id=? AND r.tenant_id=? AND r.supprime=0 AND r.statut='prete' AND f.actif=1 AND f.vecteur IS NOT NULL "
        f"AND f.modele=? AND f.dimension=?{filtre} ORDER BY f.cree DESC LIMIT ?",
        (tenant_id, tenant_id, str(e.modele)[:120], len(vecteur), *params, VECTEURS_MAX)).fetchall()
    if not lignes:
        return [], "vide"
    return [i for i, _ in rag.plus_proches(vecteur, [(l["id"], l["vecteur"]) for l in lignes], limite=CANDIDATS,
                                           seuil=0.2)], "ok"


def chercher(tenant_id: str, question: str, *, collection: str | None = None, etiquette: str | None = None,
             n: int = 8) -> dict:
    """Fragments classés (BM25 ± vecteurs, fusion RRF), chacun avec sa citation complète."""
    question = _court(question, 500)
    n = max(1, min(50, int(n)))
    with _lire(tenant_id) as a:
        base = {"question": question, "moteur_mots": "fts5" if a.fts else "python", "nature": "donnee_non_fiable",
                "avertissement": AVERTISSEMENT}
        if not rag.termes(question):
            return {**base, "mode": "bm25", "vecteurs": "desactive", "resultats": []}
        mots = _par_mots(a, tenant_id, question, collection)
        voisins, etat = _par_vecteurs(a, tenant_id, question, collection)
        rangs_mots = {i: k for k, i in enumerate(mots, start=1)}
        rangs_vecteurs = {i: k for k, i in enumerate(voisins, start=1)}
        fusion = rag.fusion_rrf([l for l in (mots, voisins) if l])
        resultats = []
        if fusion:
            ids = [i for i, _ in fusion]
            marques = ",".join("?" * len(ids))
            lignes = {l["id"]: l for l in a.c.execute(
                "SELECT f.id, f.reference_id, f.position, f.section, f.texte, f.zone, f.modele, r.titre, r.type, r.source, "
                "r.url_finale, r.collection, r.etiquettes, r.capture_le FROM board_reference_fragments f "
                f"JOIN board_references r ON r.id = f.reference_id WHERE f.tenant_id=? AND r.tenant_id=? AND f.id IN ({marques})",
                (tenant_id, tenant_id, *ids))}
            fichiers = _fichiers(a.c, tenant_id, list({l["reference_id"] for l in lignes.values()}))
            for ident, score in fusion:
                l = lignes.get(ident)
                if l is None or (etiquette and etiquette.lower() not in _json(l["etiquettes"], [])):
                    continue
                f = fichiers.get(l["reference_id"], {})
                zone = _json(l["zone"], None)
                url = l["url_finale"] or (l["source"] if l["type"] == "site" else "")
                resultats.append({
                    "fragment_id": l["id"], "reference_id": l["reference_id"], "score": round(score, 6),
                    "rangs": {"mots": rangs_mots.get(ident), "vecteurs": rangs_vecteurs.get(ident)},
                    "section": l["section"], "position": l["position"], "extrait": rag.extrait(l["texte"], question),
                    "section_surlignages": [list(p) for p in rag.plages(l["section"], question)],
                    "nature": "donnee_non_fiable",
                    "citation": {"reference_id": l["reference_id"], "titre": l["titre"], "url": url, "type": l["type"],
                                 "collection": l["collection"], "section": l["section"], "capture_le": l["capture_le"],
                                 "capture_url": (f.get("bureau_page") or f.get("bureau_vue") or {}).get("url"),
                                 "vignette_url": (f.get("bureau_vue") or {}).get("url"),
                                 "zone": {"y": zone.get("y"), "hauteur": zone.get("hauteur")} if isinstance(zone, dict) else None,
                                 "lien": f"/v2/?vue=references&ref={l['reference_id']}&fragment={l['id']}"}})
                if len(resultats) >= n:
                    break
    return {**base, "mode": "hybride" if etat == "ok" and voisins else "bm25", "vecteurs": etat, "resultats": resultats}


def fragment(tenant_id: str, fragment_id: str) -> dict:
    """Un fragment entier (pour citer plus long que l'extrait)."""
    with _lire(tenant_id) as a:
        l = a.c.execute("SELECT f.*, r.titre, r.url_finale, r.source, r.type, r.capture_le, r.supprime FROM "
                        "board_reference_fragments f JOIN board_references r ON r.id = f.reference_id "
                        "WHERE f.id=? AND f.tenant_id=? AND r.tenant_id=? AND f.actif=1",
                        (fragment_id, tenant_id, tenant_id)).fetchone()
    if l is None or l["supprime"]:
        raise MissionError("inconnue", f"fragment inconnu : {fragment_id}")
    return {"fragment_id": l["id"], "reference_id": l["reference_id"], "section": l["section"], "position": l["position"],
            "texte": l["texte"], "zone": _json(l["zone"], None), "titre": l["titre"],
            "url": l["url_finale"] or (l["source"] if l["type"] == "site" else ""), "capture_le": l["capture_le"],
            "nature": "donnee_non_fiable", "avertissement": AVERTISSEMENT}


# --- Board ----------------------------------------------------------------------------------------------

def poser_sur_board(tenant_id: str, reference_id: str, *, espace: str = "accueil", x: float = 0, y: float = 0,
                    auteur: str) -> dict:
    """Crée sur le Board une carte reliée à la référence (`meta.reference_id`). Aucune mission n'est lancée :
    la carte montre la capture, la bibliothèque garde le texte."""
    from . import board
    r = voir(tenant_id, reference_id)
    if r["statut"] != "prete":
        raise MissionError("conflit", "référence pas encore prête")
    meta = {"titre": r["titre"], "description": r["description"][:300], "reference_id": reference_id, "source": "reference",
            "url": r["url"], "collection": r["collection"], "palette": [p["hex"] for p in r["palette"][:6]]}
    vue = r["fichiers"].get("bureau_vue")
    espace = board.nom_espace(espace)
    with missions.transaction(tenant_id) as c:
        px, py = missions.place_libre(c, tenant_id, espace, float(x), float(y), 420, 320)
    if vue:
        o = missions.board_ajouter(tenant_id, espace, "capture", r["url"] or r["titre"], auteur=auteur, x=px, y=py,
                                   largeur=420, hauteur=320, meta=meta, asset_id=vue["asset_id"], analyser=False)
    else:
        resume = "\n\n".join(s["extrait"] for s in r["sections"][:3])[:1500] or r["titre"]
        o = missions.board_ajouter(tenant_id, espace, "note", resume, auteur=auteur, x=px, y=py, largeur=408, hauteur=320,
                                   meta=meta, analyser=False)
    return {"objet_id": o["objet_id"], "espace": espace, "reference_id": reference_id}
