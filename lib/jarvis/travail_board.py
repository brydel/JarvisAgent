"""Le travail réel du chef sur le Board du projet : plans, tâches d'agents de code et équipe au travail.

Le chef lance son travail depuis Telegram ou le terminal (plans validés, agents workmux avec un rôle et un modèle).
Ce module le rend visible sur le Board du projet, sans rien lancer lui-même :
- une carte « plan » par plan proposé ou approuvé (statut, mode, nombre de tâches) ;
- une carte « tâche » par lancement d'agent (issue, rôle, modèle, effort, statut vivant, verdict), reliée à son plan ;
- une carte « équipe » par projet, qui n'apparaît que lorsqu'il y a du travail : chaque agent avec son rôle, son
  modèle et ce qu'il fait, reliée aux tâches en cours.

Les cartes sont retrouvées par leur référence (meta.travail_ref) : la synchronisation est idempotente et ne
réécrit une carte que si son contenu change. Une carte supprimée par l'humain n'est jamais recréée.
"""

from __future__ import annotations

import json
import time

from . import missions, store

FENETRE_S = 7 * 86400  # plans et tâches des 7 derniers jours
ACTIFS = ("working", "waiting", "untracked", "silent")
STATUTS_AGENT = {"working": "travaille", "waiting": "attend ton retour", "untracked": "actif", "silent": "silencieux",
                 "done": "terminé", "idle": "au repos"}
STATUTS_FICHE = {"lancee": "lancée", "en_cours": "travaille", "attente": "attend ton retour", "silencieuse": "silencieux",
                 "terminee": "terminé", "echec": "échec", "annulee": "annulée"}
RECENT_S = 12 * 3600  # une tâche finie reste visible 12 h (un plan décidé : 24 h)


def _references(tenant: str) -> set[str]:
    """Références des cartes de travail déjà posées (supprimées comprises : on ne les recrée pas)."""
    c = missions._connecter(tenant)
    try:
        return {json.loads(r["meta"]).get("travail_ref", "") for r in c.execute(
            "SELECT meta FROM board_objets WHERE tenant_id=? AND meta LIKE '%travail_ref%'", (tenant,))}
    finally:
        c.close()


def _trouver(c, tenant: str, espace: str, ref: str):
    return c.execute("SELECT id, meta, supprime, x, y, largeur, hauteur FROM board_objets WHERE tenant_id=? AND espace=? "
                     "AND meta LIKE ? ORDER BY cree LIMIT 1", (tenant, espace, f'%"travail_ref": "{ref}"%')).fetchone()


def _carte(tenant: str, espace: str, ref: str, type_: str, meta: dict, *, pres_de: str | None = None,
           taille=(420, 300), now: float) -> str | None:
    """Crée ou met à jour la carte `ref` ; None si l'humain l'a supprimée (on ne la recrée pas)."""
    from . import synchro
    meta = {**meta, "travail_ref": ref, "source": "chef"}
    c = missions._connecter(tenant)
    try:
        o = _trouver(c, tenant, espace, ref)
        if o is None:
            if pres_de:
                p = c.execute("SELECT x, y, largeur FROM board_objets WHERE id=? AND tenant_id=?", (pres_de, tenant)).fetchone()
                x, y = missions.place_libre(c, tenant, espace, p["x"] + (p["largeur"] or 400) + 100, p["y"], *taille) if p \
                    else synchro.position_libre(tenant, espace, *taille)
            else:
                x, y = None, None
    finally:
        c.close()
    if o is not None:
        if o["supprime"]:
            return None
        ancienne = json.loads(o["meta"] or "{}")
        nouvelle = {**ancienne, **meta}
        if nouvelle != ancienne:  # aucune écriture (ni rechargement du Studio) si rien n'a changé
            with missions.transaction(tenant) as c:
                c.execute("UPDATE board_objets SET meta=?, version=version+1, maj=? WHERE id=? AND tenant_id=?",
                          (json.dumps(nouvelle, ensure_ascii=False), now, o["id"], tenant))
                missions._evenement(c, tenant, "board_maj", now=now, objet_id=o["id"], champs=["meta"], par="jarvis")
        return o["id"]
    if x is None:
        x, y = synchro.position_libre(tenant, espace, *taille)
    return missions.board_ajouter(tenant, espace, type_, "", auteur="chef", x=x, y=y, largeur=taille[0],
                                  hauteur=taille[1], meta=meta, analyser=False, contextualiser=False, now=now)["objet_id"]


def _lier(tenant: str, espace: str, source: str | None, cible: str | None, libelle: str, style: str) -> None:
    if not source or not cible:
        return
    from . import board
    c = missions._connecter(tenant)
    try:
        existe = c.execute("SELECT 1 FROM board_liens WHERE tenant_id=? AND source_id=? AND cible_id=?",
                           (tenant, source, cible)).fetchone()  # supprimée par l'humain : on ne la remet pas
    finally:
        c.close()
    if not existe:
        board.lier(tenant, espace, source, cible, libelle=libelle, style=style, par="jarvis:chef")


