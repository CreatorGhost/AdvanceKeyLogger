"""
FTP transport using ftplib.

Uploads report bytes to an FTP server.
"""
from __future__ import annotations

import io
from ftplib import FTP, FTP_TLS
from typing import Any

from transport import register_transport
from transport.base import BaseTransport
from utils.resilience import retry


@register_transport("ftp")
class FTPTransport(BaseTransport):
    """FTP transport (uploads files)."""

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self._host = config.get("host")
        self._port = int(config.get("port", 21))
        self._username = config.get("username")
        self._password = config.get("password")
        self._remote_dir = config.get("remote_dir", "/")
        self._use_tls = bool(config.get("use_tls", False))
        self._ftp: FTP | None = None

    def connect(self) -> None:
        if not self._host:
            raise ValueError("FTP transport requires host")
        self._ftp = FTP_TLS() if self._use_tls else FTP()
        self._ftp.connect(self._host, self._port, timeout=10)
        if self._username:
            self._ftp.login(self._username, self._password or "")
        else:
            self._ftp.login()
        if self._use_tls and isinstance(self._ftp, FTP_TLS):
            self._ftp.prot_p()
        if self._remote_dir:
            self._ensure_remote_dir(self._remote_dir)
        self._connected = True

    def _ensure_remote_dir(self, path: str) -> None:
        """Navigate to *path*, creating each component that doesn't exist."""
        assert self._ftp is not None  # noqa: S101
        if path.startswith("/"):
            self._ftp.cwd("/")
        for part in path.split("/"):
            if not part:
                continue
            try:
                self._ftp.cwd(part)
            except Exception:
                self._ftp.mkd(part)
                self._ftp.cwd(part)

    @retry(max_attempts=3, backoff_base=2.0, retry_on_false=True)
    def send(self, data: bytes, metadata: dict[str, Any] | None = None) -> bool:
        if not self._connected:
            self.connect()
        if not self._ftp:
            return False
        try:
            filename = (metadata or {}).get("filename", "report.bin")
            bio = io.BytesIO(data)
            self._ftp.storbinary(f"STOR {filename}", bio)
            return True
        except Exception as exc:
            self.logger.error("FTP send failed: %s", exc)
            # Reset the FTP connection so it doesn't remain in an undefined state
            self._connected = False
            try:
                if self._ftp:
                    self._ftp.close()
            except Exception:
                pass
            self._ftp = None
            return False

    def disconnect(self) -> None:
        if self._ftp is not None:
            try:
                self._ftp.quit()
            except Exception:
                self._ftp.close()
            self._ftp = None
        self._connected = False
