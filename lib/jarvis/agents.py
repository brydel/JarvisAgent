"""Lecture de l'état des agents (workmux) et communication avec le chef (tmux)."""

from __future__ import annotations

import json
import shutil
import subprocess

from . import config

STATUS_LABELS = {"working": "travaille", "waiting": "attend", "done": "terminé"}


def _run(cmd: list[str], timeout: int = 20, input_text: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, input=input_text)


def status_all() -> tuple[list[dict] | None, str]:
    """Agents suivis par workmux dans tous les projets. Renvoie (agents, erreur).

    `agents` vaut None si l'observation a échoué : l'appelant ne doit alors rien conclure.
    """
    if not shutil.which("workmux"):
        return None, "workmux introuvable"
    try:
        res = _run(["workmux", "status", "--all", "--json"])
    except (subprocess.TimeoutExpired, OSError) as exc:
        return None, f"workmux status : {exc}"
    if res.returncode != 0:
        lines = (res.stderr or res.stdout or "").strip().splitlines()
        return None, lines[-1] if lines else f"workmux status a échoué (code {res.returncode})"
    try:
        data = json.loads(res.stdout or "{}")
    except json.JSONDecodeError:
        return None, "réponse JSON illisible de workmux status"
    agents = []
    for a in data.get("agents", []) or []:
        agents.append({
            "worktree": a.get("worktree") or "?",
            "branch": a.get("branch") or "",
            "project": a.get("project") or config.project_for_path(a.get("workdir") or "") or "?",
            "status": a.get("status") or "?",
            "elapsed": int(a.get("elapsed_secs") or 0),
            "title": (a.get("title") or "").strip(),
            "kind": a.get("agent_kind") or "",
            "session": a.get("session") or "",
            "window": a.get("window_name") or "",
            "pane": a.get("pane_id") or "",
            "workdir": a.get("workdir") or "",
        })
    order = {"waiting": 0, "working": 1, "done": 2}
    agents.sort(key=lambda a: (order.get(a["status"], 3), a["project"], a["worktree"]))
    return agents, ""


def target(agent: dict) -> str:
    return f"{agent['project']}:{agent['worktree']}" if agent.get("project") not in (None, "", "?") else agent["worktree"]


def capture(handle: str, lines: int = 60) -> str:
    try:
        res = _run(["workmux", "capture", handle, "-n", str(lines)], timeout=15)
    except (subprocess.TimeoutExpired, OSError) as exc:
        return f"(aperçu indisponible : {exc})"
    return res.stdout if res.returncode == 0 else f"(aperçu indisponible : {(res.stderr or '').strip()})"


def send(handle: str, text: str) -> tuple[bool, str]:
    try:
        res = _run(["workmux", "send", handle, text], timeout=15)
    except (subprocess.TimeoutExpired, OSError) as exc:
        return False, str(exc)
    return res.returncode == 0, (res.stderr or res.stdout).strip()


# --- tmux ------------------------------------------------------------------------

def tmux_windows(session: str = config.SESSION) -> list[str]:
    if not shutil.which("tmux"):
        return []
    try:
        res = _run(["tmux", "list-windows", "-t", session, "-F", "#{window_name}"], timeout=5)
    except (subprocess.TimeoutExpired, OSError):
        return []
    return res.stdout.split() if res.returncode == 0 else []


def chef_running() -> bool:
    return config.CHEF_WINDOW in tmux_windows()


CHEF_QUEUE = "chef_queue.json"
# Éléments propres aux boîtes de choix de Claude Code (permission, sélection) : le curseur « ❯ »
# devant une option numérotée, ou les libellés de la boîte de permission.
DIALOG_MARKERS = ("❯ 1.", "❯ 2.", "❯ 3.", "Do you want to proceed", "don't ask again")


def _chef_win() -> str:
    return f"{config.SESSION}:{config.CHEF_WINDOW}"


def chef_has_dialog() -> bool:
    """Vrai si le chef affiche une question à choix : y taper Entrée validerait une option à sa place.

    On ne regarde que le bas de l'écran visible (pas l'historique) : une boîte de dialogue est
    toujours en bas, et un vieux texte qui défile ne doit pas bloquer les messages.
    """
    try:
        res = _run(["tmux", "capture-pane", "-p", "-t", _chef_win()], timeout=5)
    except (subprocess.TimeoutExpired, OSError):
        return True  # dans le doute, on n'écrit pas
    if res.returncode != 0:
        return True
    tail = [ln for ln in res.stdout.splitlines() if ln.strip()][-10:]
    return any(m in ln for ln in tail for m in DIALOG_MARKERS)


def _type_into_chef(line: str) -> bool:
    if chef_has_dialog():  # nouvelle vérification juste avant d'écrire : l'écran a pu changer
        return False
    try:
        _run(["tmux", "send-keys", "-t", _chef_win(), "-l", line], timeout=5)
        _run(["tmux", "send-keys", "-t", _chef_win(), "Enter"], timeout=5)
        return True
    except (subprocess.TimeoutExpired, OSError):
        return False


def chef_inject(text: str) -> bool:
    """Transmet un message au chef comme si tu l'écrivais.

    Si le chef affiche une boîte de dialogue, le message attend dans une file que le démon
    vide dès que l'écran est libre. Renvoie False seulement si le chef n'est pas lancé.
    """
    if not chef_running():
        return False
    from . import store  # import tardif
    line = " ".join(text.split())  # une seule ligne : un retour à la ligne enverrait le message trop tôt
    if not _type_into_chef(line):
        store.update_json(CHEF_QUEUE, [], lambda q: q.append(line))
    return True


def chef_flush_queue() -> int:
    """Envoie les messages en attente si l'écran du chef est libre. Renvoie le nombre envoyé."""
    from . import store
    if not chef_running() or chef_has_dialog():
        return 0
    sent: list[str] = []

    def _take(q):
        sent.extend(q)
        q.clear()

    store.update_json(CHEF_QUEUE, [], _take)
    delivered = 0
    for i, line in enumerate(sent):
        if not _type_into_chef(line):
            # Une boîte de dialogue est apparue entre-temps : le reste repart en tête de file.
            rest = sent[i:]

            def _requeue(q, rest=rest):
                q[:0] = rest

            store.update_json(CHEF_QUEUE, [], _requeue)
            break
        delivered += 1
    return delivered


def select_window(session: str, window: str) -> bool:
    if not (session and window and shutil.which("tmux")):
        return False
    try:
        res = _run(["tmux", "select-window", "-t", f"{session}:{window}"], timeout=5)
        if res.returncode == 0:
            _run(["tmux", "switch-client", "-t", session], timeout=5)
        return res.returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


def fmt_elapsed(secs: int) -> str:
    secs = max(0, int(secs))
    if secs < 60:
        return f"{secs}s"
    if secs < 3600:
        return f"{secs // 60}min"
    return f"{secs // 3600}h{(secs % 3600) // 60:02d}"


def kind_label(kind: str) -> str:
    k = (kind or "").lower()
    if "claude" in k:
        return "Claude"
    if "codex" in k:
        return "Codex"
    return kind or "?"
