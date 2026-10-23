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
    tracked = {(a["session"], a["window"]) for a in agents if a["window"]}
    now = time.time()
    windows = tmux_agent_windows()
    panes = _pane_commands() if windows else {}
    arbre = None
    for a in agents:
        if not a["kind"]:
            a["kind"] = _kind_from_command(panes.get((a["session"], a["window"]), ""))
    for w in windows:
        if (w["session"], w["window"]) in tracked:
            continue
        kind = _kind_from_command(w["command"], panes.get((w["session"], w["window"]), ""))
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


def _pane_commands() -> dict[tuple[str, str], str]:
    """{(session, fenêtre): commandes des volets} — deux projets peuvent partager un nom de fenêtre."""
    if not shutil.which("tmux"):
        return {}
    try:
        res = _run(["tmux", "list-panes", "-a", "-F", "#{session_name}\t#{window_name}\t#{pane_current_command}"], timeout=5)
    except (subprocess.TimeoutExpired, OSError):
        return {}
    out: dict[tuple[str, str], str] = {}
    for line in res.stdout.splitlines():
        parts = line.split("\t", 2)
        if len(parts) != 3:
            continue
        session, window, command = parts
        key = (session, window)
        out[key] = f"{out.get(key, '')} {command}".strip()
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
    project, _, worktree = handle.rpartition(":")
    candidates = [w for w in tmux_agent_windows() if w["window"] == WINDOW_PREFIX + worktree
                  and (not project or config.project_for_path(w["path"]) == project)]
    if len(candidates) > 1:
        return "(aperçu indisponible : cible ambiguë, précise le projet et vérifie les sessions)"
    for w in candidates:
        try:
            res = _run(["tmux", "capture-pane", "-p", "-J", "-t", w["id"],
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
        saisie = _run(["tmux", "send-keys", "-t", _chef_win(), "-l", line], timeout=5)
        if saisie.returncode:
            return False
        validation = _run(["tmux", "send-keys", "-t", _chef_win(), "Enter"], timeout=5)
        return validation.returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


def _chef_file_verifiee():
    from . import store
    q = store.read_json(CHEF_QUEUE, None)
    if q is None and not store.existe(CHEF_QUEUE):
        return []
    if not isinstance(q, list) or any(not isinstance(x, (str, dict)) for x in q):
        raise ValueError("file du chef illisible : état conservé")
    for x in q:
        if isinstance(x, dict) and (not isinstance(x.get("id"), str) or not isinstance(x.get("empreinte"), str)
                                   or type(x.get("recu")) is not bool
                                   or (not x["recu"] and not isinstance(x.get("texte"), str))):
            raise ValueError("entrée de file du chef invalide : état conservé")
    return q


def chef_inject(text: str, *, message_id: str | None = None) -> bool:
    """Persiste avant remise. Une coupure ne vide plus les messages avant leur envoi.

    `message_id` permet au producteur de rejouer une remise sans réinjecter un message déjà acquitté.
    L'acquittement signifie « tapé dans tmux », pas « compris/exécuté par le modèle ». Une interruption
    entre le retour de tmux et cet acquittement peut encore dupliquer la ligne à la reprise.
    """
    if not chef_running():
        return False
    from . import store
    import hashlib
    line = " ".join(text.split())
    empreinte = hashlib.sha256(line.encode()).hexdigest()
    # Verrou distinct de celui du stockage : aucun commit DB ni verrou d'écriture JSON retenu pendant tmux.
    with store.locked(CHEF_QUEUE + ".delivery"):
        q = _chef_file_verifiee()
        if message_id is not None:
            if not isinstance(message_id, str) or not message_id or len(message_id) > 200:
                raise ValueError("identifiant du message hors bornes")
            ancien = next((x for x in q if isinstance(x, dict) and x["id"] == message_id), None)
            if ancien:
                if ancien["empreinte"] != empreinte:
                    raise ValueError("identifiant de message déjà utilisé avec un autre texte")
                return True
            entree = {"id": message_id, "texte": line, "empreinte": empreinte, "recu": False}
        else:
            entree = line  # format historique conservé pour les messages sans identifiant
        store.update_json(CHEF_QUEUE, [], lambda file: file.append(entree))
        _chef_flush_verrouille()
    return True


def _chef_flush_verrouille() -> int:
    from . import store
    delivered = 0
    while delivered < 50:
        q = _chef_file_verifiee()
        index = next((i for i, x in enumerate(q) if isinstance(x, str) or not x["recu"]), None)
        if index is None:
            break
        entree = q[index]
        line = entree if isinstance(entree, str) else entree["texte"]
        if not _type_into_chef(line):
            break  # l'entrée reste persistée, y compris si le processus meurt pendant la remise

        def acquitter(file):
            if index >= len(file) or file[index] != entree:
                raise ValueError("la file du chef a changé pendant la remise")
            if isinstance(entree, str):
                file.pop(index)
            else:
                file[index] = {"id": entree["id"], "empreinte": entree["empreinte"], "recu": True, "ts": time.time()}

        store.update_json(CHEF_QUEUE, [], acquitter)
        delivered += 1
    return delivered


def chef_flush_queue() -> int:
    """Remet puis acquitte chaque entrée sous un verrou inter-processus ; jamais de vidage anticipé."""
    from . import store
    if not chef_running() or chef_has_dialog():
        return 0
    with store.locked(CHEF_QUEUE + ".delivery"):
        return _chef_flush_verrouille()


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
