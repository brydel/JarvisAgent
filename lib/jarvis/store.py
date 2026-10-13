"""Stockage local : fil d'activité (JSONL) et fichiers JSON protégés par verrou."""

from __future__ import annotations

import contextlib
import fcntl
import json
import os
import time
from pathlib import Path
from typing import Callable, Iterator

from . import config

FEED_FILE = "feed.jsonl"
FEED_MAX_BYTES = 2_000_000

# Icône par type d'événement, reprise par le cockpit et Telegram.
ICONS = {
    "agent_done": "✅",
    "agent_waiting": "💬",
    "agent_working": "🤖",
    "agent_gone": "◌",
    "plan_new": "📋",
    "plan_ok": "👍",
    "plan_no": "✋",
    "task": "🚀",
    "chef": "🧠",
    "question": "❓",
    "toi": "🗣",
    "note": "📝",
    "systeme": "⚙",
    "erreur": "⚠",
    "livrable": "🎬",
    "agent_bloque": "🧱",
    "modele": "🧬",
}


def state_path(name: str) -> Path:
    config.STATE_DIR.mkdir(parents=True, exist_ok=True)
    return config.STATE_DIR / name


@contextlib.contextmanager
def locked(name: str) -> Iterator[None]:
    """Verrou exclusif inter-processus (cockpit, démon et chef écrivent en même temps)."""
    lock = state_path(name + ".lock")
    with lock.open("a") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def read_json(name: str, default):
    try:
        return json.loads(state_path(name).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def write_json(name: str, data) -> None:
    path = state_path(name)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def update_json(name: str, default, fn: Callable):
    """Lit, transforme et réécrit un fichier JSON sous verrou. Renvoie ce que `fn` renvoie."""
    with locked(name):
        data = read_json(name, default)
        result = fn(data)
        write_json(name, data)
        return result


# --- Fil d'activité ------------------------------------------------------------

def feed_add(kind: str, text: str, **extra) -> dict:
    event = {"ts": time.time(), "type": kind, "icone": ICONS.get(kind, "•"), "texte": text}
    event.update({k: v for k, v in extra.items() if v is not None})
    path = state_path(FEED_FILE)
    with locked(FEED_FILE):
        if path.exists() and path.stat().st_size > FEED_MAX_BYTES:
            # Garde la seconde moitié du fil : on ne veut pas d'un fichier qui grossit sans fin.
            lines = path.read_text(encoding="utf-8").splitlines()
            path.write_text("\n".join(lines[len(lines) // 2:]) + "\n", encoding="utf-8")
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, ensure_ascii=False) + "\n")
    return event


def feed_tail(n: int = 100) -> list[dict]:
    path = state_path(FEED_FILE)
    try:
        with path.open("rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            fh.seek(max(0, size - 200 * (n + 10)))
            chunk = fh.read().decode("utf-8", errors="replace")
    except FileNotFoundError:
        return []
    events = []
    for line in chunk.splitlines()[-n:]:
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events


# --- Pause globale -------------------------------------------------------------

def paused() -> bool:
    return state_path("pause").exists()


def set_paused(value: bool) -> None:
    p = state_path("pause")
    if value:
        p.write_text(time.strftime("%Y-%m-%d %H:%M"), encoding="utf-8")
    else:
        p.unlink(missing_ok=True)
