"""Prévenir l'humain : Telegram, notification Windows et barre tmux."""

from __future__ import annotations

import base64
import shutil
import subprocess
from pathlib import Path

from . import config, store
from .telegram import Bot, TelegramError

POWERSHELL_PATHS = [
    "/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe",
    "powershell.exe",
]
# Identifiant d'application déjà enregistré par Windows : les toasts s'affichent sans installation.
TOAST_APP_ID = r"{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe"


def bot_and_chat() -> tuple[Bot | None, str]:
    s = config.settings()["telegram"]
    if not (s.get("token") and s.get("chat_id")):
        return None, ""
    try:
        return Bot(s["token"]), str(s["chat_id"])
    except TelegramError:
        return None, ""


def telegram(text: str, buttons=None) -> bool:
    bot, chat = bot_and_chat()
    if not bot:
        return False
    try:
        bot.send(chat, text, buttons)
        return True
    except TelegramError as exc:
        store.feed_add("erreur", f"Telegram : {exc}")
        return False


def _powershell() -> str | None:
    for p in POWERSHELL_PATHS:
        if Path(p).exists() or shutil.which(p):
            return p
    return None


def _ps_quote(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


def toast(title: str, text: str) -> bool:
    """Notification Windows (WSL). Sans effet hors Windows ; ne bloque jamais."""
    if not config.settings()["notifications"].get("windows", True):
        return False
    ps = _powershell()
    if not ps:
        return False
    script = (
        "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null;"
        "$t = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent("
        "[Windows.UI.Notifications.ToastTemplateType]::ToastText02);"
        "$x = $t.GetElementsByTagName('text');"
        f"$x.Item(0).AppendChild($t.CreateTextNode({_ps_quote(title)})) > $null;"
        f"$x.Item(1).AppendChild($t.CreateTextNode({_ps_quote(text[:200])})) > $null;"
        f"[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier({_ps_quote(TOAST_APP_ID)})"
        ".Show([Windows.UI.Notifications.ToastNotification]::new($t))"
    )
    encoded = base64.b64encode(script.encode("utf-16-le")).decode()
    try:
        subprocess.Popen([ps, "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        return True
    except OSError:
        return False


def tmux_message(text: str) -> None:
    if shutil.which("tmux"):
        subprocess.run(["tmux", "display-message", "-d", "5000", text[:150]],
                       capture_output=True, timeout=5, check=False)


def plan_buttons(plan_id: str) -> list[list[tuple[str, str]]]:
    return [[("✅ Approuver", f"ok:{plan_id}"), ("✋ Refuser", f"non:{plan_id}")]]


def rollback_buttons(tache_id: str) -> list[list[tuple[str, str]]]:
    return [[("↩ Revert", f"rbok:{tache_id}"), ("Garder", f"rbnon:{tache_id}")]]


def proposition_buttons(prop_id: str) -> list[list[tuple[str, str]]]:
    return [[("✅ Accepter", f"mok:{prop_id}"), ("✋ Refuser", f"mnon:{prop_id}")]]


def alert(kind: str, text: str, *, buttons=None, title: str = "JARVIS", windows: bool = True, **extra) -> dict:
    """Événement important pour l'humain : fil + Telegram + toast Windows."""
    event = store.feed_add(kind, text, **extra)
    icon = event["icone"]
    telegram(f"{icon} {text}", buttons)
    if windows:
        toast(title, f"{icon} {text}")
    return event
