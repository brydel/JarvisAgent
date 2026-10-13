"""Cockpit plein écran de Jarvis (curses, bibliothèque standard).

  ╭─ AGENTS ───────────────────────────╮╭─ À VALIDER ─────────╮
  │ ▶ repriceo  bis-71  Codex  travaille ││ P-0003 ◇ Vague auth  │
  │ ? jobpilot  bis-12  Claude attend    │╰─────────────────────╯
  ╰─────────────────────────────────────╯╭─ PROJETS ───────────╮
  ╭─ FIL D'ACTIVITÉ / APERÇU ──────────────────────────────────╮
"""

from __future__ import annotations

import curses
import locale
import os
import threading
import time
import unicodedata

from . import agents as ag
from . import config, plans, report, store

REFRESH_DATA = 3.0     # secondes entre deux lectures de l'état des agents
REFRESH_PREVIEW = 3.0  # secondes entre deux captures de l'agent sélectionné

STATUS = {  # symbole, libellé, couleur
    "working": ("▶", "travaille", "cyan"),
    "waiting": ("?", "attend", "yellow"),
    "done": ("✓", "terminé", "green"),
    "untracked": ("~", "actif ?", "magenta"),
    "idle": ("·", "inactif ?", "dim"),
}
FEED = {  # type d'événement → symbole, couleur
    "agent_done": ("✓", "green"), "agent_waiting": ("?", "yellow"), "agent_working": ("▶", "cyan"),
    "agent_gone": ("○", "dim"), "plan_new": ("◇", "magenta"), "plan_ok": ("✓", "green"),
    "plan_no": ("✗", "red"), "task": ("»", "cyan"), "chef": ("◆", "cyan"), "question": ("?", "yellow"),
    "toi": ("›", "white"), "note": ("•", "magenta"), "systeme": ("·", "dim"), "erreur": ("!", "red"),
}

HELP_NORMAL = [
    ("Tab", "panneau"), ("↑↓", "choisir"), ("Entrée", "ouvrir"), ("o", "approuver"), ("x", "refuser"),
    ("m", "parler au chef"), ("e", "écrire à l'agent"), ("p", "aperçu"), ("c", "chef"), ("P", "pause"), ("q", "quitter"),
]


# --- Largeur d'affichage (émojis et lettres larges comptent double) -----------

def _w(ch: str) -> int:
    if unicodedata.combining(ch):
        return 0
    return 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1


def width(s: str) -> int:
    return sum(_w(c) for c in s)


def cut(s: str, maxw: int) -> str:
    """Tronque à `maxw` colonnes, avec « … » si nécessaire."""
    if maxw <= 0:
        return ""
    if width(s) <= maxw:
        return s
    out, w = [], 0
    for c in s:
        cw = _w(c)
        if w + cw > maxw - 1:
            break
        out.append(c)
        w += cw
    return "".join(out) + "…"


def pad(s: str, n: int) -> str:
    s = cut(s, n)
    return s + " " * (n - width(s))


# --- Données en arrière-plan ------------------------------------------------------

class Data:
    """Lit l'état dans un fil séparé pour que l'interface ne gèle jamais."""

    def __init__(self):
        self.lock = threading.Lock()
        self.snap: dict | None = None
        self.preview_target: str | None = None
        self.preview_text = ""
        self.stop = threading.Event()
        threading.Thread(target=self._loop, daemon=True).start()
        threading.Thread(target=self._preview_loop, daemon=True).start()

    def _loop(self):
        while not self.stop.is_set():
            try:
                snap = report.snapshot()
            except Exception as exc:  # noqa: BLE001
                snap = {"agents": None, "agents_error": str(exc), "busy": 0, "max_agents": 0,
                        "pending": [], "active": [], "projects": {}, "paused": False, "chef": False, "ts": time.time()}
            with self.lock:
                self.snap = snap
            self.stop.wait(REFRESH_DATA)

    def _preview_loop(self):
        while not self.stop.is_set():
            target = self.preview_target
            if target:
                text = ag.capture(target, lines=120)
                with self.lock:
                    if self.preview_target == target:
                        self.preview_text = text
            self.stop.wait(REFRESH_PREVIEW)

    def get(self):
        with self.lock:
            return self.snap, self.preview_text


