"""Lecture commune des projets et des sessions observées, avec leurs appartenances prouvées."""
from __future__ import annotations

from contextlib import closing
import hashlib
import json
import re
import sqlite3
import threading
import time

from . import activite, agents, board, config, journal_memoire, memoire, missions, store, taches

LIMITE_MAX = 100
_OBJET = re.compile(r"BO-[0-9a-f]{12}\Z")
_TENTATIVE = re.compile(r"AT-[0-9a-f]{12}\Z")
_RUNTIME = re.compile(r"AR-[0-9a-f]{24}\Z")
_ENTREE = re.compile(r"memoire:([1-9][0-9]{0,18})\Z")
_SESSION = re.compile(r"(?:AT-[0-9a-f]{12}|AR-[0-9a-f]{24}|T-[0-9]{5,}|workmux:[0-9a-f]{24})\Z")
_verrou_sessions = threading.Lock()
_cache_sessions: tuple[float, list[dict] | None, str] = (0, None, "")


def _texte(valeur, maximum=200):
    return memoire.expurger(" ".join(str(valeur or "").split()))[:maximum]


def _json(valeur):
    try:
        objet = json.loads(valeur or "{}")
        return objet if isinstance(objet, dict) else {}
    except (TypeError, ValueError):
        return {}


def _session(ident, titre, origine, statut, *, debut=None, fin=None, projets=()):
    projets = sorted({str(p) for p in projets if p})
    return {"id": ident, "titre": _texte(titre) or ident, "origine": origine, "statut": _texte(statut, 60),
            "projet": projets[0] if len(projets) == 1 else "", "projets": projets,
            "debut": debut, "fin": fin, "objet_ids": [], "mission_ids": [], "evenement_ids": []}


def _vivantes():
    global _cache_sessions
    with _verrou_sessions:
        if time.monotonic() - _cache_sessions[0] > 5:
            lignes, erreur = agents.status_all()
            _cache_sessions = time.monotonic(), lignes, erreur
        return _cache_sessions[1:]


def _locales(tenant_id):
    """Les registres du poste appartiennent exclusivement au tenant local."""
    if tenant_id != missions.tenant_local():
        return [], [], []
    avertissements = []
    try:
        historique = [t for t in taches.toutes() if isinstance(t, dict)]
    except (OSError, ValueError, KeyError, TypeError):
        historique = []
        avertissements.append("Le registre des lancements de code est indisponible.")
    vivantes, erreur = _vivantes()
    if vivantes is None:
        avertissements.append("Les sessions de code en direct sont indisponibles. Les lancements conservés restent consultables.")
        vivantes = []
    sessions = []
    par_lancement = {}
    for t in historique:
        ident = str(t.get("id") or "")
        if not re.fullmatch(r"T-[0-9]{5,}", ident):
            continue
        titre = " · ".join(filter(None, (t.get("issue"), t.get("worktree"))))
        session = _session(ident, titre, "workmux", t.get("statut"), debut=t.get("debut") or t.get("cree"),
                           fin=t.get("fin"), projets=[t.get("projet")])
        session["reference_travail"] = _texte(t.get("issue"))
        sessions.append(session)
        par_lancement[ident] = t
    for a in vivantes:
        fiche = taches.pour_agent(a.get("project", ""), a.get("worktree", ""), historique, a.get("workdir", ""))
        if fiche and fiche.get("id") in par_lancement:
            next(s for s in sessions if s["id"] == fiche["id"])["statut"] = _texte(a.get("status"), 60)
            continue
        ident = "workmux:" + activite._id(a)
        sessions.append(_session(ident, a.get("title") or a.get("worktree"), "workmux", a.get("status"),
                                 projets=[a.get("project")]))
    return sessions, historique, avertissements


