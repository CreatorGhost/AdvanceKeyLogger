"""
Transport failover chain — automatic fallback across multiple transports.

Tries the primary transport first. On failure, cascades through a
configurable list of fallback transports until one succeeds.

Config::

    transport:
      method: "http"               # primary
      failover:
        enabled: true
        methods: ["dns", "email"]  # fallback order
        retry_primary_after: 300   # seconds before retrying primary

Usage::

    from transport.failover import FailoverTransport

    transport = FailoverTransport(config)
    transport.send(data, metadata)  # tries http -> dns -> email
"""
from __future__ import annotations

import logging
import time
from typing import Any

from transport import create_transport_for_method, get_transport_class
from transport.base import BaseTransport

logger = logging.getLogger(__name__)


class FailoverTransport(BaseTransport):
    """Transport wrapper that cascades through multiple transport methods.

    Parameters
    ----------
    config : dict
        Full config dict with ``transport.method`` (primary) and
        ``transport.failover.methods`` (fallback list).
    """

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config.get("transport", {}))
        self._full_config = config
        transport_cfg = config.get("transport", {})

        self._primary_method: str = transport_cfg.get("method", "http")
        failover_cfg = transport_cfg.get("failover", {})
        self._enabled: bool = bool(failover_cfg.get("enabled", False))
        self._fallback_methods: list[str] = list(failover_cfg.get("methods", []))
        self._retry_primary_after: float = float(failover_cfg.get("retry_primary_after", 300))

        # Transport instances (lazy-created)
        self._primary: BaseTransport | None = None
        self._fallbacks: dict[str, BaseTransport] = {}
        self._primary_failed_at: float = 0.0
        self._consecutive_total_failures: int = 0

    def connect(self) -> None:
        """Connect the primary transport.

        Raises on failure, matching the ``BaseTransport.connect() -> None``
        contract.  Use ``try_connect()`` if you need a boolean result.
        """
        self._primary = create_transport_for_method(self._full_config, self._primary_method)
        if self._primary is None:
            raise ConnectionError(
                f"Failed to create primary transport: {self._primary_method}"
            )
        if hasattr(self._primary, "connect"):
            self._primary.connect()
        self._connected = True

    def try_connect(self) -> bool:
        """Attempt to connect the primary transport, returning success bool."""
        try:
            self.connect()
            return True
        except Exception as exc:
            logger.debug("Primary transport (%s) connect failed: %s",
                         self._primary_method, exc)
            return False

    def disconnect(self) -> None:
        if self._primary:
            try:
                self._primary.disconnect()
            except Exception:
                pass
        for t in self._fallbacks.values():
            try:
                t.disconnect()
            except Exception:
                pass
        self._connected = False

    def send(self, data: bytes, metadata: dict[str, Any] | None = None) -> bool:
        """Try primary transport, then cascade through fallbacks on failure."""
        # Exponential backoff when entire chain has failed repeatedly
        if self._consecutive_total_failures > 3:
            backoff = min(2 ** self._consecutive_total_failures, 60)
            logger.debug("Backoff %.1fs before retry (consecutive total failures: %d)",
                         backoff, self._consecutive_total_failures)
            time.sleep(backoff)

        has_fallbacks = self._enabled and bool(self._fallback_methods)

        # Apply primary backoff only when fallbacks are available;
        # otherwise always attempt the primary so data isn't silently dropped.
        now = time.time()
        if has_fallbacks and self._primary_failed_at != 0 and \
           (now - self._primary_failed_at) <= self._retry_primary_after:
            # Primary recently failed and fallbacks exist — skip to fallbacks
            pass
        else:
            if self._try_send(self._primary_method, data, metadata):
                self._primary_failed_at = 0
                self._consecutive_total_failures = 0
                return True
            if has_fallbacks:
                self._primary_failed_at = now
            logger.warning("Primary transport (%s) failed, trying fallbacks",
                           self._primary_method)

        # Try fallbacks in order
        if not has_fallbacks:
            self._consecutive_total_failures += 1
            return False

        for method in self._fallback_methods:
            if self._try_send(method, data, metadata):
                logger.info("Fallback transport (%s) succeeded", method)
                # Reset primary timer so it's retried sooner after a fallback win
                self._primary_failed_at = now
                self._consecutive_total_failures = 0
                return True
            logger.debug("Fallback transport (%s) also failed", method)

        self._consecutive_total_failures += 1
        logger.error("All transports failed (primary: %s, fallbacks: %s)",
                     self._primary_method, self._fallback_methods)
        return False

    def _try_send(self, method: str, data: bytes, metadata: dict[str, Any] | None) -> bool:
        """Attempt to send via a specific transport method."""
        try:
            # Get or create the transport instance
            if method == self._primary_method and self._primary:
                transport = self._primary
            elif method in self._fallbacks:
                transport = self._fallbacks[method]
            else:
                transport = create_transport_for_method(self._full_config, method)
                if transport is None:
                    logger.warning("Failed to create transport for method: %s", method)
                    return False
                # Cache the transport for reuse
                if method == self._primary_method:
                    self._primary = transport
                else:
                    self._fallbacks[method] = transport

            # Connect if needed
            if hasattr(transport, "_connected") and not transport._connected:
                if hasattr(transport, "connect"):
                    transport.connect()

            return transport.send(data, metadata)

        except Exception as exc:
            logger.warning("Transport %s send failed: %s", method, exc)
            return False

    def preflight(self) -> bool:
        """Health check on primary transport."""
        if self._primary and hasattr(self._primary, "preflight"):
            return self._primary.preflight()
        return True
