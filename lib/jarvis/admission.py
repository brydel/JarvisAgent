"""Point d'admission commun : TOUT départ d'agent passe ici (plan, ligne de commande, reprise, relance).

Sous un seul verrou, on vérifie dans l'ordre : configuration valide, pauses (toutes causes), observation
possible, capacité du poste (agents occupés + réservations en attente), opérations lourdes, doublons,
jetons, puis le plan approuvé. Si tout passe, une RÉSERVATION est posée : elle compte comme un agent
occupé tant que l'agent n'est pas visible, et expire seule si le lancement n'aboutit jamais (le plan
est alors rendu relançable). Deux lancements simultanés ne peuvent donc pas dépasser le plafond.

Ce que l'admission ne fait PAS : elle n'arrête rien d'existant et n'impose aucune limite aux commandes
qu'un agent lance ensuite dans son terminal. Les opérations lourdes (compilation, tests, navigateur,
vidéo) sont déclarées par les agents avec « jarvis lourd » : c'est une consigne vérifiée a posteriori,
pas une barrière (voir docs/autonomy/admission.md).
"""

from __future__ import annotations

import os
import time

from . import agents as ag
from . import config, plans, store

LOCK = "admission"
RESERVATIONS = "reservations.json"
LOURDES = "lourdes.json"
RELANCES = "relances.json"
ORIGINES = ("plan", "cli", "reprise", "relance", "chef", "sous-agent")
# Classes de charge. Les lourdes occupent une place d'« opération lourde » en plus d'une place d'agent.
CLASSES = {"recherche": False, "orchestration": False, "edition": False,
           "compilation": True, "tests": True, "navigateur": True, "video": True}
ROLE_CLASSE = {"video": "video", "qa": "tests", "design": "navigateur", "recherche": "recherche"}
LOURDE_DUREE_MAX = 4 * 3600  # une opération lourde jamais clôturée est oubliée après ce délai


class Refus(Exception):
    """Lancement refusé. `code` : config, pause, observation, capacite, lourde, doublon, budget, plan, origine."""

    def __init__(self, code: str, raison: str):
        super().__init__(raison)
        self.code, self.raison = code, raison


def classe_pour_role(role: str) -> str:
    return ROLE_CLASSE.get(role or "", "edition")


def _vide_res() -> dict:
    return {"seq": 0, "reservations": []}


def _vide_lourdes() -> dict:
    return {"seq": 0, "operations": []}


def _pid_vivant(pid: int | None) -> bool:
    if not pid:
        return True  # sans PID, on fait confiance à la durée
    try:
        os.kill(int(pid), 0)
        return True
    except ProcessLookupError:
        return False
    except (PermissionError, OSError, ValueError):
        return True


def _actives(data: dict, visibles: set[str], now: float) -> list[dict]:
    """Réservations qui comptent encore : ni libérées, ni expirées, ni déjà visibles dans tmux."""
    out = []
    for r in data["reservations"]:
        if r["etat"] not in ("reservee", "confirmee"):
            continue
        if now >= r["expire"]:
            continue
        if r.get("worktree") and r["worktree"].lower() in visibles:
            continue
        out.append(r)
    return out


def _lourdes_actives(data: dict, now: float) -> list[dict]:
    return [o for o in data["operations"] if o["etat"] == "en_cours" and now < o["expire"] and _pid_vivant(o.get("pid"))]


def _journal(decision: str, objet: str, raison: str, acteur: str, **extra) -> None:
    try:
        from . import journal
        journal.ecrire("admission", acteur=acteur or "?", objet=objet, decision=decision, raison=raison, **extra)
    except Exception:  # noqa: BLE001 — le journal ne bloque jamais un lancement
        pass


