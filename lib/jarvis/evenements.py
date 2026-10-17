"""Journal d'événements par tâche, pour reconstruire après coup ce qui s'est passé (audit, « replay » partiel).

Chaque événement porte la tâche (T-xxxxx), un type, l'heure et un petit instantané d'état (statut, jetons
connus, modèle). Types écrits par le code : admis, lance, tour_agent (fin d'un tour : l'agent attend ou a fini),
reprise (il repart), echec, verdict, plafond, termine, perdue. `rejouer` y ajoute, à partir des registres
existants, la proposition et l'approbation du plan.

Reconstruction, pas voyage dans le temps : rien n'est réexécuté, aucun modèle n'est rappelé.
"""

from __future__ import annotations

import json
import time

from . import store

FILE = "evenements.jsonl"
MAX_BYTES = 10_000_000
TYPES = ("plan_propose", "plan_approuve", "admis", "lance", "tour_agent", "reprise", "echec", "verdict", "plafond",
         "termine", "perdue")


def ecrire(tache: str, type_: str, ts: float | None = None, **donnees) -> dict:
    if type_ not in TYPES:
        raise ValueError(f"type d'événement inconnu « {type_} »")
    ev = {"ts": ts or time.time(), "tache": tache, "type": type_,
          **{k: v for k, v in donnees.items() if v not in (None, "")}}
    path = store.state_path(FILE)
    with store.locked(FILE):
        if path.exists() and path.stat().st_size > MAX_BYTES:
            lignes = path.read_text(encoding="utf-8").splitlines()
            tmp = path.with_suffix(".tmp")
            tmp.write_text("\n".join(lignes[len(lignes) // 2:]) + "\n", encoding="utf-8")
            tmp.replace(path)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(ev, ensure_ascii=False) + "\n")
    return ev


def sans_echec(tache: str, type_: str, **donnees) -> None:
    """Écrit un événement sans jamais faire échouer l'appelant (le journal est un plus)."""
    try:
        ecrire(tache, type_, **donnees)
    except Exception:  # noqa: BLE001
        pass


def lire(tache: str | None = None) -> list[dict]:
    try:
        lignes = store.state_path(FILE).read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return []
    out = []
    for ln in lignes:
        try:
            ev = json.loads(ln)
        except json.JSONDecodeError:
            continue
        if tache is None or ev.get("tache") == tache:
            out.append(ev)
    return out


def chronologie(tache_id: str) -> list[dict]:
    """Événements de la tâche, complétés par le plan (proposition, approbation), dans l'ordre du temps."""
    from . import plans, taches
    fiche = taches.get(tache_id)
    if not fiche:
        raise ValueError(f"tâche {tache_id} introuvable")
    evs = list(lire(fiche["id"]))
    if fiche.get("plan"):
        p = plans.get(fiche["plan"])
        if p:
            evs.append({"ts": p["cree"], "tache": fiche["id"], "type": "plan_propose", "plan": p["id"], "titre": p["titre"],
                        "origine": p.get("origine")})
            if p.get("decide") and p.get("statut") in ("approuve", "termine"):
                evs.append({"ts": p["decide"], "tache": fiche["id"], "type": "plan_approuve", "plan": p["id"], "par": p.get("par")})
    evs.sort(key=lambda e: e["ts"])
    for i, e in enumerate(evs, 1):
        e["n"] = i
    return evs


def texte(evs: list[dict], depuis: int = 1) -> str:
    if not evs:
        return "Aucun événement."
    t0 = evs[0]["ts"]
    libelles = {"plan_propose": "plan proposé", "plan_approuve": "plan approuvé", "admis": "admis",
                "lance": "agent lancé", "tour_agent": "fin de tour", "reprise": "reprise", "echec": "échec classé",
                "verdict": "verdict de relecture", "plafond": "plafond de jetons atteint", "termine": "terminé",
                "perdue": "interrompu"}
    out = []
    for e in evs:
        if e["n"] < depuis:
            continue
        ecart = e["ts"] - t0
        rel = f"+{int(ecart // 3600)} h {int(ecart % 3600 // 60):02d}" if ecart >= 3600 else f"+{int(ecart // 60)} min"
        details = {k: v for k, v in e.items() if k not in ("ts", "tache", "type", "n")}
        quand = time.strftime("%d/%m %H:%M:%S", time.localtime(e["ts"]))
        out.append(f"{e['n']:>3}. {quand} ({rel:>9})  {libelles.get(e['type'], e['type'])}"
                   + (" — " + ", ".join(f"{k}={v}" for k, v in details.items()) if details else ""))
    return "\n".join(out)
