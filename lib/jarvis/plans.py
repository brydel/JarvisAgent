"""Plans proposés par le chef et validés par toi (Telegram, cockpit ou terminal).

Un plan liste des lancements précis : (projet, issue Linear, agent). Le chef ne peut
lancer QUE ce qui figure dans un plan approuvé, une seule fois par élément.
Un « plan de nuit » est un plan plus long, validé avant de dormir.
"""

from __future__ import annotations

import re
import time

from . import store

PLANS_FILE = "plans.json"
AGENTS = {"claude": "claude", "cc": "claude", "codex": "codex", "cx": "codex"}
VALIDITE = {"vague": 24 * 3600, "nuit": 16 * 3600}  # durée de validité après approbation

_ITEM_RE = re.compile(r"^(?P<projet>[\w.-]+):(?P<issue>[A-Za-z]+-\d+):(?P<agent>[a-z]+)(?::(?P<desc>.+))?$")


class PlanError(ValueError):
    pass


def parse_item(spec: str) -> dict:
    """« repriceo:BIS-71:codex:garde-fous coûts » → élément de plan."""
    m = _ITEM_RE.match(spec.strip())
    if not m:
        raise PlanError(f"élément invalide « {spec} » (attendu projet:ISSUE:agent[:description])")
    agent = AGENTS.get(m["agent"])
    if not agent:
        raise PlanError(f"agent inconnu « {m['agent']} » dans « {spec} » (claude ou codex)")
    return {
        "projet": m["projet"],
        "issue": m["issue"].upper(),
        "agent": agent,
        "desc": (m["desc"] or "").strip(),
        "lance": False,
        "lance_ts": None,
    }


def _empty() -> dict:
    return {"seq": 0, "plans": []}


def create(titre: str, items: list[dict], mode: str = "vague", resume: str = "", origine: str = "chef") -> dict:
    if not items:
        raise PlanError("un plan doit contenir au moins un élément")
    if mode not in VALIDITE:
        raise PlanError("mode inconnu (vague ou nuit)")

    def _add(data):
        data["seq"] += 1
        plan = {
            "id": f"P-{data['seq']:04d}",
            "titre": titre.strip() or "Plan sans titre",
            "mode": mode,
            "resume": resume.strip(),
            "statut": "en_attente",
            "origine": origine,
            "cree": time.time(),
            "decide": None,
            "par": None,
            "raison": "",
            "items": items,
        }
        data["plans"].append(plan)
        data["plans"] = data["plans"][-200:]
        return plan

    plan = store.update_json(PLANS_FILE, _empty(), _add)
    store.feed_add("plan_new", f"{plan['id']} proposé : {plan['titre']} ({len(items)} tâche(s), {mode})", plan=plan["id"])
    return plan


def all_plans() -> list[dict]:
    return store.read_json(PLANS_FILE, _empty())["plans"]


def get(plan_id: str) -> dict | None:
    plan_id = plan_id.upper()
    return next((p for p in all_plans() if p["id"] == plan_id), None)


def pending() -> list[dict]:
    return [p for p in all_plans() if p["statut"] == "en_attente"]


def active() -> list[dict]:
    """Plans approuvés, encore valides, avec des éléments non lancés."""
    now = time.time()
    return [
        p for p in all_plans()
        if p["statut"] == "approuve" and now - (p["decide"] or 0) < VALIDITE[p["mode"]]
    ]


def decide(plan_id: str, ok: bool, par: str, raison: str = "") -> dict:
    """Approuve ou refuse un plan, puis prévient le chef. Renvoie le plan mis à jour."""
    plan_id = plan_id.upper()

    def _decide(data):
        for p in data["plans"]:
            if p["id"] == plan_id:
                if p["statut"] != "en_attente":
                    deja = {"approuve": "approuvé", "refuse": "refusé", "termine": "terminé"}
                    raise PlanError(f"{plan_id} est déjà {deja.get(p['statut'], p['statut'])}")
                p["statut"] = "approuve" if ok else "refuse"
                p["decide"] = time.time()
                p["par"] = par
                p["raison"] = raison
                return dict(p)
        raise PlanError(f"plan {plan_id} introuvable")

    plan = store.update_json(PLANS_FILE, _empty(), _decide)
    if ok:
        store.feed_add("plan_ok", f"{plan_id} approuvé ({par})", plan=plan_id)
        msg = (f"[JARVIS] Plan {plan_id} APPROUVÉ par ton humain ({par}). "
               f"Lance ses tâches maintenant avec : jarvis task --plan {plan_id} --projet <projet> <ISSUE> <agent> [desc].")
    else:
        store.feed_add("plan_no", f"{plan_id} refusé ({par})" + (f" : {raison}" if raison else ""), plan=plan_id)
        msg = (f"[JARVIS] Plan {plan_id} REFUSÉ par ton humain ({par})."
               + (f" Raison : {raison}." if raison else "")
               + " Remets-toi en question, puis propose un plan corrigé.")
    from . import agents  # import tardif : évite une boucle d'imports
    agents.chef_inject(msg)
    return plan


