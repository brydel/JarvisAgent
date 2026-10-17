"""Rollback assisté d'une tâche : défaire, par de nouveaux commits « revert », ce qu'un agent a committé.

- L1 `proposer` : le diff de la branche de la tâche depuis sa base et la commande exacte à lancer. Rien ne bouge.
- L2 `demander` : la proposition part sur Telegram avec deux boutons ; seul TON clic « Revert » (ou ta commande
  dans un terminal) autorise `executer`, qui fait `git revert` dans le worktree de la tâche.

Jamais automatique. Refusé si un agent travaille encore dans ce worktree, si le worktree contient des
modifications non commitées, ou si la branche a bougé depuis la proposition (on ne défait que ce qu'on t'a
montré). Un revert crée des commits : rien n'est effacé de l'historique, et le revert lui-même se défait.
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

from . import store

FILE = "rollbacks.json"
VALIDITE = 24 * 3600
MAX_COMMITS = 30


class RollbackError(ValueError):
    pass


def _git(chemin: str, *args: str, ok_codes=(0,)) -> str:
    r = subprocess.run(["git", "-C", chemin, *args], capture_output=True, text=True, timeout=60)
    if r.returncode not in ok_codes:
        raise RollbackError(f"git {' '.join(args)} : {(r.stderr or r.stdout).strip()[:300]}")
    return r.stdout.strip()


def _base(chemin: str, enregistree: str = "") -> str:
    """Base de la branche : le commit noté au lancement (point de départ réel), sinon la branche principale LOCALE
    d'abord (workmux part du dépôt local : des commits de main non poussés ne sont pas ceux de la tâche)."""
    if enregistree:
        r = subprocess.run(["git", "-C", chemin, "merge-base", "HEAD", enregistree], capture_output=True, text=True, timeout=30)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    for ref in ("main", "master", "origin/main", "origin/master", "origin/HEAD"):
        r = subprocess.run(["git", "-C", chemin, "merge-base", "HEAD", ref], capture_output=True, text=True, timeout=30)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    raise RollbackError("branche de base introuvable (main, master)")


def proposer(tache_id: str) -> dict:
    """{"tache", "chemin", "base", "tete", "commits": [(sha, titre)], "diffstat", "commande", "sale"}."""
    from . import taches
    t = taches.get(tache_id)
    if not t:
        raise RollbackError(f"tâche {tache_id} introuvable")
    chemin = t.get("chemin") or ""
    if not chemin or not Path(chemin).is_dir():
        raise RollbackError(f"worktree de {t['id']} introuvable ({chemin or 'inconnu'})")
    base = _base(chemin, t.get("base") or "")
    tete = _git(chemin, "rev-parse", "HEAD")
    lignes = _git(chemin, "log", "--format=%H %s", "--no-merges", f"{base}..HEAD").splitlines()
    commits = [(ln[:40], ln[41:]) for ln in lignes if ln]
    if not commits:
        raise RollbackError(f"aucun commit de {t['id']} à défaire depuis la base {base[:8]}")
    diffstat = _git(chemin, "diff", "--stat", f"{base}..HEAD")
    sale = bool(_git(chemin, "status", "--porcelain"))
    commande = f"git -C {chemin} revert --no-edit " + " ".join(sha[:12] for sha, _ in commits)  # du plus récent au plus ancien
    return {"tache": t["id"], "projet": t["projet"], "issue": t["issue"], "chemin": chemin, "base": base, "tete": tete,
            "commits": commits, "diffstat": diffstat, "commande": commande, "sale": sale}


def texte(p: dict) -> str:
    out = [f"Rollback proposé pour {p['tache']} ({p['projet']} {p['issue']}) — {len(p['commits'])} commit(s) à défaire :"]
    out += [f"  {sha[:10]} {titre}" for sha, titre in p["commits"]]
    out += ["", p["diffstat"], "", "Commande (crée des commits « revert », n'efface rien) :", f"  {p['commande']}"]
    if p["sale"]:
        out.append("⚠ Le worktree contient des modifications non commitées : le revert sera refusé tant qu'elles restent.")
    return "\n".join(out)


def demander(tache_id: str, par: str = "chef") -> dict:
    """Enregistre la proposition (en attente) et l'envoie sur Telegram avec les boutons Revert / Garder."""
    p = proposer(tache_id)
    from . import notify
    from .telegram import MAX_LEN
    if len(p["commits"]) > MAX_COMMITS:
        raise RollbackError(f"{len(p['commits'])} commits : trop pour une validation par bouton (max {MAX_COMMITS}). "
                            "Relis « jarvis rollback proposer » et fais le revert toi-même au terminal.")
    message = "↩ " + texte(p)
    if len(message) > MAX_LEN:
        # Tous les commits doivent être visibles avant le clic : on retire le diffstat, jamais la liste.
        message = "↩ " + texte({**p, "diffstat": "(diffstat omis : trop long, voir jarvis rollback proposer)"})
    if len(message) > MAX_LEN:
        raise RollbackError("proposition trop longue pour Telegram : fais le revert toi-même au terminal")

    def _set(data):
        data[p["tache"]] = {"ts": time.time(), "statut": "en_attente", "tete": p["tete"], "base": p["base"],
                            "par": par, "commits": [sha for sha, _ in p["commits"]], "envoye": False}

    store.update_json(FILE, {}, _set)
    envoye = bool(notify.telegram(message, notify.rollback_buttons(p["tache"])))
    store.update_json(FILE, {}, lambda data: data[p["tache"]].update(envoye=envoye))
    p["envoye"] = envoye
    try:
        from . import journal
        journal.ecrire("politique", acteur=par, objet=f"rollback:{p['tache']}", decision="demande",
                       raison=f"{len(p['commits'])} commit(s)")
    except Exception:  # noqa: BLE001
        pass
    return p