def synchroniser(agents_vus: list[dict] | None = None, *, now: float | None = None) -> dict:
    """Un passage (démon, toutes les 20 s) : plans, tâches et équipes des projets reflétés sur leurs Boards."""
    from . import agents as ag, plans, report, roles, taches
    now = now or time.time()
    if not missions.backend().existe():
        return {}
    tenant = missions.tenant_local()
    if agents_vus is None:
        agents_vus, _ = ag.status_all()
    vivants = report.enrichir([dict(a) for a in (agents_vus or [])])
    par_tache = {}
    for a in vivants:
        if a.get("tache"):
            par_tache[a["tache"]["id"]] = a
    bilan = {"plans": 0, "taches": 0, "equipes": 0}

    # Ce qui mérite une carte : le travail EN COURS et ce qui vient de finir ; une carte déjà posée est tenue à jour
    # jusqu'à son état final. L'historique (des dizaines de tâches) reste dans `jarvis tache`, pas sur le Board.
    deja = _references(tenant)
    visibles = []
    for t in taches.toutes():
        vivant = par_tache.get(t["id"])
        en_cours = (vivant and vivant["status"] in ACTIFS) or t.get("statut") in ("lancee", "en_cours", "attente", "silencieuse")
        recente = t.get("fin") and now - t["fin"] < RECENT_S
        if en_cours or recente or f"tache:{t['id']}" in deja:
            visibles.append(t)
    plans_utiles = {(t.get("plan"), t["projet"]) for t in visibles if t.get("plan")}

    cartes_plan: dict[tuple[str, str], str] = {}
    for p in plans.all_plans():
        if p["statut"] not in ("en_attente", "approuve") or now - (p.get("cree") or 0) > FENETRE_S:
            continue
        for projet in sorted({i["projet"] for i in p["items"]}):
            if not (p["statut"] == "en_attente" or now - (p.get("decide") or 0) < 2 * RECENT_S
                    or (p["id"], projet) in plans_utiles or f"plan:{p['id']}" in deja):
                continue
            items = [i for i in p["items"] if i["projet"] == projet]
            oid = _carte(tenant, projet, f"plan:{p['id']}", "plan", {
                "titre": p["titre"][:120], "plan_id": p["id"], "statut": p["statut"], "mode": p["mode"],
                "resume": (p.get("resume") or "")[:400], "origine": p.get("origine", "chef"),
                "elements": [{"issue": i["issue"], "role": i.get("role") or "", "agent": i.get("agent", ""),
                              "modele": i.get("modele") or "", "desc": (i.get("desc") or "")[:120], "lance": bool(i.get("lance"))}
                             for i in items][:12]}, taille=(440, 320), now=now)
            if oid:
                cartes_plan[(p["id"], projet)] = oid
                bilan["plans"] += 1

    for t in visibles:
        vivant = par_tache.get(t["id"])
        role = roles.ou_defaut(t.get("role"))
        statut = (STATUTS_AGENT.get(vivant["status"], vivant["status"]) if vivant
                  else STATUTS_FICHE.get(t.get("statut", ""), t.get("statut", "")))
        plan_carte = cartes_plan.get((t.get("plan"), t["projet"]))
        oid = _carte(tenant, t["projet"], f"tache:{t['id']}", "tache", {
            "titre": f"{t['issue']} · {role['titre']}"[:120], "tache_id": t["id"], "issue": t["issue"],
            "role": role["nom"], "role_titre": role["titre"], "equipe": role.get("equipe", ""),
            "agent": t.get("agent", ""), "modele": t.get("modele") or "", "effort": t.get("effort") or "",
            "statut": statut, "actif": bool(vivant and vivant["status"] in ACTIFS), "worktree": t.get("worktree", ""),
            "plan_id": t.get("plan") or "", "debut": t.get("debut") or t.get("cree"), "fin": t.get("fin"),
            "verdict": t.get("verdict") or "", "essai": t.get("essai", 1)},
            pres_de=plan_carte, taille=(400, 260), now=now)
        if oid:
            bilan["taches"] += 1
            _lier(tenant, t["projet"], plan_carte, oid, "tâche", "alimente")

    # une équipe par projet, seulement quand il y a du travail : chaque agent avec son rôle et son modèle
    for projet in sorted({a["project"] for a in vivants if a.get("project")}):
        membres = []
        for a in vivants:
            if a.get("project") != projet:
                continue
            t = a.get("tache") or {}
            role = roles.ou_defaut(a.get("role") or None)
            membres.append({"id": a.get("worktree", ""), "role": role["nom"] if t else "", "titre": role["titre"] if t else "Agent",
                            "modele": a.get("modele") or t.get("agent", ""), "agent": t.get("agent", a.get("kind", "")),
                            "statut": STATUTS_AGENT.get(a["status"], a["status"]), "actif": a["status"] in ACTIFS,
                            "issue": a.get("issue") or "", "depuis": a.get("elapsed", "")})
        actifs = [m for m in membres if m["actif"]]
        c = missions._connecter(tenant)
        try:
            existe = _trouver(c, tenant, projet, f"equipe:{projet}")
        finally:
            c.close()
        if not actifs and (existe is None or existe["supprime"]):
            continue  # pas de travail : la carte existante passe au repos, aucune n'est créée ni ramenée
        if actifs and existe is not None and existe["supprime"]:
            # retirée quand l'équipe était au repos : elle revient dès que des agents se remettent au travail
            from . import board
            board.supprimer(tenant, [existe["id"]], par="jarvis:chef", restaurer=True, now=now)
        oid = _carte(tenant, projet, f"equipe:{projet}", "agents", {
            "titre": f"Équipe {projet}", "membres": membres[:8], "actifs": len(actifs)}, taille=(360, 360), now=now)
        if oid:
            bilan["equipes"] += 1
            for a in vivants:  # l'équipe est reliée aux tâches sur lesquelles elle travaille en ce moment
                t = a.get("tache")
                if a.get("project") == projet and t and a["status"] in ACTIFS:
                    c = missions._connecter(tenant)
                    try:
                        carte_t = _trouver(c, tenant, projet, f"tache:{t['id']}")
                    finally:
                        c.close()
                    if carte_t and not carte_t["supprime"]:
                        _lier(tenant, projet, oid, carte_t["id"], "travaille sur", "utilise")
    return bilan