def demander(*, origine: str, projet: str, issue: str, agent: str, worktree: str = "", classe: str = "",
             role: str = "", plan: str = "", relecture: bool = False, acteur: str = "", forcer: bool = False,
             now: float | None = None) -> dict:
    """Demande l'admission d'un départ. Renvoie {"reservation", "fiche", "avertissements"} ou lève Refus.

    `fiche` : affectation effective (plan approuvé) ou None (lancement manuel : le routeur choisit ensuite).
    `forcer` (humain devant un terminal seulement, vérifié par l'appelant) : passe outre la capacité,
    jamais les pauses, l'observation, les doublons, les jetons ni le plan.
    """
    now = now or time.time()
    objet = f"{projet}:{issue}:{agent}"
    if origine not in ORIGINES:
        raise Refus("origine", f"origine de lancement inconnue « {origine} »")
    classe = classe or classe_pour_role(role)
    if classe not in CLASSES:
        raise Refus("config", f"classe de charge inconnue « {classe} » (valeurs : {', '.join(CLASSES)})")
    lourde = CLASSES[classe]
    avertissements: list[str] = []

    def _refus(code: str, raison: str) -> Refus:
        _journal("refuse", objet, raison, acteur or origine, code=code, origine=origine)
        return Refus(code, raison)

    with store.locked(LOCK):
        s = config.settings()
        erreurs = config.valider(s)
        if erreurs:
            raise _refus("config", "configuration invalide, aucun lancement : " + " ; ".join(erreurs))
        from . import pauses
        causes = pauses.actives()
        if causes:
            raise _refus("pause", pauses.texte(causes) + ". Aucun nouveau lancement tant qu'une cause reste.")
        agents, err = ag.status_all()
        if agents is None:
            raise _refus("observation", f"état des agents illisible ({err}) : on ne lance rien à l'aveugle")
        from . import poste
        busy = sum(1 for a in agents if a["status"] in ag.BUSY)
        visibles = {a["worktree"].lower() for a in agents}
        cap = poste.capacite(busy, now)
        res_data = store.read_json(RESERVATIONS, _vide_res())
        actives = _actives(res_data, visibles, now)
        total = busy + len(actives)
        if total >= cap["max"]:
            detail = f" (plafond {cap['base']} réduit : {' ; '.join(cap['raisons'])})" if cap["raisons"] else ""
            raison = (f"{total}/{cap['max']} places occupées (dont {len(actives)} réservation(s) en attente){detail} : "
                      "attends qu'un agent termine.")
            if not forcer:
                raise _refus("capacite", raison)
            avertissements.append("capacité dépassée volontairement (--forcer) : " + raison)
        if lourde:
            maxi = int(s["admission"].get("operations_lourdes_max", 1))
            lourdes = store.read_json(LOURDES, _vide_lourdes())
            en_cours = len(_lourdes_actives(lourdes, now)) + sum(1 for r in actives if r.get("lourde"))
            # Les agents visibles dont la tâche est de classe lourde comptent aussi.
            from . import taches
            fiches = taches.toutes()
            for a in agents:
                if a["status"] not in ag.BUSY:
                    continue
                t = taches.pour_agent(a["project"], a["worktree"], fiches, a.get("workdir", ""))
                if t and CLASSES.get(t.get("classe") or classe_pour_role(t.get("role", "")), False):
                    en_cours += 1
            if en_cours >= maxi:
                raise _refus("lourde", f"{en_cours}/{maxi} opération(s) lourde(s) en cours ({classe} refusée) : "
                                       "attends la fin d'une compilation, d'un test ou d'un rendu.")
        for r in actives:
            if (r["projet"], r["issue"], r["agent"]) == (projet, issue.upper(), agent):
                raise _refus("doublon", f"{objet} a déjà une réservation en attente ({r['id']}, {r['origine']}) : "
                                        "pas de double lancement.")
            if worktree and r.get("worktree") == worktree:
                raise _refus("doublon", f"le worktree {worktree} est déjà réservé ({r['id']})")
        if worktree and worktree.lower() in visibles and origine != "reprise":
            raise _refus("doublon", f"un agent travaille déjà dans le worktree {worktree}")
        from . import usage
        resume = usage.summary()
        epuises = {p for p in usage.PROVIDERS if resume[p]["niveau"] == "epuise"}
        fiche = None
        if plan:
            try:
                fiche = plans.authorize_launch(plan, projet, issue, agent, busy=busy, visible=visibles,
                                               max_agents=None, epuises=epuises, relecture=relecture)
            except plans.BudgetError as exc:
                reprises = [usage.fmt_reset(resume[p].get("reprise")) for p in sorted(epuises) if resume[p].get("reprise")]
                suite = f" (remise à zéro : {', '.join(reprises)})" if reprises else ""
                raise _refus("budget", f"{exc}{suite}") from exc
            except plans.PlanError as exc:
                raise _refus("plan", str(exc)) from exc
            agent = fiche["agent"]
        elif agent in epuises:
            raise _refus("budget", f"jetons {agent} épuisés : choisis l'autre fournisseur ou attends la remise à zéro")
        elif agent not in ("claude", "codex", "auto"):
            raise _refus("config", f"agent inconnu « {agent} »")

        def _reserver(data):
            data["seq"] += 1
            r = {"id": f"R-{data['seq']:05d}", "ts": now, "expire": now + 60 * int(s["admission"].get("reservation_min", 15)),
                 "origine": origine, "acteur": acteur or origine, "projet": projet, "issue": issue.upper(),
                 "agent": agent, "worktree": worktree, "classe": classe, "lourde": lourde, "plan": plan or "",
                 "etat": "reservee", "tache": ""}
            data["reservations"].append(r)
            data["reservations"] = data["reservations"][-500:]
            return r

        r = store.update_json(RESERVATIONS, _vide_res(), _reserver)
    _journal("admis", objet, f"{origine}, classe {classe}, {total + 1}/{cap['max']} places", acteur or origine,
             reservation=r["id"], origine=origine, plan=plan or None)
    return {"reservation": r["id"], "fiche": fiche, "avertissements": avertissements, "classe": classe}


