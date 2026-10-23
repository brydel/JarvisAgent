"""Vue de lecture du travail réel : sessions de code et tâches du moteur de missions.

Aucun lancement ni secret d'exécutant. L'accueil observe tous les projets ; un Board de projet ne montre que
son travail. Une observation impossible reste une erreur, jamais une équipe vide présentée comme certaine.
"""

from __future__ import annotations

import hashlib
import subprocess
import time

from . import agents, board, missions, report


def _id(a: dict) -> str:
    return hashlib.sha256(f"{a.get('session')}\0{a.get('window')}\0{a.get('workdir')}".encode()).hexdigest()[:24]


def instantane(tenant_id: str, espace: str, *, now: float | None = None) -> dict:
    now = time.time() if now is None else now
    espace = board.nom_espace(espace)
    # Les sessions tmux appartiennent au poste local, pas aux autres tenants de la base.
    sessions, erreur = (agents.status_all() if tenant_id == missions.tenant_local()
                        else (None, "Les sessions du poste ne sont visibles que dans l'espace local."))
    if sessions is not None:
        from . import specifications
        try:
            report.enrichir(sessions)  # rôle et modèle réels du registre, comme dans /etat
        except (OSError, ValueError, KeyError, TypeError):
            pass  # le statut reste observable ; rôle inconnu si le registre n'est pas exploitable
        sessions = [{"id": _id(a), "contrats": specifications.pour_workmux(a), **{k: a.get(k, "") for k in
                    ("project", "worktree", "status", "kind", "elapsed", "title", "session", "window")}}
                    for a in sessions if espace == "accueil" or a["project"] == espace]
    c = missions._connecter(tenant_id)
    try:
        # La mission peut être liée à une note contextualisée, pas seulement à une carte « mission ».
        taches = [dict(r) for r in c.execute(
            "SELECT t.id, t.mission_id, t.type, t.statut, t.raison, t.fournisseur_choisi AS fournisseur, "
            "a.debut, e.nom AS executant, t.bail_expire, m.objectif, "
            "(SELECT b.id FROM board_objets b WHERE b.tenant_id=t.tenant_id AND b.mission_id=t.mission_id "
            "AND b.supprime=0 AND (?='accueil' OR b.espace=?) ORDER BY b.cree LIMIT 1) AS objet_id "
            "FROM taches t JOIN missions m ON m.id=t.mission_id AND m.tenant_id=t.tenant_id "
            "LEFT JOIN tentatives a ON a.id=t.tentative_id AND a.tenant_id=t.tenant_id "
            "LEFT JOIN executants e ON e.id=a.executant_id AND e.tenant_id=t.tenant_id "
            "WHERE t.tenant_id=? AND t.statut NOT IN ('SUCCEEDED','FAILED','CANCELLED','EXPIRED') "
            "AND (?='accueil' OR EXISTS (SELECT 1 FROM board_objets b WHERE b.tenant_id=t.tenant_id "
            "AND b.mission_id=t.mission_id AND b.espace=? AND b.supprime=0)) "
            "ORDER BY a.debut, t.cree, t.id", (espace, espace, tenant_id, espace, espace))]
        for t in taches:
            t["bail_perime"] = t["bail_expire"] is not None and t["bail_expire"] < now
            del t["bail_expire"]
        signe = c.execute("SELECT MAX(dernier_signe) AS ts FROM executants WHERE tenant_id=? AND revoque=0",
                          (tenant_id,)).fetchone()["ts"]
    finally:
        c.close()
    return {"ts": now, "espace": espace, "sessions": sessions, "sessions_erreur": erreur,
            "taches": taches, "demon": report.demon_vivant(now),
            "executant_actif": signe is not None and now - signe < 180}


def apercu(tenant_id: str, session_id: str, espace: str) -> str:
    """Capture bornée d'une fenêtre observée ; aucune cible tmux arbitraire fournie par le navigateur."""
    if tenant_id != missions.tenant_local():
        raise missions.MissionError("inconnue", "session inconnue")
    espace = board.nom_espace(espace)
    trouves, erreur = agents.status_all()
    if trouves is None:
        raise missions.MissionError("indisponible", erreur)
    a = next((a for a in trouves if _id(a) == session_id
              and (espace == "accueil" or a["project"] == espace)), None)
    if a is None:
        raise missions.MissionError("inconnue", "session inconnue ou terminée")
    # L'identifiant de fenêtre évite les ambiguïtés de noms (points, deux sessions identiques).
    w = next((w for w in agents.tmux_agent_windows()
              if w["session"] == a["session"] and w["window"] == a["window"]), None)
    if w is None:
        raise missions.MissionError("inconnue", "fenêtre de session introuvable")
    try:
        r = agents._run(["tmux", "capture-pane", "-p", "-J", "-t", w["id"], "-S", "-80"], timeout=5)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise missions.MissionError("indisponible", "capture de session interrompue") from exc
    if r.returncode:
        raise missions.MissionError("indisponible", "capture de session indisponible")
    return r.stdout[-16000:]