RECENT_LAUNCH = 300  # s : un agent tout juste lancé peut mettre ce temps à apparaître dans workmux


def authorize_launch(plan_id: str, projet: str, issue: str, agent: str, *,
                     busy: int | None = None, visible: set[str] | None = None,
                     max_agents: int | None = None) -> dict:
    """Vérifie qu'un lancement figure dans un plan approuvé et le marque comme lancé.

    Si `max_agents` est donné, la capacité est vérifiée sous le même verrou : agents occupés
    (`busy`) + lancements récents pas encore visibles dans workmux (`visible` = worktrees vus).
    Lève PlanError avec une explication si ce n'est pas autorisé.
    """
    plan_id, issue, agent = plan_id.upper(), issue.upper(), AGENTS.get(agent, agent)
    visible = {v.lower() for v in (visible or set())}

    def _check(data):
        if max_agents is not None:
            now = time.time()
            pending_start = sum(
                1 for p in data["plans"] for i in p["items"]
                if i["lance"] and now - (i["lance_ts"] or 0) < RECENT_LAUNCH
                and not any(w.startswith(i["issue"].lower()) for w in visible)
            )
            total = (busy or 0) + pending_start
            if total >= max_agents:
                raise PlanError(f"{total}/{max_agents} agents occupés (dont {pending_start} en démarrage) : "
                                "attends qu'un agent termine.")
        for p in data["plans"]:
            if p["id"] != plan_id:
                continue
            if p["statut"] == "en_attente":
                raise PlanError(f"{plan_id} attend encore la validation de ton humain")
            if p["statut"] == "refuse":
                raise PlanError(f"{plan_id} a été refusé")
            if p["statut"] == "termine":
                raise PlanError(f"{plan_id} est terminé : toutes ses tâches ont été lancées")
            if time.time() - (p["decide"] or 0) > VALIDITE[p["mode"]]:
                raise PlanError(f"{plan_id} a expiré : propose un nouveau plan")
            for item in p["items"]:
                if (item["projet"], item["issue"], item["agent"]) == (projet, issue, agent):
                    if item["lance"]:
                        raise PlanError(f"{issue} ({agent}) a déjà été lancé avec {plan_id}")
                    item["lance"] = True
                    item["lance_ts"] = time.time()
                    if all(i["lance"] for i in p["items"]):
                        p["statut"] = "termine"
                    return dict(item)
            raise PlanError(f"{projet}:{issue}:{agent} ne fait pas partie de {plan_id}")
        raise PlanError(f"plan {plan_id} introuvable")

    return store.update_json(PLANS_FILE, _empty(), _check)


def release(plan_id: str, projet: str, issue: str, agent: str) -> None:
    """Rend un élément relançable après un échec technique du lancement (workmux add)."""
    plan_id, issue, agent = plan_id.upper(), issue.upper(), AGENTS.get(agent, agent)

    def _release(data):
        for p in data["plans"]:
            if p["id"] != plan_id:
                continue
            for item in p["items"]:
                if (item["projet"], item["issue"], item["agent"]) == (projet, issue, agent):
                    item["lance"], item["lance_ts"] = False, None
                    if p["statut"] == "termine":
                        p["statut"] = "approuve"
                    return
        raise PlanError(f"{projet}:{issue}:{agent} introuvable dans {plan_id}")

    store.update_json(PLANS_FILE, _empty(), _release)


def format_plan(p: dict, detail: bool = True) -> str:
    statut = {"en_attente": "⏳ en attente", "approuve": "✅ approuvé", "refuse": "✋ refusé", "termine": "🏁 terminé"}
    lines = [f"{p['id']} — {p['titre']}  [{p['mode']}, {statut.get(p['statut'], p['statut'])}]"]
    if detail:
        if p.get("resume"):
            lines.append(f"  Pourquoi : {p['resume']}")
        for i in p["items"]:
            mark = "✓" if i["lance"] else "·"
            desc = f" — {i['desc']}" if i["desc"] else ""
            lines.append(f"  {mark} {i['projet']} {i['issue']} → {i['agent']}{desc}")
    return "\n".join(lines)
