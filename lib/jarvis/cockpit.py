"""Cockpit plein écran de Jarvis (curses, bibliothèque standard) : l'usine vue par ateliers.

  ◆ JARVIS · usine                              ● démon  ● chef  ● Telegram     12:03:11
  Agents 3/4 · ? 1 attend · ✓ 2 terminés · ◇ 1 à valider · ▣ 2 livrables
  ● Claude 5h ████░░░░ 62% sem ███░░░░░ 41% ↗12%/h    ● Codex 5h ██░░░░░░ 22%    ▪ 6.1 Go libres
 ╭─ ATELIERS ────────────────────────────────────────────╮╭─ À VALIDER ───────────────╮
 │ CONCEPTION · libres : DSG                              ││ ◇ P-0007 Vague auth [vague]│
 │  ARC  Architecte   ▶ repriceo BIS-90 adr   Claude·fable ││   BIS-82 → Codex · sol  FRT│
 │ FABRICATION · libres : DAT DEV                         │╰────────────────────────────╯
 │  FRT  Front-end    ▶ jobpilot JP-12 onbo…  Codex·sol   │╭─ LIVRABLES ────────────────╮
 │  BCK  Back-end     ? repriceo BIS-71 gard… Codex·sol   ││ 🎬 L-0003 Vidéo de lancement│
 ╰────────────────────────────────────────────────────────╯╰────────────────────────────╯
 ╭─ FIL D'ACTIVITÉ ──────────────────────────────────────────────────────────────────────╮
"""

from __future__ import annotations

import curses
import locale
import os
import threading
import time
import unicodedata

from . import agents as ag
from . import config, plans, report, roles, store

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
    "livrable": ("▣", "green"), "agent_bloque": ("■", "red"), "modele": ("◈", "blue"),
}
GENRES = {"video": "▶", "image": "▣", "document": "≡"}

HELP_NORMAL = [
    ("Tab", "panneau"), ("↑↓", "choisir"), ("Entrée", "ouvrir"), ("o", "approuver"), ("x", "refuser"),
    ("m", "chef"), ("e", "agent"), ("p", "aperçu"), ("d", "fiche"), ("b", "bilan"), ("v", "vue"),
    ("c", "voir le chef"), ("P", "pause"), ("q", "quitter"),
]


# --- Largeur d'affichage (émojis et lettres larges comptent double) -----------

def _w(ch: str) -> int:
    if unicodedata.combining(ch) or ch in "️‍":
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


# --- Mise en ateliers ---------------------------------------------------------------

def ateliers(agents: list[dict]) -> list[tuple]:
    """Lignes de la vue par ateliers : ("equipe", nom, [sigles libres]) puis ("agent", agent, rôle).

    Une équipe sans agent tient sur sa ligne d'en-tête : l'écran montre qui travaille, pas une
    liste de postes vides.
    """
    par_role: dict[str, list[dict]] = {}
    for a in agents:
        par_role.setdefault(a.get("role") or "", []).append(a)
    ordre = {"waiting": 0, "untracked": 1, "working": 2, "done": 3}
    rows: list[tuple] = []
    for equipe, membres in roles.par_equipe():
        libres = [r["sigle"] for r in membres if not par_role.get(r["nom"])]
        rows.append(("equipe", equipe, libres))
        for r in membres:
            for a in sorted(par_role.get(r["nom"], []), key=lambda x: (ordre.get(x["status"], 4), x["project"])):
                rows.append(("agent", a, r))
    connus = set(roles.tous())
    hors = [a for nom, lst in par_role.items() if nom not in connus for a in lst]
    if hors:
        rows.append(("equipe", "Hors registre", []))
        rows += [("agent", a, None) for a in hors]
    return rows


def affectation(a: dict) -> str:
    """« Codex · sol · high » : fournisseur, modèle et effort d'un agent."""
    parts = [ag.kind_label(a.get("kind") or (a.get("tache") or {}).get("agent", ""))]
    modele = a.get("modele") or ""
    if modele and not modele.endswith("-defaut"):
        parts.append(modele)
    if a.get("effort"):
        parts.append(a["effort"])
    return " · ".join(parts)


# --- Données en arrière-plan ------------------------------------------------------