def _runtimes(tenant_id, page, limite, selections):
    if tenant_id != missions.tenant_local() or not store.db_path().exists():
        return [], 0, []
    try:
        connexion = sqlite3.connect(store.db_path().resolve().as_uri() + "?mode=ro", uri=True, timeout=2)
        with closing(connexion) as c:
            if not c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='agent_runtime_runs'").fetchone():
                return [], 0, []
            total = c.execute("SELECT COUNT(*) FROM agent_runtime_runs").fetchone()[0]
            lignes = c.execute("SELECT id,project,status,updated_at,document FROM agent_runtime_runs "
                               "ORDER BY updated_at DESC,id LIMIT ? OFFSET ?", (limite, (page - 1) * limite)).fetchall()
            connues = {r[0] for r in lignes}
            manquantes = sorted(s for s in selections - connues if _RUNTIME.fullmatch(s))
            if manquantes:
                marques = ",".join("?" * len(manquantes))
                lignes += c.execute("SELECT id,project,status,updated_at,document FROM agent_runtime_runs "
                                    f"WHERE id IN ({marques})", manquantes).fetchall()
            sessions = []
            for r in lignes:
                document = _json(r[4])
                tache = document.get("tache") if isinstance(document.get("tache"), dict) else {}
                s = _session(r[0], tache.get("objective"), "runtime", r[2], projets=[r[1]],
                             debut=document.get("started_at") or document.get("created_at"),
                             fin=r[3] if r[2] in ("succeeded", "failed", "cancelled") else None)
                inputs = tache.get("inputs")
                for entree in inputs if isinstance(inputs, list) else []:
                    if not isinstance(entree, str):
                        continue
                    typ, _, ident = entree.partition(":")
                    if typ in ("objet", "board") and _OBJET.fullmatch(ident):
                        s["objet_ids"].append(ident)
                    if typ == "mission" and re.fullmatch(r"MI-[0-9a-f]{12}", ident):
                        s["mission_ids"].append(ident)
                sessions.append(s)
            return sessions, total, []
    except (OSError, sqlite3.Error):
        return [], 0, ["Le registre des sessions d’agent locales est indisponible."]

def _tentatives(c, tenant_id, page, limite, requises):
    total = c.execute("SELECT COUNT(*) AS n FROM tentatives WHERE tenant_id=?", (tenant_id,)).fetchone()["n"]
    sql = ("SELECT a.id,a.debut,a.fin,a.issue,a.fournisseur,t.mission_id,t.statut,t.travail,m.objectif "
           "FROM tentatives a JOIN taches t ON t.id=a.tache_id AND t.tenant_id=a.tenant_id "
           "JOIN missions m ON m.id=t.mission_id AND m.tenant_id=t.tenant_id WHERE a.tenant_id=?")
    lignes = c.execute(sql + " ORDER BY a.debut DESC,a.id LIMIT ? OFFSET ?", (tenant_id, limite, (page - 1) * limite)).fetchall()
    ids = {r["id"] for r in lignes}
    manquantes = sorted(r for r in requises - ids if _TENTATIVE.fullmatch(r))
    if manquantes:
        marques = ",".join("?" * len(manquantes))
        lignes += c.execute(sql + f" AND a.id IN ({marques})", (tenant_id, *manquantes)).fetchall()
    mid = list({r["mission_id"] for r in lignes})
    projets_missions = {}
    if mid:
        marques = ",".join("?" * len(mid))
        for r in c.execute(f"SELECT DISTINCT mission_id,espace FROM board_objets WHERE tenant_id=? AND mission_id IN ({marques})",
                           (tenant_id, *mid)):
            projets_missions.setdefault(r["mission_id"], set()).add(r["espace"])
    sessions = []
    for r in lignes:
        travail = _json(r["travail"])
        projets = projets_missions.get(r["mission_id"], set()) | ({travail["espace"]} if isinstance(travail.get("espace"), str) else set())
        titre = " · ".join(filter(None, (r["objectif"], r["fournisseur"], r["id"])))
        statut = r["issue"] or ("running" if r["fin"] is None else r["statut"])
        s = _session(r["id"], titre, "tentative", statut, debut=r["debut"], fin=r["fin"], projets=projets)
        s["mission_ids"] = [r["mission_id"]]
        sessions.append(s)
    return sessions, total


def _journal(c, tenant_id, page, limite, selection):
    backend = missions.backend().nom
    sql = f"""WITH journal AS (
      SELECT e.seq,e.tenant_id,e.mission_id,e.tache_id,e.type,e.donnees,e.ts,m.objectif,
        {journal_memoire._nature(backend)} AS nature
      FROM evenements e JOIN missions m ON m.id=e.mission_id AND m.tenant_id=e.tenant_id
      WHERE e.tenant_id=? AND e.type IN ('tache_etat','tache_retenue','approbation','frustration_declaree')
    ) SELECT * FROM journal WHERE nature IS NOT NULL"""
    total = c.execute("SELECT COUNT(*) AS n FROM (" + sql + ") total", (tenant_id,)).fetchone()["n"]
    lignes = c.execute(sql + " ORDER BY seq DESC LIMIT ? OFFSET ?", (tenant_id, limite, (page - 1) * limite)).fetchall()
    if selection:
        sequence = int(selection.partition(":")[2])
        if all(r["seq"] != sequence for r in lignes):
            cible = c.execute(sql + " AND seq=?", (tenant_id, sequence)).fetchone()
            if cible:
                lignes.append(cible)
    return [journal_memoire._entree(c, r, backend) for r in lignes], total


