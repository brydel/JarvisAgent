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


def level(u: dict) -> str:
    alert, stop = thresholds()
    used = [w["used"] for k, w in u.items() if k in ("5h", "semaine") and w]
    if not used:
        return "inconnu"
    if u.get("limite_atteinte") or max(used) >= stop:
        return "epuise"
    if max(used) >= alert:
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
    for name, fn in (("claude", claude_usage), ("codex", codex_usage)):
        u = fn(now)
        u["niveau"] = level(u)
        u["marge"] = headroom(u)
        u["reprise"] = next_reset(u)
        out[name] = u
    return out


def fmt_reset(ts: int | None) -> str:
    if not ts:
        return ""
    t = time.localtime(ts)
    when = time.strftime("%H:%M", t)
    if ts - time.time() > 20 * 3600:
        jours = ("lun", "mar", "mer", "jeu", "ven", "sam", "dim")
        when = f"{jours[t.tm_wday]} {t.tm_mday} {when}"
    return when


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
    alert, stop = thresholds()
    lines.append(f"Seuils : alerte {alert:.0f} %, arrêt {stop:.0f} %")
    return "\n".join(lines)
