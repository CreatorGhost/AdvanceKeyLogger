"""
HTTP transport using requests.

Sends report bytes to a configured URL.
"""
from __future__ import annotations

import time
from typing import Any

import requests

from transport import register_transport
from transport.base import BaseTransport
from utils.resilience import retry


@register_transport("http")
class HttpTransport(BaseTransport):
    """HTTP transport (POST/PUT)."""

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self._url = config.get("url")
        self._method = str(config.get("method", "POST")).upper()
        self._headers = dict(config.get("headers", {}))
        self._timeout = float(config.get("timeout", 30))
        self._verify = config.get("verify", True)
        self._ca_cert = config.get("ca_cert")
        if self._ca_cert:
            self._verify = self._ca_cert
        self._health_url = config.get("healthcheck_url")
        self._health_ttl = float(config.get("healthcheck_interval", 60))
        self._last_health_ts = 0.0
        self._healthy = True
        self._session: requests.Session | None = None

    def connect(self) -> None:
        if not self._url:
            raise ValueError("HTTP transport requires a URL")
        self._session = requests.Session()
        if self._headers:
            self._session.headers.update(self._headers)
        self._connected = True

    def preflight(self) -> bool:
        if not self._health_url:
            return True
        now = time.time()
        if now - self._last_health_ts < self._health_ttl:
            return self._healthy
        self._last_health_ts = now
        try:
            if not self._session:
                self.connect()
            response = self._session.get(
                self._health_url,
                timeout=self._timeout,
                verify=self._verify,
            )
            self._healthy = 200 <= response.status_code < 300
        except requests.RequestException:
            self._healthy = False
        return self._healthy

    @retry(max_attempts=3, backoff_base=2.0, retry_on_false=True)
    def send(self, data: bytes, metadata: dict[str, Any] | None = None) -> bool:
        if not self._connected:
            self.connect()
        if not self._session:
            return False
        if self._health_url and not self.preflight():
            return False
        try:
            headers = {}
            if metadata and metadata.get("content_type"):
                headers["Content-Type"] = metadata["content_type"]
            response = self._session.request(
                self._method,
                self._url,
                data=data,
                headers=headers,
                timeout=self._timeout,
                verify=self._verify,
            )
            return 200 <= response.status_code < 300
        except requests.RequestException as exc:
            self.logger.error("HTTP send failed: %s", exc)
            return False

    def disconnect(self) -> None:
        if self._session is not None:
            self._session.close()
            self._session = None
        self._connected = False
