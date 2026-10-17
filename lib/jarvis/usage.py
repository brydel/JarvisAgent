"""Consommation des abonnements Claude (Max) et Codex (ChatGPT) : fenêtres 5 h et semaine.

Sources, sans aucune estimation :
- Claude Code transmet `rate_limits.five_hour` / `seven_day` (used_percentage, resets_at) à sa barre
  d'état ; bin/jarvis-statusline enregistre ce JSON dans STATE_DIR/claude_usage.json.
  (code.claude.com/docs/en/statusline)
- Codex écrit dans ~/.codex/sessions/AAAA/MM/JJ/rollout-*.jsonl des événements
  {"type":"event_msg","payload":{"type":"token_count","rate_limits":{"primary":{...},"secondary":{...}}}}
  avec used_percent, window_minutes, resets_at (codex-rs/protocol, RateLimitSnapshot).
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from . import config, store

CLAUDE_FILE = "claude_usage.json"
PROVIDERS = ("claude", "codex")
LEVELS = ("ok", "alerte", "epuise", "inconnu")


def _window(used, resets_at, now: float) -> dict | None:
    if used is None:
        return None
    resets_at = int(resets_at) if resets_at else None
    if resets_at and resets_at <= now:
        return {"used": 0.0, "resets_at": None, "remis_a_zero": True}  # fenêtre écoulée : repartie à zéro
    return {"used": float(used), "resets_at": resets_at}


# --- Claude -------------------------------------------------------------------------

def save_claude_snapshot(payload: dict) -> None:
    """Appelé par bin/jarvis-statusline avec le JSON reçu de Claude Code."""
    rl = payload.get("rate_limits") or {}
    if not rl:
        return
    data = {"ts": time.time()}
    for key in ("five_hour", "seven_day"):
        w = rl.get(key) or {}
        if w.get("used_percentage") is not None:
            data[key] = {"used_percentage": w["used_percentage"], "resets_at": w.get("resets_at")}
    store.write_json(CLAUDE_FILE, data)


def claude_usage(now: float | None = None) -> dict:
    now = now or time.time()
    snap = store.read_json(CLAUDE_FILE, {})
    if not snap:
        return {"source": "aucune donnée (lance une session Claude Code)", "maj": None}
    out = {"source": "barre d'état Claude Code", "maj": snap.get("ts")}
    fh, sd = snap.get("five_hour") or {}, snap.get("seven_day") or {}
    out["5h"] = _window(fh.get("used_percentage"), fh.get("resets_at"), now)
    out["semaine"] = _window(sd.get("used_percentage"), sd.get("resets_at"), now)
    return out


# --- Codex ----------------------------------------------------------------------------

def codex_sessions_dir() -> Path:
    return Path(os.environ.get("CODEX_HOME") or config.HOME / ".codex") / "sessions"


def _recent_rollouts(limit: int = 12) -> list[Path]:
    root = codex_sessions_dir()
    if not root.exists():
        return []
    files: list[tuple[float, Path]] = []
    # Les sessions sont rangées par date : on ne parcourt que les jours les plus récents.
    day_dirs = sorted((p for p in root.glob("*/*/*") if p.is_dir()), reverse=True)[:4]
    for d in day_dirs:
        for f in d.glob("rollout-*.jsonl"):
            try:
                files.append((f.stat().st_mtime, f))
            except OSError:
                continue
    return [f for _, f in sorted(files, reverse=True)[:limit]]


def _last_rate_limits(path: Path) -> tuple[dict, float] | None:
    try:
        with path.open("rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            fh.seek(max(0, size - 400_000))
            lines = fh.read().decode("utf-8", errors="replace").splitlines()
    except OSError:
        return None
    for line in reversed(lines):
        if '"token_count"' not in line or '"rate_limits"' not in line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        payload = item.get("payload") or {}
        rl = payload.get("rate_limits")
        if payload.get("type") == "token_count" and rl:
            return rl, path.stat().st_mtime
    return None


def codex_usage(now: float | None = None) -> dict:
    now = now or time.time()
    best = None
    for f in _recent_rollouts():
        found = _last_rate_limits(f)
        if found:
            best = found
            break  # fichiers triés du plus récent au plus ancien
    if not best:
        return {"source": "aucune donnée (lance une session Codex)", "maj": None}
    rl, ts = best
    out = {"source": "sessions Codex", "maj": ts}
    for slot in ("primary", "secondary"):
        w = rl.get(slot) or {}
        if w.get("used_percent") is None:
            continue
        minutes = w.get("window_minutes") or 0
        name = "5h" if 0 < minutes <= 24 * 60 else "semaine"
        out[name] = _window(w.get("used_percent"), w.get("resets_at"), now)
    if rl.get("rate_limit_reached_type"):
        out["limite_atteinte"] = rl["rate_limit_reached_type"]
    return out


# --- Synthèse -------------------------------------------------------------------------

def thresholds() -> tuple[float, float]:
    s = config.settings()["jetons"]
    return float(s.get("alerte", 80)), float(s.get("arret", 95))


PEREMPTION_H = 6  # au-delà, une mesure de quota ne prouve plus rien : prudence (jamais « illimité »)


def perime(u: dict, now: float | None = None) -> bool:
    """Vrai si la dernière mesure du fournisseur est trop vieille pour être crue."""
    maj = u.get("maj")
    if not maj:
        return False  # pas de mesure du tout : c'est « inconnu », traité ailleurs
    heures = float(config.settings()["jetons"].get("peremption_h", PEREMPTION_H))
    return (now or time.time()) - float(maj) > heures * 3600


def level(u: dict, now: float | None = None) -> str:
    alert, stop = thresholds()
    used = [w["used"] for k, w in u.items() if k in ("5h", "semaine") and w]
    if not used:
        return "inconnu"
    if u.get("limite_atteinte") or max(used) >= stop:
        return "epuise"
    if max(used) >= alert:
        return "alerte"
    # Mesure périmée : on ne la prend pas pour un feu vert. Le routeur réserve alors les modèles chers.
    if perime(u, now):
        return "alerte"
    return "ok"


def headroom(u: dict) -> float | None:
    used = [w["used"] for k, w in u.items() if k in ("5h", "semaine") and w]
    return None if not used else max(0.0, 100.0 - max(used))


def next_reset(u: dict) -> int | None:
    """Heure à laquelle l'agent redevient utilisable (fenêtre la plus contraignante)."""
    alert, stop = thresholds()
    blocking = [w["resets_at"] for k, w in u.items()
                if k in ("5h", "semaine") and w and w["used"] >= stop and w.get("resets_at")]
    return max(blocking) if blocking else None