class Data:
    """Lit l'état dans un fil séparé pour que l'interface ne gèle jamais."""

    def __init__(self):
        self.lock = threading.Lock()
        self.snap: dict | None = None
        self.preview_target: str | None = None
        self.preview_text = ""
        self.memoire_go: float | None = None
        self.stop = threading.Event()
        threading.Thread(target=self._loop, daemon=True).start()
        threading.Thread(target=self._preview_loop, daemon=True).start()

    def _loop(self):
        while not self.stop.is_set():
            try:
                snap = report.snapshot()
            except Exception as exc:  # noqa: BLE001
                snap = {"agents": None, "agents_error": str(exc), "busy": 0, "max_agents": 0, "max_base": 0,
                        "capacite_raisons": [], "pending": [], "active": [], "propositions": [], "livrables": [],
                        "projects": {}, "paused": False, "chef": False, "demon": False, "usage": None,
                        "ts": time.time()}
            try:
                from . import poste
                mem = poste._meminfo().get("MemAvailable")
                memoire = mem / 1048576 if mem else None
            except Exception:  # noqa: BLE001
                memoire = None
            with self.lock:
                self.snap = snap
                self.memoire_go = memoire
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
        # La sélection suit l'identité (cet agent, ce plan), pas la position : la liste se réordonne
        # toute seule, et un message ou une approbation ne doit jamais glisser sur le voisin.
        self.cle: dict[str, str | None] = {"agents": None, "plans": None}
        self.input_cible: str | None = None   # agent visé par le message en cours de saisie
        self.a_confirmer: str | None = None   # plan ou proposition montré avant confirmation
        self.mode = "normal"          # normal | saisie
        self.input_target = "chef"    # chef | agent
        self.buffer = ""
        self.vue = "ateliers"         # ateliers | liste
        self.bas = "fil"              # fil | apercu | fiche | bilan
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
        return self.colors.get(name, self.colors.get("white", 0)) | (curses.A_BOLD if bold else 0)

    def put(self, y: int, x: int, text: str, attr: int = 0, maxw: int | None = None):
        h, w = self.scr.getmaxyx()
        if y < 0 or y >= h or x >= w or x < 0:
            return
        room = w - x - (1 if y == h - 1 else 0)  # la dernière case de l'écran ne s'écrit pas
        if maxw is not None:
            room = min(room, maxw)
        # Un retour à la ligne dans un texte (ex. un bilan) déborderait sur les panneaux voisins.
        text = " ".join(str(text).replace("\t", " ").replace("\x00", "").splitlines())
        try:
            self.scr.addstr(y, x, cut(text, room), attr)
        except (curses.error, ValueError):
            pass  # caractère que le terminal ne sait pas afficher : la ligne est sautée, pas le cockpit

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
        self.put(y, x + 2, f" {title} ", self.c("cyan" if focused else "white", True), w - 4)
        if right and width(right) + width(title) + 10 < w:
            self.put(y, x + w - width(right) - 4, f" {right} ", self.c("dim"))

    # -- sélection
    def rows(self, snap) -> list[tuple]:
        agents = (snap or {}).get("agents") or []
        if self.vue == "ateliers":
            return ateliers(agents)
        return [("agent", a, roles.get(a.get("role"))) for a in agents]

    def agents_list(self, snap) -> list[dict]:
        """Agents dans l'ordre où ils sont affichés (c'est l'ordre de la sélection)."""
        return [r[1] for r in self.rows(snap) if r[0] == "agent"]

    def decisions(self, snap) -> list[tuple[str, dict]]:
        """Ce qui attend l'humain : plans du chef, puis propositions sur le catalogue des modèles."""
        snap = snap or {}
        return [("plan", p) for p in snap.get("pending") or []] + \
               [("modele", i) for i in snap.get("propositions") or []]

    def _cles(self, focus: str, snap) -> list[str]:
        if focus == "agents":
            return [ag.target(a) for a in self.agents_list(snap)]
        return [d["id"] for _, d in self.decisions(snap)]

    def _resync(self, snap) -> None:
        """Replace chaque sélection sur l'élément choisi s'il a changé de place ; sinon sur son voisin."""
        for focus in ("agents", "plans"):
            cles = self._cles(focus, snap)
            if not cles:
                self.sel[focus], self.cle[focus] = 0, None
                continue
            if self.cle[focus] in cles:
                self.sel[focus] = cles.index(self.cle[focus])
            else:
                self.sel[focus] = max(0, min(self.sel[focus], len(cles) - 1))
                self.cle[focus] = cles[self.sel[focus]]

    def _deplacer(self, snap, pas: int) -> None:
        cles = self._cles(self.focus, snap)
        if cles:
            self.sel[self.focus] = max(0, min(self.sel[self.focus] + pas, len(cles) - 1))
            self.cle[self.focus] = cles[self.sel[self.focus]]

    def selected_agent(self, snap) -> dict | None:
        lst = self.agents_list(snap)
        self._resync(snap)
        return lst[self.sel["agents"]] if lst else None

    def selected_decision(self, snap) -> tuple[str, dict] | None:
        lst = self.decisions(snap)
        self._resync(snap)
        return lst[self.sel["plans"]] if lst else None

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
        top_h = max(9, int(body_h * 0.6))
        left_w = int(w * 0.64) if w >= 110 else int(w * 0.6)
        right_w = w - left_w

        self._draw_agents(snap, body_top, 0, top_h, left_w)
        self._draw_right(snap, body_top, left_w, top_h, right_w)
        bottom_h = body_h - top_h
        y = body_top + top_h
        if self.bas == "apercu":
            self._draw_preview(snap, preview_text, y, 0, bottom_h, w)
        elif self.bas == "fiche":
            self._draw_fiche(snap, y, 0, bottom_h, w)
        elif self.bas == "bilan":
            self._draw_bilan(y, 0, bottom_h, w)
        else:
            self._draw_feed(y, 0, bottom_h, w)
        self._draw_footer(h, w)
        self.scr.refresh()

    def _draw_header(self, snap, w):
        now = time.strftime("%H:%M:%S")
        self.put(0, 0, " " * (w - 1), self.c("header"))
        self.put(0, 0, " ◆ J A R V I S  ·  usine ", self.c("header") | curses.A_BOLD)
        self.put(0, w - len(now) - 2, now, self.c("header") | curses.A_BOLD)
        if not snap:
            self.put(1, 1, "chargement…", self.c("dim"))
            return
        # Voyants de service, à droite de la barre de titre.
        tg = config.settings()["telegram"].get("chat_id")
        voyants = [("démon", snap.get("demon")), ("chef", snap["chef"]), ("Telegram", bool(tg))]
        x = w - len(now) - 4
        for nom, ok in reversed(voyants):
            seg = f"{'●' if ok else '○'} {nom}"
            x -= width(seg) + 2
            if x > 28:
                self.put(0, x, seg, self.c("header") | (curses.A_BOLD if ok else curses.A_DIM))
        agents = snap.get("agents") or []
        waiting = sum(1 for a in agents if a["status"] == "waiting")
        done = sum(1 for a in agents if a["status"] == "done")
        a_valider = len(snap["pending"]) + len(snap.get("propositions") or [])
        cap = f"Agents {snap['busy']}/{snap['max_agents']}"
        if snap.get("capacite_raisons"):
            cap += f" (plafond {snap['max_base']} réduit)"
        chips = [
            (cap, "yellow" if snap.get("capacite_raisons") else "cyan"),
            (f"? {waiting} attend", "yellow" if waiting else "dim"),
            (f"✓ {done} terminé{'s' if done > 1 else ''}", "green" if done else "dim"),
            (f"◇ {a_valider} à valider", "magenta" if a_valider else "dim"),
            (f"▣ {len(snap.get('livrables') or [])} livrable{'s' if len(snap.get('livrables') or []) > 1 else ''}",
             "green" if snap.get("livrables") else "dim"),
        ]
        if snap["paused"]:
            chips.append(("⏸ PAUSE", "red"))
        if not snap.get("demon"):
            chips.append(("⚠ démon arrêté : jarvis start", "red"))
        x = 1
        for text, col in chips:
            self.put(1, x, text, self.c(col, True))
            x += width(text) + 3
        if snap.get("agents") is None:
            self.put(1, x, f"⚠ {snap.get('agents_error', '')}", self.c("red"))
        elif snap.get("capacite_raisons"):
            self.put(1, x, "· " + " ; ".join(snap["capacite_raisons"]), self.c("yellow"))

    def _draw_tokens(self, snap, y, w):
        """Jauges de jetons : Claude et Codex, fenêtres 5 h et semaine, rythme et prévision."""
        from . import usage
        s = (snap or {}).get("usage")
        if not s:
            self.put(y, 1, "Jetons : données indisponibles", self.c("dim"))
            return
        alert, stop = usage.thresholds()
        large = w >= 120
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
                seg = f"{label} {usage.bar(pct, 8 if large else 5)} {pct:3.0f}%"
                self.put(y, x, seg, self.c(col, True))
                x += width(seg) + 2
            if not shown:
                self.put(y, x, "en attente de données", self.c("dim"))
                x += 23
            prev = u.get("prevision") or {}
            if lvl == "epuise" and u.get("reprise"):
                seg = f"→ {usage.fmt_reset(u['reprise'])}"
                self.put(y, x, seg, self.c("red"))
                x += width(seg) + 1
            elif prev.get("minutes") is not None and prev.get("rythme", 0) >= 1:
                seg = f"↗{prev['rythme']:.0f}%/h"
                if prev.get("avant_reset"):
                    seg += f" ⚠ {usage.fmt_duree(prev['minutes'])}"
                self.put(y, x, seg, self.c("red" if prev.get("avant_reset") else "dim", bool(prev.get("avant_reset"))))
                x += width(seg) + 1
            x += 3
            if x >= w - 22:
                return
        mem = self.data.memoire_go
        if mem is not None and x < w - 20:
            self.put(y, x, f"▪ {mem:.1f} Go libres", self.c("yellow" if mem < 2 else "dim"))

    def _badge(self, y: int, x: int, role: dict | None, base: int = 0) -> int:
        """Pastille du rôle (sigle sur fond coloré). Renvoie la largeur écrite."""
        sigle = pad(role["sigle"] if role else "···", 3)
        col = self.c(role["couleur"] if role else "dim", True)
        self.put(y, x, f" {sigle} ", col | curses.A_REVERSE | base)
        return 5

    def _draw_agents(self, snap, y, x, h, w):
        agents = self.agents_list(snap)
        rows = self.rows(snap)
        focused = self.focus == "agents"
        actifs = sum(1 for a in agents if a["status"] in ag.BUSY)
        titre = "ATELIERS" if self.vue == "ateliers" else "AGENTS"
        self.box(y, x, h, w, titre, focused, f"{actifs} au travail · v : vue")
        inner = w - 4
        if snap and snap.get("agents") is None:
            self.put(y + 2, x + 3, "État des agents indisponible.", self.c("red"))
            return
        sel = self.selected_agent(snap)
        visible = h - 2
        if not agents and self.vue == "liste":
            self.put(y + 2, x + 3, "Aucun agent en cours.", self.c("dim"))
            self.put(y + 3, x + 3, "Le chef propose un plan → tu l'approuves → les agents démarrent.", self.c("dim"))
            return
        # Garder la ligne sélectionnée (et l'en-tête de son équipe) à l'écran.
        sel_row = next((i for i, r in enumerate(rows) if r[0] == "agent" and r[1] is sel), 0)
        start = 0
        if sel_row >= visible:
            start = sel_row - visible + 1
        # Colonnes : pastille 5, rôle, état 1, projet, tâche, modèle, durée.
        role_w = 10 if inner >= 54 else 0
        proj_w = 12 if inner >= 84 else 9
        model_w = 24 if inner >= 86 else 0
        dur_w = 6
        fixe = 5 + 1 + (role_w + 1 if role_w else 0) + 2 + proj_w + 1 + (model_w + 1 if model_w else 0) + dur_w + 1
        reste = inner - fixe
        task_w = min(26, max(10, reste))
        title_w = max(0, reste - task_w - 1)
        for i, row in enumerate(rows[start:start + visible]):
            ry = y + 1 + i
            if row[0] == "equipe":
                _, equipe, libres = row
                self.put(ry, x + 2, equipe.upper(), self.c("white", True))
                if libres:
                    cx = x + 2 + width(equipe) + 1
                    self.put(ry, cx, "· libres : " + " ".join(libres), self.c("dim"), w - (cx - x) - 2)
                continue
            _, a, role = row
            is_sel = focused and a is sel
            base = curses.A_REVERSE if is_sel else 0
            if is_sel:
                self.put(ry, x + 1, " " * (w - 2), curses.A_REVERSE)
            sym, label, col = STATUS.get(a["status"], ("·", a["status"], "white"))
            cx = x + 2
            cx += self._badge(ry, cx, role) + 1
            if role_w:
                self.put(ry, cx, pad(role["court"] if role else "à la main", role_w),
                         self.c(role["couleur"] if role else "dim", True) | base)
                cx += role_w + 1
            self.put(ry, cx, sym, self.c(col, True) | base)
            cx += 2
            self.put(ry, cx, pad(a["project"], proj_w), self.c("white", True) | base)
            cx += proj_w + 1
            self.put(ry, cx, pad(a["worktree"], task_w), self.c("white") | base)
            cx += task_w + 1
            if model_w:
                self.put(ry, cx, pad(affectation(a), model_w), self.c("blue", True) | base)
                cx += model_w + 1
            duree = label if a["status"] == "waiting" else ag.fmt_elapsed(a["elapsed"])
            self.put(ry, cx, pad(duree, dur_w), self.c(col if a["status"] == "waiting" else "dim") | base)
            cx += dur_w + 1
            if title_w > 6:
                self.put(ry, cx, pad(a["title"], title_w), self.c("dim") | base)
        if not agents and self.vue == "ateliers":
            ry = y + 1 + min(len(rows), visible - 2)
            if ry < y + h - 1:
                self.put(ry, x + 2, "Usine au repos : le chef propose un plan → tu l'approuves → les spécialistes démarrent.",
                         self.c("dim"), inner)

    def _draw_right(self, snap, y, x, h, w):
        livr = (snap or {}).get("livrables") or []
        decisions = self.decisions(snap)
        actifs = (snap or {}).get("active") or []
        besoin = 2 + sum(1 + len(d["items"]) if k == "plan" else 2 for k, d in decisions) + (len(actifs) + 2 if actifs else 0)
        bas_h = max(4, min(h // 2, (len(livr) if livr else len((snap or {}).get("projects") or {})) + 2))
        plans_h = max(5, min(h - 4, max(besoin, h - bas_h)))
        self._draw_plans(snap, y, x, plans_h, w)
        reste = h - plans_h
        if reste >= 3:
            if livr:
                self._draw_livrables(livr, y + plans_h, x, reste, w)
            else:
                self._draw_projects(snap, y + plans_h, x, reste, w)

    def _draw_plans(self, snap, y, x, h, w):
        decisions = self.decisions(snap)
        active = (snap or {}).get("active") or []
        focused = self.focus == "plans"
        self.box(y, x, h, w, "À VALIDER", focused, f"{len(decisions)}")
        ry, maxy = y + 1, y + h - 1
        sel = self.selected_decision(snap)
        if not decisions:
            self.put(ry, x + 2, "Rien à valider.", self.c("dim"), w - 4)
            ry += 1
        for kind, d in decisions:
            if ry >= maxy:
                break
            is_sel = focused and sel is not None and d is sel[1]
            attr = self.c("magenta", True) | (curses.A_REVERSE if is_sel else 0)
            if kind == "modele":
                c = d["champs"]
                self.put(ry, x + 2, pad(f"◈ {d['id']} modèle {d['nom']} ({c.get('fournisseur')})", w - 4), attr)
                ry += 1
                if ry < maxy:
                    detail = " · ".join(f"{k} {c[k]}" for k in ("id", "niveau", "atouts") if k in c) or d.get("pourquoi", "")
                    self.put(ry, x + 4, detail, self.c("white"), w - 6)
                    ry += 1
                continue
            tag = "nuit" if d["mode"] == "nuit" else "vague"
            self.put(ry, x + 2, pad(f"◇ {d['id']} {d['titre']} [{tag}]", w - 4), attr)
            ry += 1
            for it in d["items"]:
                if ry >= maxy:
                    break
                role = roles.get(it.get("role"))
                cx = x + 4
                if role:
                    cx += self._badge(ry, cx, role) + 1
                self.put(ry, cx, f"{it['issue']} → {plans.affectation(it)}", self.c("white"), w - (cx - x) - 2)
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

    def _draw_livrables(self, livr, y, x, h, w):
        self.box(y, x, h, w, "LIVRABLES", False, f"{len(livr)}")
        for i, item in enumerate(reversed(livr[-(h - 2):])):
            ry = y + 1 + i
            col = "green" if item.get("envoye") else "yellow"
            self.put(ry, x + 2, GENRES.get(item["genre"], "•"), self.c(col, True))
            quand = time.strftime("%H:%M", time.localtime(item["ts"]))
            self.put(ry, x + 4, f"{item['id']} {item['titre']}", self.c("white"), w - 14)
            self.put(ry, x + w - 8, quand, self.c("dim"))

    def _draw_projects(self, snap, y, x, h, w):
        projs = (snap or {}).get("projects") or {}
        self.box(y, x, h, w, "PROJETS", False, f"{len(projs)}")
        counts: dict[str, int] = {}
        for a in (snap or {}).get("agents") or []:
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
        self.box(y, x, h, w, "FIL D'ACTIVITÉ", False, "p : aperçu · d : fiche · b : bilan")
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
        title = f"APERÇU · {a['project']}/{a['worktree']} ({affectation(a)})" if a else "APERÇU"
        self.box(y, x, h, w, title, False, "p : revenir au fil")
        if not a:
            self.put(y + 1, x + 2, "Choisis un agent dans le panneau du haut.", self.c("dim"))
            return
        lines = [ln for ln in (text or "chargement…").splitlines()]
        while lines and not lines[-1].strip():
            lines.pop()
        for i, ln in enumerate(lines[-(h - 2):]):
            self.put(y + 1 + i, x + 2, ln.expandtabs(4), self.c("white"), w - 4)

    def _draw_fiche(self, snap, y, x, h, w):
        """Fiche de la tâche de l'agent sélectionné : rôle, modèle et pourquoi, plan, jetons."""
        a = self.selected_agent(snap)
        self.box(y, x, h, w, "FICHE DE LA TÂCHE", False, "d : revenir au fil")
        if not a:
            self.put(y + 1, x + 2, "Choisis un agent dans le panneau du haut.", self.c("dim"))
            return
        t = a.get("tache")
        role = roles.get(a.get("role"))
        lignes: list[tuple[str, str, str]] = []
        if role:
            lignes.append(("Rôle", f"{role['titre']} — équipe {role['equipe']}", role["couleur"]))
            lignes.append(("", role["resume"], "dim"))
        else:
            lignes.append(("Rôle", "agent lancé à la main, hors registre", "dim"))
        lignes.append(("Tâche", f"{a['project']} · {(t or {}).get('issue') or a['worktree']} · branche {a['worktree']}", "white"))
        lignes.append(("Modèle", affectation(a) + (f" · taille {t['taille']}" if t else ""), "blue"))
        if t:
            if t.get("raison"):
                lignes.append(("Pourquoi", t["raison"], "white"))
            if t.get("secours"):
                lignes.append(("", "lancé avec le secours : le fournisseur prévu était épuisé", "yellow"))
            origine = f"plan {t['plan']}" if t.get("plan") else "lancement manuel"
            lignes.append(("Origine", f"{origine} · {time.strftime('%d/%m %H:%M', time.localtime(t['cree']))}", "white"))
            if t.get("revue"):
                lignes.append(("Relecture", f"PR #{t['revue']} (aucun commit)", "green"))
            if t.get("jetons"):
                from . import taches
                j = t["jetons"]
                lignes.append(("Jetons", f"{taches.fmt_jetons(j.get('total', 0))} (sortie {taches.fmt_jetons(j.get('sortie', 0))}, "
                                         f"cache relu {taches.fmt_jetons(j.get('cache_lecture', 0))})", "white"))
            if t.get("verdict"):
                from . import taches
                lignes.append(("Verdict", taches.VERDICTS[t["verdict"]] + (f" — {t['verdict_note']}" if t.get("verdict_note") else ""),
                               "green" if t["verdict"] == "pret" else "yellow"))
        sym, label, col = STATUS.get(a["status"], ("·", a["status"], "white"))
        lignes.append(("État", f"{sym} {label} depuis {ag.fmt_elapsed(a['elapsed'])}" + (f" — {a['title']}" if a["title"] else ""), col))
        for i, (cle, val, col) in enumerate(lignes[:h - 2]):
            self.put(y + 1 + i, x + 2, pad(cle, 10), self.c("dim", True))
            self.put(y + 1 + i, x + 13, val, self.c(col), w - 15)

    def _draw_bilan(self, y, x, h, w):
        from . import taches
        self.box(y, x, h, w, "BILAN · 7 JOURS", False, "b : revenir au fil")
        try:
            lines = taches.texte_bilan().splitlines()
        except Exception as exc:  # noqa: BLE001
            lines = [f"bilan indisponible : {exc}"]
        for i, ln in enumerate(lines[:h - 2]):
            titre = ln.isupper() or i == 0
            self.put(y + 1 + i, x + 2, ln, self.c("white", titre) if titre else self.c("white"), w - 4)

    def _draw_footer(self, h, w):
        if self.mode == "saisie":
            who = "au chef" if self.input_target == "chef" else f"à {self.input_cible}"
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
            self._deplacer(snap, -1)
        elif key in (curses.KEY_DOWN, "j"):
            self._deplacer(snap, +1)
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
            self.bas = "fil" if self.bas == "apercu" else "apercu"
        elif key == "d":
            self.bas = "fil" if self.bas == "fiche" else "fiche"
        elif key == "b":
            self.bas = "fil" if self.bas == "bilan" else "bilan"
        elif key == "v":
            self.vue = "liste" if self.vue == "ateliers" else "ateliers"
            self._resync(snap)  # même agent sélectionné dans l'autre vue
        elif key == "m":
            self.mode, self.input_target, self.buffer = "saisie", "chef", ""
        elif key == "e":
            a = self.selected_agent(snap)
            if a:
                self.mode, self.input_target, self.buffer = "saisie", "agent", ""
                self.input_cible = ag.target(a)  # figé maintenant : la liste peut bouger pendant la saisie
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
        self.data.preview_target = ag.target(a) if (self.bas == "apercu" and a) else None
        return True

    def _decide(self, snap, ok: bool):
        choix = self.selected_decision(snap)
        if not choix:
            self.flash("Rien à valider.", "yellow")
            return
        kind, d = choix
        if self.focus != "plans":
            # Jamais de décision à l'aveugle : on montre d'abord ce qui est concerné.
            self.focus = "plans"
            self.a_confirmer = d["id"]
            self.flash(f"{d['id']} sélectionné : appuie encore sur {'o' if ok else 'x'} pour confirmer.", "yellow")
            return
        if self.a_confirmer and self.a_confirmer != d["id"]:
            # La liste a changé entre les deux appuis : on redemande, sur ce qui est affiché maintenant.
            self.a_confirmer = d["id"]
            self.flash(f"La liste a changé. {d['id']} est sélectionné : appuie encore pour confirmer.", "yellow")
            return
        self.a_confirmer = None
        try:
            if kind == "modele":
                from . import modeles
                modeles.decider(d["id"], ok, par="cockpit")
                self.flash(f"{d['id']} {'accepté : le modèle sera essayé puis utilisé' if ok else 'refusé'}.",
                           "green" if ok else "red")
            else:
                plans.decide(d["id"], ok, par="cockpit")
                self.flash(f"{d['id']} {'approuvé' if ok else 'refusé'} — le chef est prévenu.", "green" if ok else "red")
        except ValueError as exc:  # PlanError et RoutageError
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
            elif self.input_cible:
                cible = self.input_cible
                ok, err = ag.send(cible, text)
                store.feed_add("toi", f"→ {cible} : {text}")
                self.flash(f"Envoyé à {cible}." if ok else f"Échec : {err}", "green" if ok else "red")
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
