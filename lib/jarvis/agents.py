"""Lecture de l'état des agents (workmux) et communication avec le chef (tmux)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time

from . import config

STATUS_LABELS = {"working": "travaille", "waiting": "attend", "done": "terminé", "untracked": "actif ?",
                 "idle": "inactif ?", "silent": "silencieux"}
# « untracked » : fenêtre d'agent visible dans tmux mais absente de workmux status (ex. Codex
# avant la fin de son premier tour). Comptée comme occupée : on ne relance jamais par-dessus.
# « idle » : même cas, sans activité depuis IDLE_AFTER secondes ET plus aucun programme dans le volet
# (il ne reste qu'un shell) : fini, la place est libérée (sinon une vieille fenêtre bloquerait la
# capacité toute la nuit).
# « silent » : sans activité depuis IDLE_AFTER secondes mais Claude Code ou Codex tourne encore dans le
# volet : vivant, peut-être bloqué, jamais « terminé » faute de sortie. Compté comme occupé.
BUSY = ("working", "waiting", "untracked", "silent")
IDLE_AFTER = 20 * 60
WINDOW_PREFIX = "wm-"
NON_AGENTS = (config.CHEF_WINDOW, "daemon", "cockpit", "reprise")


def tmux_agent_windows() -> list[dict]:
    """Fenêtres d'agents workmux (« wm-… ») dans toutes les sessions tmux."""
    if not shutil.which("tmux"):
        return []
    fmt = "\t".join(["#{session_name}", "#{window_name}", "#{pane_current_path}",
                     "#{pane_current_command}", "#{window_activity}", "#{window_id}", "#{pane_pid}"])
    try:
        res = _run(["tmux", "list-windows", "-a", "-F", fmt], timeout=5)
    except (subprocess.TimeoutExpired, OSError):
        return []
    out = []
    for line in res.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) not in (6, 7) or not parts[1].startswith(WINDOW_PREFIX):
            continue
        session, window, path, command, activity, wid = parts[:6]
        pid = parts[6] if len(parts) == 7 else ""
        out.append({"session": session, "window": window, "path": path, "command": command,
                    "activity": int(activity) if activity.isdigit() else 0, "id": wid,
                    "pid": int(pid) if pid.isdigit() else 0})
    return out


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
        if a.get("window_name") in NON_AGENTS:
            # Le chef est une session Claude suivie par les hooks workmux comme les autres :
            # ce n'est pas un agent. Sinon chaque fin de tour du chef le réveillerait lui-même (boucle).
            # Même règle pour les fenêtres de service de Jarvis (démon, cockpit).
            continue
        agents.append({
            "worktree": a.get("worktree") or "?",
            "branch": a.get("branch") or "",
            # Le nom du registre de Jarvis d'abord (par le dossier) : workmux, lui, nomme le projet
            # d'après le dossier du dépôt, qui peut différer.
            "project": config.project_for_path(a.get("workdir") or "") or a.get("project") or "?",
            "status": a.get("status") or "?",
            "elapsed": int(a.get("elapsed_secs") or 0),
            "title": (a.get("title") or "").strip(),
            "kind": a.get("agent_kind") or "",
            "session": a.get("session") or "",
            "window": a.get("window_name") or "",
            "pane": a.get("pane_id") or "",
            "workdir": a.get("workdir") or "",
        })
    # Agents que workmux ne suit pas (encore) : repérés par leur fenêtre tmux.
    tracked = {a["window"] for a in agents if a["window"]}
    now = time.time()
    windows = tmux_agent_windows()
    panes = _pane_commands() if windows else {}
    arbre = None
    for a in agents:
        if not a["kind"] and a["window"] in panes:
            a["kind"] = _kind_from_command(panes[a["window"]])
    for w in windows:
        if w["window"] in tracked:
            continue
        kind = _kind_from_command(w["command"], panes.get(w["window"], ""))
        idle = max(0, int(now - w["activity"])) if w["activity"] else 0
        status, titre = "untracked", f"non suivi par workmux · dernière activité il y a {fmt_elapsed(idle)}"
        if idle >= IDLE_AFTER:
            # Silence prolongé : terminé seulement si plus rien ne tourne dans le volet. Un programme
            # encore vivant est « silencieux » (bloqué ?), pas fini : sa place n'est pas libérée.
            arbre = _arbre() if arbre is None else arbre
            vivant = programme_actif(w["pid"], arbre) if w.get("pid") else None
            if vivant is None:
                vivant = w["command"] not in SHELLS  # sans /proc : ce que dit tmux
            status = "silent" if vivant else "idle"
            titre = (f"silencieux depuis {fmt_elapsed(idle)} (programme encore actif)" if vivant
                     else f"plus aucun programme · inactif depuis {fmt_elapsed(idle)}")
        agents.append({
            "worktree": w["window"][len(WINDOW_PREFIX):],
            "branch": "",
            "project": config.project_for_path(w["path"]) or "?",
            "status": status,
            "elapsed": idle,
            "title": titre,
            "kind": kind,
            "session": w["session"],
            "window": w["window"],
            "pane": "",
            "workdir": w["path"],
        })
    order = {"waiting": 0, "untracked": 1, "silent": 1, "working": 2, "done": 3}
    agents.sort(key=lambda a: (order.get(a["status"], 4), a["project"], a["worktree"]))
    return agents, ""


