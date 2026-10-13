"""Pré-accepter la confiance d'un nouveau worktree, pour que l'agent démarre sans question.

Chaque worktree est un dépôt git à part : la confiance accordée à ~/projets ne le couvre pas.
- Claude Code : projects["<chemin>"].hasTrustDialogAccepted = true dans ~/.claude.json
  (méthode documentée : code.claude.com/docs/en/permissions, « workspace trust »).
- Codex : [projects."<chemin>"] trust_level = "trusted" dans ~/.codex/config.toml.
"""

from __future__ import annotations

import fcntl
import json
import os
import re
from pathlib import Path

from . import config


def claude_json_path() -> Path:
    base = os.environ.get("CLAUDE_CONFIG_DIR")
    return Path(base) / ".claude.json" if base else config.HOME / ".claude.json"


def codex_config_path() -> Path:
    return Path(os.environ.get("CODEX_HOME") or config.HOME / ".codex") / "config.toml"


def trust_claude(path: str) -> bool:
    """Marque `path` comme approuvé pour Claude Code. Renvoie True si le fichier a changé."""
    target = claude_json_path()
    if not target.exists():
        return False  # Claude Code n'a jamais été lancé : c'est lui qui crée ce fichier
    path = str(Path(path).resolve())
    lock = target.with_name(".claude.json.jarvis-lock")
    target.parent.mkdir(parents=True, exist_ok=True)
    with lock.open("a") as lk:
        fcntl.flock(lk, fcntl.LOCK_EX)
        try:
            data = json.loads(target.read_text(encoding="utf-8")) if target.exists() else {}
        except json.JSONDecodeError:
            return False  # fichier en cours d'écriture par Claude : on ne risque pas de l'abîmer
        projects = data.setdefault("projects", {})
        entry = projects.setdefault(path, {})
        if entry.get("hasTrustDialogAccepted") is True:
            return False
        entry["hasTrustDialogAccepted"] = True
        tmp = target.with_name(".claude.json.jarvis-tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        if target.exists():
            os.chmod(tmp, target.stat().st_mode & 0o777)
        tmp.replace(target)
        return True


def _toml_key(path: str) -> str:
    return '"' + path.replace("\\", "\\\\").replace('"', '\\"') + '"'


def trust_codex(path: str) -> bool:
    """Ajoute le worktree aux projets de confiance de Codex. Renvoie True si le fichier a changé."""
    target = codex_config_path()
    path = str(Path(path).resolve())
    header = f"[projects.{_toml_key(path)}]"
    target.parent.mkdir(parents=True, exist_ok=True)
    text = target.read_text(encoding="utf-8") if target.exists() else ""
    # Une table déjà présente (même écrite autrement) ne doit jamais être dupliquée : TOML invalide.
    pattern = re.compile(r"^\[projects\.(\"|')" + re.escape(path) + r"(\"|')\]\s*$", re.MULTILINE)
    if pattern.search(text):
        return False
    block = f"\n{header}\ntrust_level = \"trusted\"\n"
    with target.open("a", encoding="utf-8") as fh:
        if text and not text.endswith("\n"):
            fh.write("\n")
        fh.write(block)
    return True


def prepare(agent: str, path: str) -> list[str]:
    """Prépare la confiance pour l'agent qui va travailler dans `path`. Renvoie ce qui a été fait."""
    done = []
    if agent in ("claude", "cc"):
        if trust_claude(path):
            done.append("confiance Claude")
    elif agent in ("codex", "cx"):
        if trust_codex(path):
            done.append("confiance Codex")
    return done
