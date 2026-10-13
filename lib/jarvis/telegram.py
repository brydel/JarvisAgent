"""Client minimal de l'API Telegram Bot (urllib, sans dépendance)."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

API_BASE = os.environ.get("JARVIS_TELEGRAM_API", "https://api.telegram.org")
MAX_LEN = 3900  # limite Telegram : 4096 caractères par message


class TelegramError(RuntimeError):
    pass


class Bot:
    def __init__(self, token: str, api_base: str | None = None):
        if not token:
            raise TelegramError("aucun jeton Telegram configuré (jarvis telegram config)")
        self.token = token
        self.base = (api_base or os.environ.get("JARVIS_TELEGRAM_API") or API_BASE).rstrip("/")

    def call(self, method: str, http_timeout: int = 30, **params):
        url = f"{self.base}/bot{self.token}/{method}"
        body = json.dumps({k: v for k, v in params.items() if v is not None}).encode()
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=http_timeout) as resp:
                data = json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            try:
                detail = json.loads(exc.read().decode()).get("description", "")
            except Exception:  # noqa: BLE001 — on veut juste un message lisible
                detail = ""
            raise TelegramError(f"{method} : HTTP {exc.code} {detail}".strip()) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise TelegramError(f"{method} : {exc}") from exc
        if not data.get("ok"):
            raise TelegramError(f"{method} : {data.get('description', 'erreur inconnue')}")
        return data.get("result")

    def me(self) -> dict:
        return self.call("getMe")

    def updates(self, offset: int | None, wait: int = 25) -> list[dict]:
        # `timeout` ici est le long-polling côté Telegram ; le délai HTTP doit être plus long.
        return self.call("getUpdates", http_timeout=wait + 15, offset=offset, timeout=wait,
                         allowed_updates=["message", "callback_query"]) or []

    def send(self, chat_id, text: str, buttons: list[list[tuple[str, str]]] | None = None) -> dict:
        markup = None
        if buttons:
            markup = {"inline_keyboard": [[{"text": t, "callback_data": d} for t, d in row] for row in buttons]}
        if len(text) > MAX_LEN:
            text = text[:MAX_LEN] + "\n…"
        return self.call("sendMessage", chat_id=chat_id, text=text, reply_markup=markup,
                         disable_web_page_preview=True)

    def download(self, file_id: str, dest, max_bytes: int = 20 * 1024 * 1024) -> None:
        """Télécharge un fichier envoyé au bot (photo, document) vers `dest`."""
        info = self.call("getFile", file_id=file_id) or {}
        path = info.get("file_path")
        if not path:
            raise TelegramError("getFile : chemin du fichier absent")
        if (info.get("file_size") or 0) > max_bytes:
            raise TelegramError("fichier trop gros")
        url = f"{self.base}/file/bot{self.token}/{path}"
        try:
            with urllib.request.urlopen(url, timeout=60) as resp:
                data = resp.read(max_bytes + 1)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise TelegramError(f"téléchargement : {exc}") from exc
        if len(data) > max_bytes:
            raise TelegramError("fichier trop gros")
        tmp = f"{dest}.part"
        with open(tmp, "wb") as fh:
            fh.write(data)
        os.replace(tmp, dest)

    def answer(self, callback_id: str, text: str = "") -> None:
        self.call("answerCallbackQuery", callback_query_id=callback_id, text=text[:190] or None)

    def edit(self, chat_id, message_id: int, text: str) -> None:
        self.call("editMessageText", chat_id=chat_id, message_id=message_id, text=text[:MAX_LEN])
