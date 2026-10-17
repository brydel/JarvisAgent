"""Stockage local : fil d'activité (JSONL) et état JSON protégé par verrou.

Deux modes, mêmes fonctions (`read_json`, `write_json`, `update_json`, `supprimer`, `existe`) :
- **json** (défaut) : un fichier par état sous ~/.local/state/jarvis/, écrit de façon atomique sous verrou fcntl ;
- **sqlite** (réglage stockage.backend, après « jarvis stockage migrer ») : une table `etat` (nom → JSON) dans
  jarvis.db, en WAL, chaque `update_json` dans une transaction BEGIN IMMEDIATE (imbriquées : même transaction).
Restent toujours des fichiers : les journaux en ajout seul (*.jsonl, dont le journal d'audit chaîné), les marqueurs
sans extension .json, et `lourdes/` (seul dossier où le bac à sable de Codex peut écrire).
"""

from __future__ import annotations

import contextlib
import fcntl
import json
import os
import sqlite3
import threading
import time
import tomllib
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
    """Chemin d'un fichier d'état. Un sous-dossier (« lourdes/operations.json ») est créé au besoin."""
    path = config.STATE_DIR / name
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


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


# --- Mode de stockage ------------------------------------------------------------

_backend_cache: tuple[float, str] | None = None
_local = threading.local()


def backend() -> str:
    """« json » ou « sqlite » : variable JARVIS_STOCKAGE, sinon [stockage] backend des réglages (relu s'il change)."""
    global _backend_cache
    env = os.environ.get("JARVIS_STOCKAGE", "")
    if env in ("json", "sqlite"):
        return env
    try:
        mtime = config.SETTINGS_FILE.stat().st_mtime
    except OSError:
        return "json"
    if _backend_cache and _backend_cache[0] == mtime:
        return _backend_cache[1]
    try:
        with open(config.SETTINGS_FILE, "rb") as fh:
            valeur = str((tomllib.load(fh).get("stockage") or {}).get("backend") or "json")
    except (OSError, tomllib.TOMLDecodeError):
        valeur = "json"
    valeur = valeur if valeur in ("json", "sqlite") else "json"
    _backend_cache = (mtime, valeur)
    return valeur


def en_base(name: str) -> bool:
    return backend() == "sqlite" and name.endswith(".json") and not name.startswith("lourdes/")


def db_path() -> Path:
    return state_path("jarvis.db")


def connexion() -> sqlite3.Connection:
    """Connexion SQLite propre au fil d'exécution (et au processus : jamais partagée après un fork)."""
    c = getattr(_local, "conn", None)
    chemin = db_path()
    if c is not None and getattr(_local, "pid", None) == os.getpid() and getattr(_local, "chemin", None) == chemin:
        try:
            meme_fichier = chemin.stat().st_ino == _local.inode
        except OSError:
            meme_fichier = False
        if meme_fichier or _local.profondeur > 0:
            return c
        c.close()  # base supprimée ou remplacée (restauration, ménage) : on ne lit pas un fichier fantôme
    c = sqlite3.connect(chemin, timeout=30, isolation_level=None)
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA busy_timeout=30000")
    c.execute("PRAGMA synchronous=NORMAL")
    c.execute("CREATE TABLE IF NOT EXISTS etat (nom TEXT PRIMARY KEY, valeur TEXT NOT NULL, maj REAL NOT NULL)")
    _local.conn, _local.pid, _local.chemin, _local.profondeur = c, os.getpid(), chemin, 0
    _local.inode = chemin.stat().st_ino
    return c


def _db_lire(name: str, default):
    row = connexion().execute("SELECT valeur FROM etat WHERE nom = ?", (name,)).fetchone()
    if not row:
        return default
    try:
        return json.loads(row[0])
    except json.JSONDecodeError:
        return default


def _db_ecrire(name: str, data) -> None:
    connexion().execute("INSERT INTO etat (nom, valeur, maj) VALUES (?, ?, ?) ON CONFLICT(nom) DO UPDATE SET "
                        "valeur = excluded.valeur, maj = excluded.maj",
                        (name, json.dumps(data, ensure_ascii=False), time.time()))


@contextlib.contextmanager
def transaction() -> Iterator[sqlite3.Connection]:
    """Transaction d'écriture (BEGIN IMMEDIATE) ; une transaction imbriquée rejoint celle qui est ouverte."""
    c = connexion()
    if _local.profondeur == 0:
        c.execute("BEGIN IMMEDIATE")
    _local.profondeur += 1
    ok = False
    try:
        yield c
        ok = True
    finally:
        _local.profondeur -= 1
        if _local.profondeur == 0:
            c.execute("COMMIT" if ok else "ROLLBACK")


# --- Lecture et écriture de l'état --------------------------------------------------

def read_json(name: str, default):
    if en_base(name):
        return _db_lire(name, default)
    try:
        return json.loads(state_path(name).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def write_json(name: str, data) -> None:
    if en_base(name):
        _db_ecrire(name, data)
        return
    path = state_path(name)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def update_json(name: str, default, fn: Callable):
    """Lit, transforme et réécrit un état sous verrou (ou dans une transaction SQLite). Renvoie ce que `fn` renvoie."""
    if en_base(name):
        with transaction():
            data = _db_lire(name, default)
            result = fn(data)
            _db_ecrire(name, data)
            return result
    with locked(name):
        data = read_json(name, default)
        result = fn(data)
        write_json(name, data)
        return result


def supprimer(name: str) -> None:
    """Efface un état (fichier et, si la base existe, sa ligne) : les deux modes restent cohérents."""
    state_path(name).unlink(missing_ok=True)
    if name.endswith(".json") and db_path().exists():
        connexion().execute("DELETE FROM etat WHERE nom = ?", (name,))


def existe(name: str) -> bool:
    if en_base(name):
        return connexion().execute("SELECT 1 FROM etat WHERE nom = ?", (name,)).fetchone() is not None
    return state_path(name).exists()


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
    """Vrai s'il reste au moins une cause de pause (voir pauses.py)."""
    from . import pauses
    return pauses.active()


def set_paused(value: bool, par: str = "humain") -> None:
    """Pose ou lève la cause « humain » seulement : les causes automatiques restent (pauses.py)."""
    from . import pauses
    if value:
        pauses.poser("humain", par=par)
    else:
        pauses.lever("humain", par=par)
