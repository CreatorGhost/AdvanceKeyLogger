"""
Email transport using SMTP.

Sends a report as an email with optional attachments.
"""
from __future__ import annotations

import mimetypes
import smtplib
from email.message import EmailMessage
from typing import Any

from transport import register_transport
from transport.base import BaseTransport
from utils.resilience import retry


@register_transport("email")
class EmailTransport(BaseTransport):
    """SMTP email transport."""

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self._smtp: smtplib.SMTP | smtplib.SMTP_SSL | None = None
        self._server = config.get("smtp_server", "smtp.gmail.com")
        self._port = int(config.get("smtp_port", 465))
        self._use_ssl = bool(config.get("use_ssl", True))
        self._sender = config.get("sender")
        self._password = config.get("password")
        self._recipient = config.get("recipient")

    def connect(self) -> None:
        if self._connected:
            return
        if not self._sender or not self._recipient:
            raise ValueError("Email transport requires sender and recipient")
        if self._use_ssl:
            self._smtp = smtplib.SMTP_SSL(self._server, self._port, timeout=10)
        else:
            self._smtp = smtplib.SMTP(self._server, self._port, timeout=10)
            self._smtp.starttls()
        if self._password:
            self._smtp.login(self._sender, self._password)
        self._connected = True

    @retry(max_attempts=3, backoff_base=2.0, retry_on_false=True)
    def send(self, data: bytes, metadata: dict[str, Any] | None = None) -> bool:
        if not self._connected:
            self.connect()
        if not self._smtp:
            return False

        try:
            meta = metadata or {}
            subject = meta.get("subject", "Report")
            body = meta.get("body", "Report attached.")
            filename = meta.get("filename", "report.bin")
            mime_type = meta.get("content_type") or meta.get("mime_type")

            msg = EmailMessage()
            msg["Subject"] = subject
            msg["From"] = self._sender
            msg["To"] = self._recipient
            msg.set_content(body)

            maintype, subtype = _split_mime(mime_type, filename)
            msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=filename)

            for attachment in meta.get("attachments", []):
                att_data = attachment.get("data", b"")
                att_name = attachment.get("filename", "attachment.bin")
                att_mime = attachment.get("content_type") or attachment.get("mime_type")
                maintype, subtype = _split_mime(att_mime, att_name)
                msg.add_attachment(
                    att_data,
                    maintype=maintype,
                    subtype=subtype,
                    filename=att_name,
                )

            self._smtp.send_message(msg)
            return True
        except smtplib.SMTPServerDisconnected:
            self.logger.warning("SMTP connection lost, will reconnect on next attempt")
            self._connected = False
            self._smtp = None
            return False
        except Exception as exc:
            self.logger.error("Email send failed: %s", exc)
            # Reset the SMTP connection so it doesn't remain in an undefined state
            self._connected = False
            try:
                if self._smtp:
                    self._smtp.close()
            except Exception:
                pass
            self._smtp = None
            return False

    def disconnect(self) -> None:
        if self._smtp is not None:
            try:
                self._smtp.quit()
            except Exception:
                try:
                    self._smtp.close()
                except Exception:
                    pass
            finally:
                self._smtp = None
        self._connected = False


def _split_mime(mime_type: str | None, filename: str) -> tuple[str, str]:
    if not mime_type:
        mime_type, _ = mimetypes.guess_type(filename)
    if mime_type and "/" in mime_type:
        return tuple(mime_type.split("/", 1))  # type: ignore[return-value]
    return ("application", "octet-stream")