def summary(now: float | None = None) -> dict:
    out = {}
    hist = store.read_json(HIST_FILE, {})
    for name, fn in (("claude", claude_usage), ("codex", codex_usage)):
        u = fn(now)
        u["perime"] = perime(u, now)
        u["age_s"] = int((now or time.time()) - float(u["maj"])) if u.get("maj") else None
        u["niveau"] = level(u, now)
        u["marge"] = headroom(u)
        u["reprise"] = next_reset(u)
        u["prevision"] = prevision(u, hist.get(name) or [], now)
        out[name] = u
    return out


# --- Historique et prévision ------------------------------------------------------------

HIST_FILE = "usage_hist.json"
HIST_PERIODE = 5 * 60       # un point toutes les 5 minutes au plus
HIST_MAX = 72               # 6 heures d'historique
PREVISION_FENETRE = 45 * 60  # rythme mesuré sur les 45 dernières minutes


def enregistrer_historique(s: dict | None = None, now: float | None = None) -> None:
    """Appelé par le démon : mémorise la consommation de la fenêtre 5 h pour en déduire le rythme."""
    now = now or time.time()
    s = s or summary(now)

    def _add(hist):
        for name in PROVIDERS:
            w = (s.get(name) or {}).get("5h")
            if not w:
                continue
            points = hist.setdefault(name, [])
            if points and now - points[-1][0] < HIST_PERIODE:
                continue
            points.append([now, w["used"], w.get("resets_at") or 0])
            del points[:-HIST_MAX]

    store.update_json(HIST_FILE, {}, _add)


def prevision(u: dict, points: list, now: float | None = None) -> dict | None:
    """Rythme de consommation de la fenêtre 5 h et délai avant le seuil d'arrêt.

    Renvoie {"rythme": % par heure, "minutes": avant l'arrêt, "avant_reset": bool} ou None si le
    rythme n'est pas mesurable (pas assez de points, fenêtre remise à zéro entre-temps).
    """
    now = now or time.time()
    w = u.get("5h")
    if not w or not points:
        return None
    reset = w.get("resets_at") or 0
    # Seulement les points de la fenêtre en cours : après une remise à zéro, le rythme repart de rien.
    recents = [p for p in points if now - p[0] <= PREVISION_FENETRE and (p[2] or 0) == reset and p[1] <= w["used"]]
    if not recents or now - recents[0][0] < 10 * 60:
        return None
    rythme = (w["used"] - recents[0][1]) / ((now - recents[0][0]) / 3600)
    if rythme <= 0.5:
        return {"rythme": max(0.0, rythme), "minutes": None, "avant_reset": False}
    _alert, stop = thresholds()
    minutes = max(0.0, (stop - w["used"]) / rythme * 60)
    avant = bool(reset) and now + minutes * 60 < reset
    return {"rythme": rythme, "minutes": minutes, "avant_reset": avant}