def confirmer(res_id: str, tache_id: str, worktree: str = "") -> bool:
    """Le lancement a créé sa fiche de tâche : la réservation la suit jusqu'à l'apparition de l'agent."""

    def _set(data):
        for r in data["reservations"]:
            if r["id"] == res_id.upper():
                r["etat"], r["tache"] = "confirmee", tache_id
                if worktree:
                    r["worktree"] = worktree
                return True
        return False

    return store.update_json(RESERVATIONS, _vide_res(), _set)


def liberer(res_id: str, raison: str = "", acteur: str = "") -> bool:
    """Le lancement a échoué avant de démarrer : la place est rendue tout de suite."""

    def _set(data):
        for r in data["reservations"]:
            if r["id"] == res_id.upper() and r["etat"] in ("reservee", "confirmee"):
                r["etat"], r["fin"] = "liberee", time.time()
                return dict(r)
        return None

    r = store.update_json(RESERVATIONS, _vide_res(), _set)
    if r:
        _journal("liberee", f"{r['projet']}:{r['issue']}:{r['agent']}", raison, acteur or r["origine"], reservation=r["id"])
    return bool(r)


def reconcilier(agents: list[dict], now: float | None = None) -> list[dict]:
    """Appelé par le démon à chaque tour : marque démarrées les réservations dont l'agent est visible,
    expire celles qui n'ont jamais abouti (et rend leur élément de plan relançable). Renvoie les expirées."""
    now = now or time.time()
    visibles = {a["worktree"].lower() for a in agents}
    expirees: list[dict] = []

    def _maj(data):
        for r in data["reservations"]:
            if r["etat"] not in ("reservee", "confirmee"):
                continue
            if r.get("worktree") and r["worktree"].lower() in visibles:
                r["etat"], r["fin"] = "demarree", now
            elif now >= r["expire"]:
                r["etat"], r["fin"] = "expiree", now
                expirees.append(dict(r))
        data["reservations"] = [r for r in data["reservations"]
                                if r["etat"] in ("reservee", "confirmee") or now - r.get("fin", r["ts"]) < 7 * 86400]

    with store.locked(LOCK):
        store.update_json(RESERVATIONS, _vide_res(), _maj)
    for r in expirees:
        libere = False
        if r.get("plan") and not r.get("tache"):
            # Sans fiche de tâche, personne d'autre ne rendra l'élément de plan : on le fait ici.
            try:
                plans.release(r["plan"], r["projet"], r["issue"], r["agent"])
                libere = True
            except plans.PlanError:
                pass
        _journal("expiree", f"{r['projet']}:{r['issue']}:{r['agent']}",
                 "lancement jamais visible" + (" ; élément de plan rendu" if libere else ""), "demon", reservation=r["id"])
        store.feed_add("erreur", f"réservation {r['id']} expirée : {r['projet']} {r['issue']} ({r['agent']}) n'a jamais démarré"
                       + (f" — relançable dans {r['plan']}" if libere else ""))
    return expirees


def en_attente(now: float | None = None) -> list[dict]:
    """Réservations qui comptent encore (pour l'affichage)."""
    now = now or time.time()
    data = store.read_json(RESERVATIONS, _vide_res())
    return [r for r in data["reservations"] if r["etat"] in ("reservee", "confirmee") and now < r["expire"]]


# --- Opérations lourdes ---------------------------------------------------------------------------