def _pane_commands() -> dict[str, str]:
    """{fenêtre: commandes de tous ses volets} — l'agent n'est pas forcément le volet actif."""
    if not shutil.which("tmux"):
        return {}
    try:
        res = _run(["tmux", "list-panes", "-a", "-F", "#{window_name}\t#{pane_current_command}"], timeout=5)
    except (subprocess.TimeoutExpired, OSError):
        return {}
    out: dict[str, str] = {}
    for line in res.stdout.splitlines():
        w, _, c = line.partition("\t")
        out[w] = f"{out.get(w, '')} {c}".strip()
    return out


def _kind_from_command(*commands: str) -> str:
    cmd = " ".join(commands).lower()
    return "codex" if "codex" in cmd else ("claude" if "claude" in cmd else "")


CLOSABLE = ("done", "idle")


def find(handle: str) -> dict | None:
    """Agent désigné par « projet:worktree » (ou « worktree » seul)."""
    found, _ = status_all()
    project, _, worktree = handle.rpartition(":")
    for a in found or []:
        if a["worktree"] == worktree and (not project or a["project"] == project):
            return a
    return None


def close(agent: dict) -> tuple[bool, str]:
    """Ferme la fenêtre d'un agent terminé. Le worktree, la branche et la conversation restent."""
    if agent["status"] not in CLOSABLE:
        return False, f"{target(agent)} est « {STATUS_LABELS.get(agent['status'], agent['status'])} » : je ne ferme que les agents terminés"
    proj = config.projects().get(agent.get("project") or "")
    if proj and shutil.which("workmux") and agent["status"] == "done":
        try:
            res = subprocess.run(["workmux", "close", agent["worktree"]], cwd=proj["chemin"],
                                 capture_output=True, text=True, timeout=20)
            if res.returncode == 0:
                return True, f"fenêtre de {target(agent)} fermée"
        except (subprocess.TimeoutExpired, OSError):
            pass
    # Par identifiant (@12) : un nom contenant un point (« v1.2 ») serait lu comme « fenêtre.volet ».
    wid = next((w["id"] for w in tmux_agent_windows()
                if w["window"] == agent.get("window") and w["session"] == agent.get("session")), "")
    if wid:
        try:
            res = _run(["tmux", "kill-window", "-t", wid], timeout=5)
        except (subprocess.TimeoutExpired, OSError) as exc:
            return False, str(exc)
        if res.returncode == 0:
            return True, f"fenêtre de {target(agent)} fermée"
        return False, (res.stderr or "tmux kill-window a échoué").strip()
    return False, f"fenêtre de {target(agent)} introuvable"


def target(agent: dict) -> str:
    return f"{agent['project']}:{agent['worktree']}" if agent.get("project") not in (None, "", "?") else agent["worktree"]


def capture(handle: str, lines: int = 60) -> str:
    """Sortie récente d'un agent. Passe par tmux si workmux ne connaît pas l'agent."""
    err = ""
    if shutil.which("workmux"):
        try:
            res = _run(["workmux", "capture", handle, "-n", str(lines)], timeout=15)
            if res.returncode == 0:
                return res.stdout
            err = (res.stderr or "").strip()
        except (subprocess.TimeoutExpired, OSError) as exc:
            err = str(exc)
    worktree = handle.split(":", 1)[-1]
    for w in tmux_agent_windows():
        if w["window"] == WINDOW_PREFIX + worktree:
            try:
                res = _run(["tmux", "capture-pane", "-p", "-J", "-t", f"{w['session']}:{w['window']}",
                            "-S", f"-{lines}"], timeout=10)
            except (subprocess.TimeoutExpired, OSError) as exc:
                return f"(aperçu indisponible : {exc})"
            if res.returncode == 0:
                return res.stdout
    return f"(aperçu indisponible : {err or 'agent introuvable'})"


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


