"""
Network traffic normalisation for stealth mode.

Makes outbound traffic indistinguishable from normal browsing by:

  - Gaussian timing jitter on send intervals
  - Packet-size normalisation (padding + chunking)
  - User-Agent rotation (``fake-useragent`` or built-in fallback)
  - Send-window scheduling (only transmit during "active hours")
  - Bandwidth throttling via token-bucket algorithm
  - DNS query minimisation (local cache)

Usage::

    from stealth.network_normalizer import NetworkNormalizer

    norm = NetworkNormalizer(config)
    norm.apply_to_session(requests_session)
    norm.wait_jitter(base_interval=30.0)
    payload = norm.normalize_payload(raw_bytes)
"""
from __future__ import annotations

import logging
import os
import random
import socket
import time
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

# ── Built-in fallback User-Agent strings ─────────────────────────────

_FALLBACK_USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPad; CPU OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.6099.144 Mobile Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64; rv:122.0) Gecko/20100101 Firefox/122.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36 Edg/121.0.0.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
]

# Minimum/maximum payload sizes for normalisation
_MIN_PAYLOAD_SIZE = 1024       # 1 KB
_MAX_PAYLOAD_CHUNK = 16384     # 16 KB


class TokenBucket:
    """Simple token-bucket rate limiter for bandwidth throttling."""

    def __init__(self, rate_bps: float) -> None:
        self._rate = rate_bps  # bytes per second
        self._tokens = rate_bps
        self._last_refill = time.monotonic()

    def consume(self, nbytes: int) -> float:
        """Consume *nbytes* tokens, returning the seconds to wait (0 if immediate)."""
        if self._rate <= 0:
            return 0.0
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self._rate, self._tokens + elapsed * self._rate)
        self._last_refill = now

        if self._tokens >= nbytes:
            self._tokens -= nbytes
            return 0.0

        deficit = nbytes - self._tokens
        wait = deficit / self._rate
        self._tokens = 0
        return wait


class NetworkNormalizer:
    """Manages network-traffic stealth measures.

    Parameters
    ----------
    config : dict
        The ``stealth.network`` section of the configuration.
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        cfg = config or {}
        self._timing_jitter: float = float(cfg.get("timing_jitter", 0.4))
        self._packet_normalization: bool = bool(cfg.get("packet_normalization", True))
        self._ua_rotation: bool = bool(cfg.get("user_agent_rotation", True))
        self._send_window_enabled: bool = bool(
            (cfg.get("send_window") or {}).get("enabled", False)
        )
        self._send_window_start: int = int(
            (cfg.get("send_window") or {}).get("start_hour", 9)
        )
        self._send_window_end: int = int(
            (cfg.get("send_window") or {}).get("end_hour", 18)
        )
        max_bw = int(cfg.get("max_bandwidth_bps", 0))
        self._throttle: TokenBucket | None = TokenBucket(max_bw) if max_bw > 0 else None

        # DNS cache
        self._dns_cache: dict[str, tuple[str, float]] = {}
        self._dns_ttl: float = 300.0  # 5 minutes

        # UA generator (lazy init)
        self._ua_gen: Any = None

    # ── Public API ───────────────────────────────────────────────────

    def apply_to_session(self, session: Any) -> None:
        """Apply stealth headers to a ``requests.Session``."""
        if self._ua_rotation:
            session.headers["User-Agent"] = self.get_user_agent()
        # Connection keep-alive
        session.headers["Connection"] = "keep-alive"
        # Accept headers matching Chrome
        session.headers.setdefault(
            "Accept",
            "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        )
        session.headers.setdefault("Accept-Language", "en-US,en;q=0.9")
        session.headers.setdefault("Accept-Encoding", "gzip, deflate, br")

    def get_user_agent(self) -> str:
        """Return a random realistic User-Agent string."""
        if self._ua_gen is None:
            try:
                from fake_useragent import UserAgent  # type: ignore[import-untyped]
                self._ua_gen = UserAgent()
            except ImportError:
                self._ua_gen = "fallback"

        if self._ua_gen == "fallback":
            return random.choice(_FALLBACK_USER_AGENTS)

        try:
            return self._ua_gen.random
        except Exception:
            return random.choice(_FALLBACK_USER_AGENTS)

    def wait_jitter(self, base_interval: float) -> None:
        """Sleep for *base_interval* with Gaussian jitter applied."""
        sigma = base_interval * self._timing_jitter
        wait = max(1.0, random.gauss(base_interval, sigma))
        time.sleep(wait)

    def jitter_value(self, base: float) -> float:
        """Return *base* with jitter (no sleep)."""
        sigma = base * self._timing_jitter
        return max(0.5, random.gauss(base, sigma))

    def normalize_payload(self, data: bytes) -> bytes:
        """Pad small payloads and ensure they look like typical HTTPS sizes."""
        if not self._packet_normalization:
            return data
        if len(data) < _MIN_PAYLOAD_SIZE:
            # Pad with random bytes (not zeros, to avoid detection)
            padding = os.urandom(_MIN_PAYLOAD_SIZE - len(data))
            return data + padding
        return data

    def is_in_send_window(self) -> bool:
        """Return whether the current time is within the send window."""
        if not self._send_window_enabled:
            return True
        hour = datetime.now().hour
        if self._send_window_start <= self._send_window_end:
            return self._send_window_start <= hour < self._send_window_end
        # Wrap-around (e.g., 22:00 - 06:00)
        return hour >= self._send_window_start or hour < self._send_window_end

    def throttle_wait(self, nbytes: int) -> None:
        """Wait if bandwidth throttling requires it."""
        if self._throttle is None:
            return
        wait = self._throttle.consume(nbytes)
        if wait > 0:
            time.sleep(wait)

    def resolve_dns(self, hostname: str) -> str:
        """Resolve hostname with local caching to reduce DNS queries."""
        now = time.monotonic()
        cached = self._dns_cache.get(hostname)
        if cached and (now - cached[1]) < self._dns_ttl:
            return cached[0]
        try:
            ip = socket.gethostbyname(hostname)
            self._dns_cache[hostname] = (ip, now)
            return ip
        except socket.gaierror:
            # Return hostname as-is on failure
            return hostname

    def get_status(self) -> dict[str, Any]:
        return {
            "timing_jitter": self._timing_jitter,
            "packet_normalization": self._packet_normalization,
            "ua_rotation": self._ua_rotation,
            "send_window_enabled": self._send_window_enabled,
            "in_send_window": self.is_in_send_window(),
            "bandwidth_throttle": self._throttle is not None,
        }