def lourde_debut(classe: str, *, worktree: str = "", desc: str = "", pid: int | None = None,
                 duree_min: int = 120, acteur: str = "", now: float | None = None) -> dict:
    """Déclare le début d'une opération lourde. Lève Refus(« lourde ») s'il n'y a plus de place."""
    now = now or time.time()
    if classe not in CLASSES or not CLASSES[classe]:
        raise Refus("config", f"« {classe} » n'est pas une classe lourde ({', '.join(c for c, l in CLASSES.items() if l)})")
    with store.locked(LOCK):
        s = config.settings()
        if config.valider(s):
            raise Refus("config", "configuration invalide : corrige-la (jarvis doctor)")
        maxi = int(s["admission"].get("operations_lourdes_max", 1))

        def _add(data):
            actives = _lourdes_actives(data, now)
            if len(actives) >= maxi:
                qui = ", ".join(f"{o['classe']} ({o.get('worktree') or o['id']})" for o in actives)
                raise Refus("lourde", f"{len(actives)}/{maxi} opération(s) lourde(s) en cours : {qui}. Attends ou réessaie.")
            data["seq"] += 1
            o = {"id": f"L-{data['seq']:05d}", "ts": now, "expire": now + min(LOURDE_DUREE_MAX, 60 * max(1, duree_min)),
                 "classe": classe, "worktree": worktree, "desc": desc[:120], "pid": pid, "acteur": acteur, "etat": "en_cours"}
            data["operations"].append(o)
            data["operations"] = data["operations"][-300:]
            return o

        o = store.update_json(LOURDES, _vide_lourdes(), _add)
    _journal("lourde_debut", f"{classe}:{worktree or '-'}", desc, acteur or "agent", operation=o["id"])
    return o


def lourde_fin(op_id: str, acteur: str = "") -> bool:
    def _set(data):
        for o in data["operations"]:
            if o["id"] == op_id.upper() and o["etat"] == "en_cours":
                o["etat"], o["fin"] = "terminee", time.time()
                return dict(o)
        return None

    o = store.update_json(LOURDES, _vide_lourdes(), _set)
    if o:
        _journal("lourde_fin", f"{o['classe']}:{o.get('worktree') or '-'}", "", acteur or o.get("acteur") or "agent",
                 operation=o["id"])
    return bool(o)


def lourdes_en_cours(now: float | None = None) -> list[dict]:
    return _lourdes_actives(store.read_json(LOURDES, _vide_lourdes()), now or time.time())


# --- Relances bornées -----------------------------------------------------------------------------

def relance_autorisee(cle: str, max_par_heure: int, now: float | None = None) -> tuple[bool, int]:
    """Compte une relance de `cle` (chef, agent…) si le plafond horaire n'est pas atteint.

    Renvoie (autorisée, relances dans l'heure écoulée, celle-ci comprise si autorisée).
    """
    now = now or time.time()

    def _maj(data):
        hist = [t for t in data.get(cle, []) if now - t < 3600]
        ok = len(hist) < max(0, int(max_par_heure))
        if ok:
            hist.append(now)
        data[cle] = hist
        return ok, len(hist)

    with store.locked(LOCK):
        ok, n = store.update_json(RELANCES, {}, _maj)
    _journal("relance" if ok else "relance_refusee", cle, f"{n}/{max_par_heure} dans l'heure", "demon")
    return ok, n


def texte_etat(now: float | None = None) -> str:
    now = now or time.time()
    res = en_attente(now)
    lourdes = lourdes_en_cours(now)
    s = config.settings()["admission"]
    out = [f"Admission — profil : {s.get('profil') or 'réglages par défaut'} · opérations lourdes : "
           f"{len(lourdes)}/{s.get('operations_lourdes_max', 1)} · réservations en attente : {len(res)}"]
    for r in res:
        out.append(f"  {r['id']} {r['projet']} {r['issue']} ({r['agent']}, {r['classe']}, {r['origine']}) "
                   f"expire dans {max(0, int((r['expire'] - now) / 60))} min")
    for o in lourdes:
        out.append(f"  {o['id']} {o['classe']} {o.get('worktree') or ''} {o.get('desc') or ''} "
                   f"(depuis {int((now - o['ts']) / 60)} min)")
    erreurs = config.valider()
    if erreurs:
        out.append("  ⚠ configuration invalide, admission fermée : " + " ; ".join(erreurs))
    return "\n".join(out)