SHELLS = ("bash", "sh", "zsh", "fish", "dash")


def _arbre() -> dict[int, list[tuple[int, str]]] | None:
    """{pid parent: [(pid, nom)]} d'après /proc, ou None si /proc est illisible."""
    enfants: dict[int, list[tuple[int, str]]] = {}
    try:
        entrees = os.listdir("/proc")
    except OSError:
        return None
    for e in entrees:
        if not e.isdigit():
            continue
        try:
            with open(f"/proc/{e}/stat", encoding="utf-8", errors="replace") as fh:
                stat = fh.read()
        except OSError:
            continue  # processus terminé entre-temps
        # « pid (nom) état ppid … » : le nom peut contenir des espaces ou des parenthèses.
        nom = stat[stat.find("(") + 1:stat.rfind(")")]
        reste = stat[stat.rfind(")") + 2:].split()
        if len(reste) >= 2 and reste[1].isdigit():
            enfants.setdefault(int(reste[1]), []).append((int(e), nom))
    return enfants


def programme_actif(pane_pid: int, arbre: dict | None = None) -> bool | None:
    """Vrai si autre chose qu'un shell tourne dans le volet (le volet lui-même ou un descendant).

    On ne peut pas se fier à #{pane_current_command} : quand tmux lance « claude …; exec bash »,
    il rapporte le shell parent, pas Claude Code. None si /proc est illisible.
    """
    arbre = _arbre() if arbre is None else arbre
    if arbre is None:
        return None
    try:
        with open(f"/proc/{pane_pid}/comm", encoding="utf-8", errors="replace") as fh:
            if fh.read().strip() not in SHELLS:
                return True
    except OSError:
        return False  # le volet n'a plus de processus
    a_voir = [pane_pid]
    while a_voir:
        for pid, nom in arbre.get(a_voir.pop(), []):
            if nom not in SHELLS:
                return True
            a_voir.append(pid)
    return False


def chef_etat() -> str:
    """« actif », « absent » (pas de fenêtre) ou « eteint » (fenêtre ouverte sur un simple shell)."""
    if not shutil.which("tmux"):
        return "absent"
    try:
        res = _run(["tmux", "list-panes", "-t", _chef_win(), "-F", "#{pane_pid}\t#{pane_current_command}"], timeout=5)
    except (subprocess.TimeoutExpired, OSError):
        return "absent"
    if res.returncode != 0:
        return "absent"
    volets = [ln.split("\t", 1) for ln in res.stdout.splitlines() if "\t" in ln]
    if not volets:
        return "absent"
    arbre = _arbre()
    for pid, commande in volets:
        actif = programme_actif(int(pid), arbre) if pid.isdigit() else None
        if actif is None:  # sans /proc : on se contente de ce que dit tmux
            actif = commande.strip() not in SHELLS
        if actif:
            return "actif"
    return "eteint"


def chef_running() -> bool:
    """Vrai si la fenêtre du chef existe ET que Claude Code (ou un autre programme) y tourne.

    Quand Claude Code s'arrête, la fenêtre reste ouverte sur un shell (pour lire l'erreur) : y taper
    un message exécuterait son texte comme une commande. Ce n'est plus un chef.
    """
    return chef_etat() == "actif"


def chef_idle_secs() -> int | None:
    """Secondes depuis la dernière activité visible du chef (None s'il n'est pas lancé)."""
    try:
        res = _run(["tmux", "list-windows", "-t", config.SESSION, "-F", "#{window_name}\t#{window_activity}"], timeout=5)
    except (subprocess.TimeoutExpired, OSError):
        return None
    for line in res.stdout.splitlines():
        name, _, act = line.partition("\t")
        if name == config.CHEF_WINDOW and act.isdigit():
            return max(0, int(time.time()) - int(act))
    return None


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


def window_idle() -> dict[str, int]:
    """{fenêtre d'agent: secondes depuis sa dernière sortie à l'écran}."""
    now = time.time()
    return {w["window"]: max(0, int(now - w["activity"])) for w in tmux_agent_windows() if w["activity"]}


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