def lire(tenant_id: str, *, page=1, limite=100, objet="", session="", entree="") -> dict:
    """Lit un lot de chaque famille, dans tous les projets du tenant authentifié."""
    if type(page) is not int or not 1 <= page <= 1_000_000:
        raise ValueError("page invalide")
    if type(limite) is not int or not 1 <= limite <= LIMITE_MAX:
        raise ValueError("limite attendue de 1 à 100")
    if objet and (not isinstance(objet, str) or not _OBJET.fullmatch(objet)):
        raise ValueError("objet invalide")
    if session and (not isinstance(session, str) or not _SESSION.fullmatch(session)):
        raise ValueError("session invalide")
    if entree and (not isinstance(entree, str) or not _ENTREE.fullmatch(entree)
                   or int(entree.partition(":")[2]) > journal_memoire.SEQ_MAX):
        raise ValueError("entrée invalide")
    debut = (page - 1) * limite
    locales, historique, avertissements = _locales(tenant_id)
    locales_lot = locales[debut:debut + limite]
    if session and all(s["id"] != session for s in locales_lot):
        locales_lot += [s for s in locales if s["id"] == session]

    with closing(missions._connecter(tenant_id)) as c:
        total_objets = c.execute("SELECT COUNT(*) AS n FROM board_objets WHERE tenant_id=? AND supprime=0", (tenant_id,)).fetchone()["n"]
        lignes = c.execute("SELECT * FROM board_objets WHERE tenant_id=? AND supprime=0 ORDER BY cree,id LIMIT ? OFFSET ?",
                           (tenant_id, limite, debut)).fetchall()
        if objet and all(r["id"] != objet for r in lignes):
            r = c.execute("SELECT * FROM board_objets WHERE tenant_id=? AND supprime=0 AND id=?", (tenant_id, objet)).fetchone()
            if r:
                lignes.append(r)
        ids = [r["id"] for r in lignes]
        filtre = "tenant_id=? AND supprime=0"
        params = (tenant_id,)
        if ids:
            marques = ",".join("?" * len(ids))
            filtre += f" AND id IN ({marques})"
            params = (tenant_id, *ids)
        objets = board._completer(c, tenant_id, lignes, filtre, params) if lignes else []
        liens_base = (" FROM board_liens l JOIN board_objets a ON a.id=l.source_id AND a.tenant_id=l.tenant_id "
                      "JOIN board_objets b ON b.id=l.cible_id AND b.tenant_id=l.tenant_id "
                      "WHERE l.tenant_id=? AND l.supprime=0 AND a.supprime=0 AND b.supprime=0")
        total_liens = c.execute("SELECT COUNT(*) AS n" + liens_base, (tenant_id,)).fetchone()["n"]
        liens = [dict(r) for r in c.execute("SELECT l.*" + liens_base + " ORDER BY l.cree,l.id LIMIT ? OFFSET ?",
                                           (tenant_id, limite, debut))]
        entrees, total_entrees = _journal(c, tenant_id, page, limite, entree)
        requises = {e["preuve"]["tentative_id"] for e in entrees if e["preuve"].get("tentative_id")}
        requises |= {o["meta"][k] for o in objets for k in ("tentative_id", "session_id")
                     if isinstance(o["meta"].get(k), str) and _TENTATIVE.fullmatch(o["meta"][k])}
        if session and _TENTATIVE.fullmatch(session):
            requises.add(session)
        par_artefact = {}
        artefacts = [o["meta"].get("artefact_id") for o in objets if isinstance(o["meta"].get("artefact_id"), str)]
        if artefacts:
            marques = ",".join("?" * len(artefacts))
            par_artefact = {r["id"]: r["tentative_id"] for r in c.execute(
                f"SELECT id,tentative_id FROM artefacts WHERE tenant_id=? AND id IN ({marques})", (tenant_id, *artefacts))}
            requises.update(par_artefact.values())
        tentatives, total_tentatives = _tentatives(c, tenant_id, page, limite, requises)
        projets = {r["espace"]: {"nom": r["espace"], "objets": r["n"]} for r in c.execute(
            "SELECT espace,COUNT(*) AS n FROM board_objets WHERE tenant_id=? AND supprime=0 GROUP BY espace", (tenant_id,))}
        missions_connues = {r["id"] for r in c.execute("SELECT id FROM missions WHERE tenant_id=?", (tenant_id,))}

    runtime_selections = {session} if session and _RUNTIME.fullmatch(session) else set()
    runtime_selections.update(o["meta"][k] for o in objets for k in ("session_id", "runtime_run_id")
                              if isinstance(o["meta"].get(k), str) and _RUNTIME.fullmatch(o["meta"][k]))
    runtimes, total_runtime, avertissements_runtime = _runtimes(tenant_id, page, limite, runtime_selections)
    avertissements += avertissements_runtime
    requises_locales = {o["meta"][k] for o in objets for k in ("session_id", "runtime_run_id")
                       if isinstance(o["meta"].get(k), str)}
    presentes_locales = {s["id"] for s in locales_lot}
    locales_lot += [s for s in locales if s["id"] in requises_locales - presentes_locales]
    sessions = {s["id"]: s for s in [*tentatives, *runtimes, *locales_lot]}
    for o in objets:
        meta = o["meta"]
        candidats = [meta.get(k) for k in ("session_id", "tentative_id", "runtime_run_id")]
        candidats.append(par_artefact.get(meta.get("artefact_id")))
        for ident in candidats:
            if isinstance(ident, str) and ident in sessions:
                sessions[ident]["objet_ids"].append(o["id"])
        reference = missions.reference_travail(meta) or ("JRV-" + o["id"][3:].upper() if o["type"] == "tache" else "")
        for s in locales:
            if s.get("reference_travail") == reference and reference and o["espace"] in s["projets"]:
                sessions.setdefault(s["id"], s)["objet_ids"].append(o["id"])
    for e in entrees:
        s = sessions.get(e["preuve"].get("tentative_id"))
        if s:
            s["evenement_ids"].append(e["id"])
    objets_connus = {o["id"] for o in objets}
    candidats_runtime = sorted({i for s in runtimes for i in s["objet_ids"]})
    with closing(missions._connecter(tenant_id)) as c:
        for debut_lot in range(0, len(candidats_runtime), 400):
            lot = candidats_runtime[debut_lot:debut_lot + 400]
            marques = ",".join("?" * len(lot))
            objets_connus.update(r["id"] for r in c.execute(
                f"SELECT id FROM board_objets WHERE tenant_id=? AND supprime=0 AND id IN ({marques})", (tenant_id, *lot)))
    for s in sessions.values():
        s["objet_ids"] = sorted(set(s["objet_ids"]) & objets_connus)
        s["mission_ids"] = sorted(set(s["mission_ids"]) & missions_connues)
        s["evenement_ids"] = sorted(set(s["evenement_ids"]))
        s.pop("reference_travail", None)
        for p in s["projets"]:
            projets.setdefault(p, {"nom": p, "objets": 0})
    if tenant_id == missions.tenant_local():
        try:
            for p in config.projects():
                projets.setdefault(p, {"nom": p, "objets": 0})
        except (OSError, ValueError, KeyError, TypeError):
            avertissements.append("La liste des projets enregistrés est indisponible.")
    total_sessions = total_tentatives + total_runtime + len(locales)
    total_max = max(total_objets, total_liens, total_entrees, total_tentatives, total_runtime, len(locales))
    couverture = {cle: {"charges": len(valeurs), "total": total} for cle, valeurs, total in (
        ("objets", objets, total_objets), ("liens", liens, total_liens),
        ("entrees", entrees, total_entrees), ("sessions", sessions, total_sessions))}
    return {"page": page, "limite": limite, "objets": objets, "liens": liens, "entrees": entrees,
            "sessions": list(sessions.values()), "projets": sorted(projets.values(), key=lambda p: p["nom"].casefold()),
            "couverture": couverture, "suivant": page + 1 if page * limite < total_max else None,
            "cle_disposition": hashlib.sha256(("jarvis-graphe-v1\0" + tenant_id).encode()).hexdigest()[:24],
            "avertissements": list(dict.fromkeys(avertissements))}