# --- Jetons consommés par une tâche -------------------------------------------------------

def _claude_projects_dir() -> Path:
    return Path(os.environ.get("CLAUDE_CONFIG_DIR") or config.HOME / ".claude") / "projects"


_cache_fichiers: dict[tuple, tuple] = {}


def _horodatage(texte) -> float | None:
    if not texte:
        return None
    from datetime import datetime
    try:
        return datetime.fromisoformat(str(texte).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _jetons_fichier_claude(f: Path, depuis: float) -> tuple[dict, dict]:
    """{clé de message: usage} d'un journal Claude, messages postérieurs à `depuis`. Mis en cache par
    (chemin, taille, date) : le démon et l'admission relisent souvent les mêmes fichiers."""
    st = f.stat()
    cle = (str(f), st.st_size, st.st_mtime, int(depuis))
    if cle in _cache_fichiers:
        return _cache_fichiers[cle]
    messages: dict[str, dict] = {}
    with f.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if '"usage"' not in line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            msg = item.get("message") or {}
            us = msg.get("usage")
            if not isinstance(us, dict):
                continue
            ts = _horodatage(item.get("timestamp"))
            if depuis and ts is not None and ts < depuis - 60:
                continue  # message d'un essai précédent dans le même worktree
            # Un même message est écrit plusieurs fois pendant sa diffusion : compté une fois.
            messages[f"{msg.get('id')}:{item.get('requestId')}" if msg.get("id") else f"{f.name}:{len(messages)}"] = us
    res = (messages, {})
    if len(_cache_fichiers) > 512:
        _cache_fichiers.clear()
    _cache_fichiers[cle] = res
    return res


def claude_task_tokens(workdir: str, depuis: float = 0) -> dict | None:
    """Jetons des sessions Claude Code ouvertes dans `workdir` (journaux ~/.claude/projects), depuis `depuis`.

    Une relance réutilise le même worktree, donc le même dossier de journaux : sans ce filtre, le 2e essai
    compterait aussi les jetons du 1er.
    """
    import re
    root = _claude_projects_dir()
    slug = re.sub(r"[^A-Za-z0-9]", "-", str(Path(workdir)))
    d = root / slug
    if not d.is_dir():
        return None
    messages: dict[str, dict] = {}
    for f in d.glob("*.jsonl"):
        try:
            if depuis and f.stat().st_mtime < depuis - 60:
                continue
            messages.update(_jetons_fichier_claude(f, depuis)[0])
        except OSError:
            continue
    if not messages:
        return None
    tot = {"entree": 0, "sortie": 0, "cache_lecture": 0, "cache_ecriture": 0}
    for us in messages.values():
        tot["entree"] += int(us.get("input_tokens") or 0)
        tot["sortie"] += int(us.get("output_tokens") or 0)
        tot["cache_lecture"] += int(us.get("cache_read_input_tokens") or 0)
        tot["cache_ecriture"] += int(us.get("cache_creation_input_tokens") or 0)
    # « total » = entrée non servie par le cache + sortie, pour les deux fournisseurs : chez Claude l'entrée
    # nouvelle se répartit entre input_tokens et l'écriture du cache ; chez Codex elle vaut input − cached.
    tot["total"] = tot["entree"] + tot["sortie"] + tot["cache_ecriture"]
    return tot


def codex_task_tokens(workdir: str, depuis: float = 0) -> dict | None:
    """Jetons des sessions Codex ouvertes dans `workdir` (dernier total de chaque fichier de session)."""
    root = codex_sessions_dir()
    if not root.exists():
        return None
    workdir = str(Path(workdir))
    tot = {"entree": 0, "sortie": 0, "cache_lecture": 0, "cache_ecriture": 0}
    trouve = False
    day_dirs = sorted((p for p in root.glob("*/*/*") if p.is_dir()), reverse=True)[:8]
    for d in day_dirs:
        for f in d.glob("rollout-*.jsonl"):
            try:
                if depuis and f.stat().st_mtime < depuis - 60:
                    continue
                with f.open(encoding="utf-8", errors="replace") as fh:
                    first = fh.readline()
                meta = (json.loads(first).get("payload") or {}) if first.strip() else {}
            except (OSError, json.JSONDecodeError):
                continue
            if str(Path(meta.get("cwd") or "/nulle-part")) != workdir:
                continue
            info = _last_token_info(f)
            if not info:
                continue
            trouve = True
            t = info.get("total_token_usage") or {}
            cache = int(t.get("cached_input_tokens") or 0)
            tot["entree"] += max(0, int(t.get("input_tokens") or 0) - cache)
            tot["sortie"] += int(t.get("output_tokens") or 0)
            tot["cache_lecture"] += cache
    if not trouve:
        return None
    tot["total"] = tot["entree"] + tot["sortie"]
    return tot


def _last_token_info(path: Path) -> dict | None:
    try:
        with path.open("rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            fh.seek(max(0, size - 400_000))
            lines = fh.read().decode("utf-8", errors="replace").splitlines()
    except OSError:
        return None
    for line in reversed(lines):
        if '"token_count"' not in line or '"total_token_usage"' not in line:
            continue
        try:
            payload = json.loads(line).get("payload") or {}
        except json.JSONDecodeError:
            continue
        if payload.get("type") == "token_count" and isinstance(payload.get("info"), dict):
            return payload["info"]
    return None


def task_tokens(fiche: dict) -> dict | None:
    """Consommation d'une tâche du registre (fiche de taches.py), selon son fournisseur."""
    if not fiche.get("chemin"):
        return None
    if fiche.get("agent") == "claude":
        return claude_task_tokens(fiche["chemin"], fiche.get("cree") or 0)
    if fiche.get("agent") == "codex":
        return codex_task_tokens(fiche["chemin"], fiche.get("cree") or 0)
    return None


def compteur_tache(tache_id: str, mesurer: bool = True) -> dict | None:
    """Consommation de l'unité de travail d'une tâche (même projet, issue et rôle, relances comprises)
    face à son plafond : {"tache", "jetons", "plafond", "reste", "depasse"}. None si la tâche est inconnue."""
    from . import couts, taches
    fiche = taches.get(tache_id)
    if not fiche:
        return None
    jetons = couts.compteur_unite(fiche["projet"], fiche["issue"], fiche.get("role", ""), mesurer=mesurer)
    plafond = int(fiche.get("jetons_max") or 0) or couts.plafond_defaut(fiche.get("role", ""), fiche.get("taille", "M"))[0]
    return {"tache": fiche["id"], "jetons": jetons, "plafond": plafond, "reste": max(0, plafond - jetons),
            "depasse": jetons >= plafond}


def fmt_reset(ts: int | None) -> str:
    if not ts:
        return ""
    t = time.localtime(ts)
    when = time.strftime("%H:%M", t)
    if ts - time.time() > 20 * 3600:
        jours = ("lun", "mar", "mer", "jeu", "ven", "sam", "dim")
        when = f"{jours[t.tm_wday]} {t.tm_mday} {when}"
    return when


def fmt_duree(minutes: float) -> str:
    minutes = int(minutes)
    return f"{minutes} min" if minutes < 60 else f"{minutes // 60} h {minutes % 60:02d}"


def bar(pct: float | None, width: int = 10) -> str:
    if pct is None:
        return "·" * width
    filled = round(max(0.0, min(100.0, pct)) / 100 * width)
    return "█" * filled + "░" * (width - filled)


def text(s: dict | None = None) -> str:
    s = s or summary()
    icon = {"ok": "🟢", "alerte": "🟠", "epuise": "🔴", "inconnu": "⚪"}
    lines = []
    for name in PROVIDERS:
        u = s[name]
        head = f"{icon[u['niveau']]} {name.capitalize():<7}"
        parts = []
        for key, label in (("5h", "5 h"), ("semaine", "semaine")):
            w = u.get(key)
            if w:
                reset = f" (remise à zéro {fmt_reset(w.get('resets_at'))})" if w.get("resets_at") else ""
                parts.append(f"{label} {bar(w['used'])} {w['used']:.0f} %{reset}")
        if not parts:
            parts.append(u["source"])
        lines.append(head + "  " + "  ·  ".join(parts))
        if u.get("maj"):
            age = int((time.time() - u["maj"]) // 60)
            if age >= 30:
                lines.append(f"          (données d'il y a {age} min : lance une session pour les rafraîchir)")
        if u["niveau"] == "epuise" and u.get("reprise"):
            lines.append(f"          → épuisé jusqu'à {fmt_reset(u['reprise'])}")
        prev = u.get("prevision") or {}
        if u["niveau"] != "epuise" and prev.get("minutes") is not None:
            quand = "avant la remise à zéro" if prev["avant_reset"] else "après la remise à zéro : ça passe"
            lines.append(f"          rythme {prev['rythme']:.0f} %/h → seuil d'arrêt dans {fmt_duree(prev['minutes'])} ({quand})")
    alert, stop = thresholds()
    lines.append(f"Seuils : alerte {alert:.0f} %, arrêt {stop:.0f} %")
    return "\n".join(lines)
