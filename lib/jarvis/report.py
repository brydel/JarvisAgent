"""Instantané de l'état (agents, plans, projets) en texte lisible par toi et par le chef."""

from __future__ import annotations

import time

from . import agents as ag
from . import config, plans, store


def snapshot() -> dict:
    agents, err = ag.status_all()
    s = config.settings()["general"]
    busy = [a for a in (agents or []) if a["status"] in ("working", "waiting")]
    return {
        "ts": time.time(),
        "agents": agents,
        "agents_error": err,
        "busy": len(busy),
        "max_agents": int(s.get("max_agents", 3)),
        "pending": plans.pending(),
        "active": plans.active(),
        "projects": config.projects(),
        "paused": store.paused(),
        "chef": ag.chef_running(),
    }


def text(snap: dict | None = None, detail: bool = True) -> str:
    snap = snap or snapshot()
    out = []
    head = f"Agents occupés : {snap['busy']}/{snap['max_agents']}"
    if snap["paused"]:
        head += " · ⏸ PAUSE (aucun nouveau lancement)"
    head += " · chef " + ("actif" if snap["chef"] else "arrêté")
    out.append(head)

    out.append("")
    out.append("AGENTS")
    if snap["agents"] is None:
        out.append(f"  ⚠ état illisible : {snap['agents_error']}")
    elif not snap["agents"]:
        out.append("  aucun agent suivi")
    else:
        icon = {"working": "🤖", "waiting": "💬", "done": "✅"}
        for a in snap["agents"]:
            line = (f"  {icon.get(a['status'], '•')} {a['project']}/{a['worktree']} "
                    f"[{ag.kind_label(a['kind'])}, {ag.STATUS_LABELS.get(a['status'], a['status'])}, "
                    f"{ag.fmt_elapsed(a['elapsed'])}]")
            if detail and a["title"]:
                line += f" — {a['title']}"
            out.append(line)

    out.append("")
    out.append("PLANS À VALIDER" if snap["pending"] else "PLANS À VALIDER : aucun")
    for p in snap["pending"]:
        out.append(plans.format_plan(p, detail))
    if snap["active"]:
        out.append("")
        out.append("PLANS APPROUVÉS EN COURS")
        for p in snap["active"]:
            out.append(plans.format_plan(p, detail))

    if detail:
        out.append("")
        out.append("PROJETS")
        projs = snap["projects"]
        if not projs:
            out.append("  aucun projet enregistré (jarvis projet ajouter)")
        for name, p in sorted(projs.items(), key=lambda kv: (kv[1]["priorite"], kv[0])):
            state = "" if p["actif"] else " (en pause)"
            linear = f", Linear : {p['linear']}" if p["linear"] else ""
            out.append(f"  P{p['priorite']} {name}{state} — {p['chemin']}{linear}")
            if p["description"]:
                out.append(f"     {p['description']}")
    return "\n".join(out)
