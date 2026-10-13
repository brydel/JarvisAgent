"""Instantané de l'état (agents, ateliers, plans, projets) en texte lisible par toi et par le chef."""

from __future__ import annotations

import time

from . import agents as ag
from . import config, plans, store

DEMON_FILE = "demon.json"


def demon_vivant(now: float | None = None) -> bool:
    """Le démon écrit son battement à chaque tour : sans battement récent, plus rien n'est surveillé."""
    beat = store.read_json(DEMON_FILE, {})
    poll = int(config.settings()["general"].get("poll_seconds", 20))
    return bool(beat) and (now or time.time()) - beat.get("ts", 0) < max(90, poll * 4)


def enrichir(agents: list[dict]) -> list[dict]:
    """Ajoute à chaque agent sa fiche du registre : rôle, modèle, effort, issue."""
    from . import roles, taches
    fiches = taches.toutes()
    for a in agents:
        t = taches.pour_agent(a["project"], a["worktree"], fiches, a.get("workdir", ""))
        role = roles.ou_defaut(t["role"] if t else None)
        a["tache"] = t
        a["role"] = role["nom"] if t else ""
        a["equipe"] = role["equipe"] if t else "Hors registre"
        a["sigle"] = role["sigle"] if t else "···"
        a["modele"] = (t or {}).get("modele", "")
        a["effort"] = (t or {}).get("effort", "")
        a["issue"] = (t or {}).get("issue", "")
    return agents


def snapshot() -> dict:
    agents, err = ag.status_all()
    s = config.settings()["general"]
    if agents is not None:
        try:
            enrichir(agents)
        except Exception:  # noqa: BLE001 — l'état doit s'afficher même si le registre est illisible
            for a in agents:
                a.setdefault("tache", None)
                a.setdefault("role", "")
                a.setdefault("equipe", "Hors registre")
                a.setdefault("sigle", "···")
                a.setdefault("modele", "")
                a.setdefault("effort", "")
                a.setdefault("issue", "")
    busy = [a for a in (agents or []) if a["status"] in ag.BUSY]
    try:
        from . import usage
        jetons = usage.summary()
    except Exception:  # noqa: BLE001 — l'état doit s'afficher même sans données de jetons
        jetons = None
    base = int(s.get("max_agents", 3))
    try:
        from . import poste
        cap = poste.capacite(len(busy))
    except Exception:  # noqa: BLE001
        cap = {"max": base, "base": base, "raisons": []}
    try:
        from . import livrables, modeles
        livr = livrables.recents(8)
        props = modeles.propositions()
    except Exception:  # noqa: BLE001
        livr, props = [], []
    return {
        "usage": jetons,
        "ts": time.time(),
        "agents": agents,
        "agents_error": err,
        "busy": len(busy),
        "max_agents": cap["max"],
        "max_base": cap["base"],
        "capacite_raisons": cap["raisons"],
        "pending": plans.pending(),
        "active": plans.active(),
        "propositions": props,
        "livrables": livr,
        "projects": config.projects(),
        "paused": store.paused(),
        "chef": ag.chef_running(),
        "demon": demon_vivant(),
    }


def _ligne_agent(a: dict, detail: bool) -> str:
    from . import modeles
    icon = {"working": "🤖", "waiting": "💬", "done": "✅", "untracked": "🌀"}
    qui = modeles.libelle(ag.kind_label(a["kind"]).lower(), a.get("modele", ""), a.get("effort", "")) \
        if a.get("modele") else ag.kind_label(a["kind"])
    line = (f"  {icon.get(a['status'], '•')} {a['project']}/{a['worktree']} "
            f"[{qui}, {ag.STATUS_LABELS.get(a['status'], a['status'])}, {ag.fmt_elapsed(a['elapsed'])}]")
    if detail and a["title"]:
        line += f" — {a['title']}"
    return line


def usine(snap: dict | None = None) -> str:
    """Les ateliers : chaque équipe, ses rôles, et qui travaille sur quoi en ce moment."""
    from . import roles
    snap = snap or snapshot()
    agents = snap["agents"] or []
    out = [f"USINE — {snap['busy']}/{snap['max_agents']} agents occupés"
           + (" · ⏸ PAUSE" if snap["paused"] else "")]
    if snap.get("capacite_raisons"):
        out.append(f"  capacité réduite ({snap['max_base']} → {snap['max_agents']}) : {' ; '.join(snap['capacite_raisons'])}")
    par_role: dict[str, list[dict]] = {}
    for a in agents:
        par_role.setdefault(a.get("role") or "", []).append(a)
    for equipe, membres in roles.par_equipe():
        actifs = [(r, a) for r in membres for a in par_role.get(r["nom"], [])]
        libres = [r["titre"] for r in membres if not par_role.get(r["nom"])]
        out.append("")
        out.append(equipe.upper())
        for r, a in actifs:
            out.append(f"  {r['emoji']} {r['titre']}")
            out.append("  " + _ligne_agent(a, detail=True))
        if libres:
            out.append("  libres : " + ", ".join(libres))
    hors = par_role.get("", [])
    if hors:
        out += ["", "HORS REGISTRE (lancés à la main)"]
        out += [_ligne_agent(a, detail=True) for a in hors]
    return "\n".join(out)


def text(snap: dict | None = None, detail: bool = True) -> str:
    snap = snap or snapshot()
    out = []
    head = f"Agents occupés : {snap['busy']}/{snap['max_agents']}"
    if snap.get("capacite_raisons"):
        head += f" (plafond {snap['max_base']} réduit : {' ; '.join(snap['capacite_raisons'])})"
    if snap["paused"]:
        head += " · ⏸ PAUSE (aucun nouveau lancement)"
    head += " · chef " + ("actif" if snap["chef"] else "arrêté")
    if not snap.get("demon", True):
        head += " · ⚠ démon arrêté (jarvis start)"
    out.append(head)

    out.append("")
    out.append("JETONS")
    try:
        from . import usage
        out.extend("  " + ln for ln in usage.text(snap.get("usage")).splitlines())
    except Exception as exc:  # noqa: BLE001
        out.append(f"  ⚠ lecture impossible : {exc}")

    out.append("")
    out.append("AGENTS")
    if snap["agents"] is None:
        out.append(f"  ⚠ état illisible : {snap['agents_error']}")
    elif not snap["agents"]:
        out.append("  aucun agent suivi")
    else:
        from . import roles
        for a in snap["agents"]:
            line = _ligne_agent(a, detail)
            if a.get("role"):
                r = roles.ou_defaut(a["role"])
                line = line.replace(f"{a['project']}/{a['worktree']}", f"{r['emoji']} {r['titre']} · {a['project']}/{a['worktree']}", 1)
            out.append(line)

    out.append("")
    out.append("PLANS À VALIDER" if snap["pending"] else "PLANS À VALIDER : aucun")
    for p in snap["pending"]:
        out.append(plans.format_plan(p, detail))
    if snap.get("propositions"):
        from . import modeles
        out.append("")
        out.append("MODÈLES À VALIDER")
        for i in snap["propositions"]:
            out.append(modeles.format_proposition(i))
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