# --- Interface --------------------------------------------------------------------

class Cockpit:
    def __init__(self, scr):
        self.scr = scr
        self.data = Data()
        self.focus = "agents"
        self.sel = {"agents": 0, "plans": 0}
        self.mode = "normal"          # normal | saisie
        self.input_target = "chef"    # chef | agent
        self.buffer = ""
        self.preview = False
        self.flash_msg, self.flash_until, self.flash_color = "", 0.0, "cyan"
        self.colors: dict[str, int] = {}
        self._init_curses()

    # -- curses
    def _init_curses(self):
        try:
            curses.curs_set(0)
        except curses.error:
            pass  # certains terminaux ne savent pas masquer le curseur
        self.scr.keypad(True)
        self.scr.timeout(400)
        if curses.has_colors():
            curses.start_color()
            try:
                curses.use_default_colors()
                bg = -1
            except curses.error:
                bg = curses.COLOR_BLACK
            pairs = {
                "cyan": curses.COLOR_CYAN, "green": curses.COLOR_GREEN, "yellow": curses.COLOR_YELLOW,
                "red": curses.COLOR_RED, "magenta": curses.COLOR_MAGENTA, "white": curses.COLOR_WHITE,
                "blue": curses.COLOR_BLUE,
            }
            for i, (name, col) in enumerate(pairs.items(), start=1):
                curses.init_pair(i, col, bg)
                self.colors[name] = curses.color_pair(i)
            curses.init_pair(20, curses.COLOR_BLACK, curses.COLOR_CYAN)
            self.colors["header"] = curses.color_pair(20)
            self.colors["dim"] = self.colors["white"] | curses.A_DIM
        for k in ("cyan", "green", "yellow", "red", "magenta", "white", "blue", "header", "dim"):
            self.colors.setdefault(k, 0)

    def c(self, name: str, bold: bool = False) -> int:
        return self.colors.get(name, 0) | (curses.A_BOLD if bold else 0)

    def put(self, y: int, x: int, text: str, attr: int = 0, maxw: int | None = None):
        h, w = self.scr.getmaxyx()
        if y < 0 or y >= h or x >= w:
            return
        room = w - x - (1 if y == h - 1 else 0)  # la dernière case de l'écran ne s'écrit pas
        if maxw is not None:
            room = min(room, maxw)
        # Un retour à la ligne dans un texte (ex. un bilan) déborderait sur les panneaux voisins.
        text = " ".join(str(text).replace("\t", " ").splitlines())
        try:
            self.scr.addstr(y, x, cut(text, room), attr)
        except curses.error:
            pass

    def flash(self, msg: str, color: str = "cyan", secs: float = 4.0):
        self.flash_msg, self.flash_until, self.flash_color = msg, time.time() + secs, color

    def box(self, y: int, x: int, h: int, w: int, title: str, focused: bool = False, right: str = ""):
        if h < 2 or w < 4:
            return
        col = self.c("cyan", True) if focused else self.c("dim")
        self.put(y, x, "╭" + "─" * (w - 2) + "╮", col)
        for i in range(1, h - 1):
            self.put(y + i, x, "│", col)
            self.put(y + i, x + w - 1, "│", col)
        self.put(y + h - 1, x, "╰" + "─" * (w - 2) + "╯", col)
        self.put(y, x + 2, f" {title} ", self.c("cyan" if focused else "white", True))
        if right:
            self.put(y, x + w - width(right) - 4, f" {right} ", self.c("dim"))

    # -- sélection
    def agents_list(self, snap) -> list[dict]:
        return (snap or {}).get("agents") or []

    def plans_list(self, snap) -> list[dict]:
        return (snap or {}).get("pending") or []

    def selected_agent(self, snap) -> dict | None:
        lst = self.agents_list(snap)
        if not lst:
            return None
        self.sel["agents"] = max(0, min(self.sel["agents"], len(lst) - 1))
        return lst[self.sel["agents"]]

    def selected_plan(self, snap) -> dict | None:
        lst = self.plans_list(snap)
        if not lst:
            return None
        self.sel["plans"] = max(0, min(self.sel["plans"], len(lst) - 1))
        return lst[self.sel["plans"]]

    # -- dessin
    def draw(self):
        snap, preview_text = self.data.get()
        self.scr.erase()
        h, w = self.scr.getmaxyx()
        if h < 20 or w < 70:
            self.put(0, 0, "JARVIS · agrandis la fenêtre (70×20 minimum)", self.c("yellow", True))
            self.scr.refresh()
            return

        self._draw_header(snap, w)
        self._draw_tokens(snap, 2, w)
        body_top, body_bottom = 3, h - 3
        body_h = body_bottom - body_top
        top_h = max(8, int(body_h * 0.58))
        left_w = int(w * 0.62)
        right_w = w - left_w

        self._draw_agents(snap, body_top, 0, top_h, left_w)
        plans_h = max(5, int(top_h * 0.55))
        self._draw_plans(snap, body_top, left_w, plans_h, right_w)
        self._draw_projects(snap, body_top + plans_h, left_w, top_h - plans_h, right_w)
        bottom_h = body_h - top_h
        if self.preview:
            self._draw_preview(snap, preview_text, body_top + top_h, 0, bottom_h, w)
        else:
            self._draw_feed(body_top + top_h, 0, bottom_h, w)
        self._draw_footer(h, w)
        self.scr.refresh()

    def _draw_tokens(self, snap, y, w):
        """Jauges de jetons : Claude et Codex, fenêtres 5 h et semaine, colorées selon les seuils."""
        from . import usage
        s = (snap or {}).get("usage")
        if not s:
            self.put(y, 1, "Jetons : données indisponibles", self.c("dim"))
            return
        alert, stop = usage.thresholds()
        x = 1
        for name in usage.PROVIDERS:
            u = s[name]
            lvl = u["niveau"]
            dot_col = {"ok": "green", "alerte": "yellow", "epuise": "red"}.get(lvl, "dim")
            self.put(y, x, "●", self.c(dot_col, True))
            self.put(y, x + 2, name.capitalize(), self.c("white", True))
            x += 2 + len(name) + 1
            shown = False
            for key, label in (("5h", "5h"), ("semaine", "sem")):
                win = u.get(key)
                if not win:
                    continue
                shown = True
                pct = win["used"]
                col = "red" if pct >= stop else ("yellow" if pct >= alert else "green")
                seg = f"{label} {usage.bar(pct, 8)} {pct:3.0f}%"
                self.put(y, x, seg, self.c(col, True))
                x += width(seg) + 2
            if not shown:
                self.put(y, x, "en attente de données", self.c("dim"))
                x += 23
            if lvl == "epuise" and u.get("reprise"):
                seg = f"→ {usage.fmt_reset(u['reprise'])}"
                self.put(y, x, seg, self.c("red"))
                x += width(seg) + 1
            x += 3
            if x >= w - 20:
                break

    def _draw_header(self, snap, w):
        now = time.strftime("%H:%M:%S")
        title = " ◆ J A R V I S  ·  poste de pilotage "
        self.put(0, 0, " " * (w - 1), self.c("header"))
        self.put(0, 0, title, self.c("header") | curses.A_BOLD)
        self.put(0, w - len(now) - 2, now, self.c("header") | curses.A_BOLD)

        if not snap:
            self.put(1, 1, "chargement…", self.c("dim"))
            return
        agents = snap.get("agents") or []
        waiting = sum(1 for a in agents if a["status"] == "waiting")
        done = sum(1 for a in agents if a["status"] == "done")
        chips = [
            (f"Agents {snap['busy']}/{snap['max_agents']}", "cyan"),
            (f"? {waiting} en attente", "yellow" if waiting else "dim"),
            (f"✓ {done} terminés", "green" if done else "dim"),
            (f"◇ {len(snap['pending'])} plan(s) à valider", "magenta" if snap["pending"] else "dim"),
            ("● chef actif" if snap["chef"] else "○ chef arrêté", "green" if snap["chef"] else "red"),
        ]
        tg = config.settings()["telegram"].get("chat_id")
        chips.append(("● Telegram" if tg else "○ Telegram", "green" if tg else "dim"))
        if snap["paused"]:
            chips.append(("⏸ PAUSE", "red"))
        x = 1
        for text, col in chips:
            self.put(1, x, text, self.c(col, True))
            x += width(text) + 3
        if snap.get("agents") is None:
            self.put(1, x, f"⚠ {snap.get('agents_error', '')}", self.c("red"))

    def _draw_agents(self, snap, y, x, h, w):
        agents = self.agents_list(snap)
        focused = self.focus == "agents"
        self.box(y, x, h, w, "AGENTS", focused, f"{len(agents)}")
        inner = w - 4
        cols = [("", 2), ("PROJET", 12), ("TÂCHE", 26), ("AGENT", 7), ("ÉTAT", 10), ("DURÉE", 7)]
        title_w = max(0, inner - sum(c for _, c in cols) - len(cols))
        hx = x + 2
        for name, cw in cols + [("TITRE", title_w)]:
            self.put(y + 1, hx, pad(name, cw), self.c("dim", True))
            hx += cw + 1
        if not agents:
            msg = "Aucun agent en cours." if snap and snap.get("agents") is not None else "État des agents indisponible."
            self.put(y + 3, x + 3, msg, self.c("dim"))
            self.put(y + 4, x + 3, "Le chef propose un plan → tu l'approuves → les agents démarrent.", self.c("dim"))
            return
        sel = self.selected_agent(snap)
        rows = h - 3
        start = max(0, self.sel["agents"] - rows + 1)
        for i, a in enumerate(agents[start:start + rows]):
            ry = y + 2 + i
            sym, label, col = STATUS.get(a["status"], ("·", a["status"], "white"))
            is_sel = focused and a is sel
            base = curses.A_REVERSE if is_sel else 0
            if is_sel:
                self.put(ry, x + 1, " " * (w - 2), curses.A_REVERSE)
            cells = [
                (sym, self.c(col, True)), (a["project"], self.c("white", True)), (a["worktree"], self.c("white")),
                (ag.kind_label(a["kind"]), self.c("blue", True)), (label, self.c(col)),
                (ag.fmt_elapsed(a["elapsed"]), self.c("dim")),
            ]
            cx = x + 2
            for (text, attr), (_, cw) in zip(cells, cols):
                self.put(ry, cx, pad(text, cw), attr | base)
                cx += cw + 1
            self.put(ry, cx, pad(a["title"], title_w), self.c("dim") | base)

    def _draw_plans(self, snap, y, x, h, w):
        pending = self.plans_list(snap)
        active = (snap or {}).get("active") or []
        focused = self.focus == "plans"
        self.box(y, x, h, w, "À VALIDER", focused, f"{len(pending)}")
        ry, maxy = y + 1, y + h - 1
        sel = self.selected_plan(snap)
        if not pending:
            self.put(ry, x + 2, "Rien à valider.", self.c("dim"))
            ry += 1
        for p in pending:
            if ry >= maxy:
                break
            is_sel = focused and p is sel
            attr = self.c("magenta", True) | (curses.A_REVERSE if is_sel else 0)
            tag = "nuit" if p["mode"] == "nuit" else "vague"
            self.put(ry, x + 2, pad(f"◇ {p['id']} {p['titre']} [{tag}]", w - 4), attr)
            ry += 1
            for it in p["items"]:
                if ry >= maxy:
                    break
                self.put(ry, x + 4, f"{it['projet']} {it['issue']} → {it['agent']}", self.c("white"), w - 6)
                ry += 1
        if active and ry < maxy - 1:
            ry += 1
            self.put(ry, x + 2, "En cours", self.c("dim", True))
            ry += 1
            for p in active:
                if ry >= maxy:
                    break
                n = sum(1 for i in p["items"] if i["lance"])
                self.put(ry, x + 2, f"✓ {p['id']} {p['titre']} ({n}/{len(p['items'])} lancées)", self.c("green"), w - 4)
                ry += 1

    def _draw_projects(self, snap, y, x, h, w):
        projs = (snap or {}).get("projects") or {}
        self.box(y, x, h, w, "PROJETS", False, f"{len(projs)}")
        counts: dict[str, int] = {}
        for a in self.agents_list(snap):
            if a["status"] in ag.BUSY:
                counts[a["project"]] = counts.get(a["project"], 0) + 1
        if not projs:
            self.put(y + 1, x + 2, "Aucun projet : jarvis projet ajouter", self.c("dim"), w - 4)
            return
        ry = y + 1
        for name, p in sorted(projs.items(), key=lambda kv: (kv[1]["priorite"], kv[0])):
            if ry >= y + h - 1:
                break
            n = counts.get(name, 0)
            dot, col = ("●", "green") if n else ("○", "dim")
            if not p["actif"]:
                dot, col = ("⏸", "dim")
            self.put(ry, x + 2, dot, self.c(col, True))
            self.put(ry, x + 4, f"P{p['priorite']} {name}", self.c("white", True), w - 16)
            self.put(ry, x + w - 12, f"{n} agent{'s' if n > 1 else ''}", self.c(col))
            ry += 1

    def _draw_feed(self, y, x, h, w):
        self.box(y, x, h, w, "FIL D'ACTIVITÉ", False, "p : aperçu de l'agent")
        events = store.feed_tail(max(1, h - 2))
        for i, e in enumerate(events[-(h - 2):]):
            sym, col = FEED.get(e.get("type", ""), ("•", "white"))
            ts = time.strftime("%H:%M", time.localtime(e.get("ts", 0)))
            ry = y + 1 + i
            self.put(ry, x + 2, ts, self.c("dim"))
            self.put(ry, x + 8, sym, self.c(col, True))
            self.put(ry, x + 10, e.get("texte", ""), self.c("white"), w - 12)

    def _draw_preview(self, snap, text, y, x, h, w):
        a = self.selected_agent(snap)
        title = f"APERÇU · {a['project']}/{a['worktree']} ({ag.kind_label(a['kind'])})" if a else "APERÇU"
        self.box(y, x, h, w, title, False, "p : revenir au fil")
        if not a:
            self.put(y + 1, x + 2, "Choisis un agent dans le panneau AGENTS.", self.c("dim"))
            return
        lines = [ln for ln in (text or "chargement…").splitlines()]
        while lines and not lines[-1].strip():
            lines.pop()
        for i, ln in enumerate(lines[-(h - 2):]):
            self.put(y + 1 + i, x + 2, ln.expandtabs(4), self.c("white"), w - 4)

    def _draw_footer(self, h, w):
        if self.mode == "saisie":
            who = "au chef" if self.input_target == "chef" else "à l'agent"
            prompt = f" › Message {who} : "
            self.put(h - 2, 0, prompt, self.c("cyan", True))
            self.put(h - 2, width(prompt), self.buffer + "█", self.c("white", True))
            self.put(h - 1, 1, "Entrée envoyer · Échap annuler", self.c("dim"))
            return
        if time.time() < self.flash_until:
            self.put(h - 2, 1, self.flash_msg, self.c(self.flash_color, True))
        x = 1
        for key, label in HELP_NORMAL:
            if x + width(key) + width(label) + 3 >= w:
                break
            self.put(h - 1, x, key, self.c("cyan", True))
            self.put(h - 1, x + width(key) + 1, label, self.c("dim"))
            x += width(key) + width(label) + 3

    # -- actions
    def on_key(self, key) -> bool:
        snap, _ = self.data.get()
        if self.mode == "saisie":
            return self._on_input_key(key, snap)
        if key == "q":
            return False
        if key == "\t":
            self.focus = "plans" if self.focus == "agents" else "agents"
        elif key in (curses.KEY_UP, "k"):
            self.sel[self.focus] = max(0, self.sel[self.focus] - 1)
        elif key in (curses.KEY_DOWN, "j"):
            self.sel[self.focus] += 1
        elif key in ("\n", "\r", curses.KEY_ENTER):
            if self.focus == "agents":
                a = self.selected_agent(snap)
                if a and ag.select_window(a["session"], a["window"]):
                    self.flash("Ctrl+B puis 1 pour revenir au cockpit.")
                else:
                    self.flash("Impossible d'ouvrir la fenêtre de cet agent.", "red")
        elif key == "o":
            self._decide(snap, True)
        elif key == "x":
            self._decide(snap, False)
        elif key == "p":
            self.preview = not self.preview
        elif key == "m":
            self.mode, self.input_target, self.buffer = "saisie", "chef", ""
        elif key == "e":
            if self.selected_agent(snap):
                self.mode, self.input_target, self.buffer = "saisie", "agent", ""
            else:
                self.flash("Aucun agent sélectionné.", "yellow")
        elif key == "c":
            if not ag.select_window(config.SESSION, config.CHEF_WINDOW):
                self.flash("Le chef n'est pas lancé : jarvis chef", "yellow")
        elif key == "P":
            now = not store.paused()
            store.set_paused(now)
            store.feed_add("systeme", "pause activée depuis le cockpit" if now else "pause levée depuis le cockpit")
            ag.chef_inject("[JARVIS] Ton humain a mis Jarvis en PAUSE : ne lance plus rien." if now
                           else "[JARVIS] Pause levée : tu peux reprendre ta boucle.")
            self.flash("⏸ Pause activée" if now else "▶ Pause levée", "red" if now else "green")
        # sélection courante → cible de l'aperçu
        a = self.selected_agent(snap)
        self.data.preview_target = ag.target(a) if (self.preview and a) else None
        return True

    def _decide(self, snap, ok: bool):
        p = self.selected_plan(snap)
        if not p:
            self.flash("Aucun plan à valider.", "yellow")
            return
        if self.focus != "plans":
            # Jamais de décision à l'aveugle : on montre d'abord le plan concerné.
            self.focus = "plans"
            self.flash(f"Plan {p['id']} sélectionné : appuie encore sur {'o' if ok else 'x'} pour confirmer.", "yellow")
            return
        try:
            plans.decide(p["id"], ok, par="cockpit")
            self.flash(f"{p['id']} {'approuvé' if ok else 'refusé'} — le chef est prévenu.", "green" if ok else "red")
        except plans.PlanError as exc:
            self.flash(str(exc), "red")

    def _on_input_key(self, key, snap) -> bool:
        if key == "\x1b":
            self.mode = "normal"
        elif key in ("\n", "\r", curses.KEY_ENTER):
            text = self.buffer.strip()
            self.mode = "normal"
            if not text:
                return True
            if self.input_target == "chef":
                store.feed_add("toi", f"(cockpit) {text}")
                if ag.chef_inject(f"[Message de ton humain via le cockpit] {text}"):
                    self.flash("Transmis au chef.", "green")
                else:
                    self.flash("Le chef n'est pas lancé : jarvis chef", "yellow")
            else:
                a = self.selected_agent(snap)
                if a:
                    ok, err = ag.send(ag.target(a), text)
                    store.feed_add("toi", f"→ {a['worktree']} : {text}")
                    self.flash("Envoyé à l'agent." if ok else f"Échec : {err}", "green" if ok else "red")
        elif key in (curses.KEY_BACKSPACE, "\x7f", "\b"):
            self.buffer = self.buffer[:-1]
        elif isinstance(key, str) and key.isprintable():
            self.buffer += key
        return True

    def run(self):
        while True:
            self.draw()
            try:
                key = self.scr.get_wch()
            except curses.error:
                continue  # délai écoulé : on redessine
            if key == curses.KEY_RESIZE:
                continue
            if not self.on_key(key):
                break
        self.data.stop.set()


def main() -> int:
    try:
        locale.setlocale(locale.LC_ALL, "")
    except locale.Error:
        pass  # locale absente : l'affichage reste possible, avec moins de symboles
    os.environ.setdefault("ESCDELAY", "50")
    curses.wrapper(lambda scr: Cockpit(scr).run())
    return 0