def decider(tache_id: str, ok: bool, par: str) -> dict:
    """Décision humaine sur une demande en attente. `ok` : exécute le revert aussitôt."""
    tache_id = tache_id.upper()
    d = store.read_json(FILE, {}).get(tache_id)
    if not d or d["statut"] != "en_attente":
        raise RollbackError(f"aucune demande de rollback en attente pour {tache_id}")
    if time.time() - d["ts"] > VALIDITE:
        raise RollbackError("demande expirée (24 h) : refais « jarvis rollback demander »")

    def _set(data):
        data[tache_id]["statut"] = "approuve" if ok else "refuse"
        data[tache_id]["decide"], data[tache_id]["decide_par"] = time.time(), par

    store.update_json(FILE, {}, _set)
    try:
        from . import journal
        journal.ecrire("politique", acteur=par, objet=f"rollback:{tache_id}", decision="approuve" if ok else "refuse")
    except Exception:  # noqa: BLE001
        pass
    if not ok:
        return {"tache": tache_id, "execute": False}
    return executer(tache_id, par=par)


def executer(tache_id: str, par: str, autorise_terminal: bool = False) -> dict:
    """Fait le revert. Exige une approbation enregistrée (bouton Telegram) ou un humain au terminal."""
    from . import agents as ag
    from . import taches
    tache_id = tache_id.upper()
    d = store.read_json(FILE, {}).get(tache_id) or {}
    if not autorise_terminal and d.get("statut") != "approuve":
        raise RollbackError("rollback non approuvé : il faut ton clic « Revert » sur Telegram ou ta commande au terminal")
    p = proposer(tache_id)
    if d.get("tete") and d["tete"] != p["tete"]:
        raise RollbackError("la branche a bougé depuis la proposition : refais « jarvis rollback demander »")
    if d.get("commits") and [sha for sha, _ in p["commits"]] != d["commits"]:
        raise RollbackError("la liste des commits a changé depuis la proposition (base déplacée) : rien n'est fait, "
                            "refais « jarvis rollback demander »")
    if p["sale"]:
        raise RollbackError("le worktree contient des modifications non commitées : revert refusé")
    t = taches.get(tache_id)
    agents, _err = ag.status_all()
    if agents is None:
        raise RollbackError("état des agents illisible : on ne touche pas au worktree à l'aveugle")
    if any(a["status"] in ag.BUSY and (a.get("workdir") == p["chemin"] or a["worktree"] == t["worktree"]) for a in agents):
        raise RollbackError("un agent travaille encore dans ce worktree : arrête-le d'abord")
    shas = [sha for sha, _ in p["commits"]]
    try:
        r = subprocess.run(["git", "-C", p["chemin"], "-c", "user.name=Jarvis", "-c", "user.email=jarvis@localhost",
                            "revert", "--no-edit", *shas], capture_output=True, text=True, timeout=300)
        echec = (r.stderr or r.stdout).strip()[:300] if r.returncode != 0 else ""
    except subprocess.TimeoutExpired:
        echec = "git revert trop long (5 min)"
    if echec:
        # Revenir exactement à la tête proposée : ni revert partiel, ni état « revert en cours ».
        subprocess.run(["git", "-C", p["chemin"], "revert", "--abort"], capture_output=True, text=True, timeout=60)
        subprocess.run(["git", "-C", p["chemin"], "reset", "--hard", "-q", p["tete"]], capture_output=True, text=True,
                       timeout=60)
        raise RollbackError("revert interrompu, worktree remis à son état d'avant : " + echec)

    def _set(data):
        data.setdefault(tache_id, {}).update(statut="execute", execute=time.time(), execute_par=par)

    store.update_json(FILE, {}, _set)
    store.feed_add("systeme", f"rollback de {tache_id} : {len(shas)} commit(s) défaits par revert ({par})")
    try:
        from . import journal
        journal.ecrire("politique", acteur=par, objet=f"rollback:{tache_id}", decision="execute", raison=f"{len(shas)} revert(s)")
    except Exception:  # noqa: BLE001
        pass
    return {"tache": tache_id, "execute": True, "commits": shas}