RETRAITS = "board_retraits.json"  # derniers retraits (pour « restaurer --dernier »)


def termines(tenant: str, espace: str) -> list[dict]:
    """Cartes de travail finies d'un Board : tâches non actives, équipe au repos, plans approuvés sans tâche active.
    Un plan encore à valider et tout ce qui est en cours restent."""
    from . import board
    objs = [o for o in board.objets(tenant, espace)["objets"] if o["meta"].get("travail_ref")]
    actives_par_plan = {}
    for o in objs:
        if o["type"] == "tache" and o["meta"].get("actif"):
            actives_par_plan[o["meta"].get("plan_id")] = True
    sortie = []
    for o in objs:
        m = o["meta"]
        if (o["type"] == "tache" and not m.get("actif")) \
                or (o["type"] == "agents" and not m.get("actifs")) \
                or (o["type"] == "plan" and m.get("statut") == "approuve" and not actives_par_plan.get(m.get("plan_id"))):
            sortie.append(o)
    return sortie


def retirer(tenant: str, espace: str, *, ids: list[str] | None = None, finis: bool = False, par: str,
            now: float | None = None) -> dict:
    """Retire du Board (suppression douce, restaurable) des cartes désignées et/ou les cartes de travail finies.
    Rien n'est effacé ; la synchronisation ne recrée pas une carte retirée."""
    from . import board
    now = now or time.time()
    choisis: dict[str, dict] = {}
    if finis:
        for o in termines(tenant, espace):
            choisis[o["id"]] = o
    if ids:
        presents = {o["id"]: o for o in board.objets(tenant, espace)["objets"]}
        inconnus = [i for i in ids if i not in presents]
        if inconnus:
            raise missions.MissionError("inconnue", f"carte(s) absente(s) du Board {espace} : {', '.join(inconnus[:5])}")
        choisis.update({i: presents[i] for i in ids})
    if not choisis:
        return {"retirees": 0, "ids": [], "espace": espace}
    liste = list(choisis)
    n = 0
    for i in range(0, len(liste), 500):
        n += board.supprimer(tenant, liste[i:i + 500], par=par, now=now)
    store.write_json(RETRAITS, {"ts": now, "ids": liste, "espace": espace, "par": par})
    par_type: dict[str, int] = {}
    for o in choisis.values():
        par_type[o["type"]] = par_type.get(o["type"], 0) + 1
    return {"retirees": n, "ids": liste, "espace": espace, "par_type": par_type}


def restaurer_dernier(tenant: str, *, par: str, now: float | None = None) -> dict:
    from . import board
    dernier = store.read_json(RETRAITS, {})
    if not dernier.get("ids"):
        raise missions.MissionError("inconnue", "aucun retrait récent à restaurer")
    n = 0
    for i in range(0, len(dernier["ids"]), 500):
        n += board.supprimer(tenant, dernier["ids"][i:i + 500], par=par, restaurer=True, now=now)
    store.write_json(RETRAITS, {})
    return {"restaurees": n, "espace": dernier.get("espace", "")}


def verifier(now: float | None = None) -> None:
    """Point d'entrée du démon : une erreur ici ne doit jamais arrêter la surveillance."""
    try:
        synchroniser(now=now)
    except Exception as exc:  # noqa: BLE001
        store.feed_add("erreur", f"Board ← travail du chef : {exc}")
