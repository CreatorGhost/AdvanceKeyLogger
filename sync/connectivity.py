"""
Connectivity Monitor — network detection, probing, and sync policy engine.

Runs as a background daemon thread, periodically probing the transport
endpoint and tracking network characteristics.  The sync engine queries
the monitor to decide *when* and *how much* to sync.

Features:
  * Network type detection (WiFi / cellular / wired / VPN / unknown)
  * Latency probing via TCP connect to the transport endpoint
  * Bandwidth estimation from recent send throughput
  * Jitter tracking (latency variance) for connection stability
  * Per-network-type sync policies (batch limits, intervals)
  * Backpressure signal when local storage exceeds a threshold
  * Callback registration for connect/disconnect transitions
"""

from __future__ import annotations

import logging
import socket
import statistics
import threading
import time
from collections import deque
from enum import Enum
from typing import Any, Callable
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class NetworkType(str, Enum):
    WIFI = "wifi"
    CELLULAR = "cellular"
    WIRED = "wired"
    VPN = "vpn"
    UNKNOWN = "unknown"
    OFFLINE = "offline"


class ConnectionStatus:
    """Snapshot of the current connectivity state."""

    __slots__ = (
        "online", "network_type", "latency_ms", "jitter_ms",
        "bandwidth_bps", "backpressure", "timestamp",
    )

    def __init__(self) -> None:
        self.online: bool = False
        self.network_type: NetworkType = NetworkType.UNKNOWN
        self.latency_ms: float = 0.0
        self.jitter_ms: float = 0.0
        self.bandwidth_bps: float = 0.0
        self.backpressure: bool = False
        self.timestamp: float = time.time()

    def to_dict(self) -> dict[str, Any]:
        return {
            "online": self.online,
            "network_type": self.network_type.value,
            "latency_ms": round(self.latency_ms, 1),
            "jitter_ms": round(self.jitter_ms, 1),
            "bandwidth_bps": round(self.bandwidth_bps, 0),
            "backpressure": self.backpressure,
            "timestamp": self.timestamp,
        }


class SyncPolicy:
    """Policy governing sync behaviour for the current network conditions."""

    __slots__ = ("max_batch_mb", "min_interval", "allowed")

    def __init__(
        self,
        max_batch_mb: float = 5.0,
        min_interval: float = 10.0,
        allowed: bool = True,
    ) -> None:
        self.max_batch_mb = max_batch_mb
        self.min_interval = min_interval
        self.allowed = allowed


# Default policies per network type
_DEFAULT_POLICIES: dict[str, dict[str, Any]] = {
    "wifi": {"max_batch_mb": 10, "min_interval": 0},
    "cellular": {"max_batch_mb": 1, "min_interval": 300},
    "wired": {"max_batch_mb": 20, "min_interval": 0},
    "vpn": {"max_batch_mb": 5, "min_interval": 10},
    "default": {"max_batch_mb": 5, "min_interval": 10},
}


class ConnectivityMonitor:
    """Background monitor for network connectivity and quality.

    Config keys (under ``sync.connectivity``):
      * ``check_interval`` — seconds between probes (default 30)
      * ``probe_timeout`` — TCP connect timeout in seconds (default 5)
      * ``backpressure_threshold_mb`` — local DB size triggering urgency (default 100)
      * ``policies`` — per-network-type overrides (see ``_DEFAULT_POLICIES``)
    """

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        probe_host: str = "",
        probe_port: int = 443,
    ) -> None:
        cfg = (config or {}).get("sync", {}).get("connectivity", {})
        self._check_interval = float(cfg.get("check_interval", 30))
        self._probe_timeout = float(cfg.get("probe_timeout", 5))
        self._bp_threshold_bytes = float(cfg.get("backpressure_threshold_mb", 100)) * 1024 * 1024

        # Build policies
        self._policies: dict[str, SyncPolicy] = {}
        raw_policies = cfg.get("policies", {})
        for net_type, defaults in _DEFAULT_POLICIES.items():
            overrides = raw_policies.get(net_type, {})
            merged = {**defaults, **overrides}
            self._policies[net_type] = SyncPolicy(
                max_batch_mb=float(merged.get("max_batch_mb", 5)),
                min_interval=float(merged.get("min_interval", 10)),
            )

        # Probe target — derived from transport URL or explicit
        self._probe_host = probe_host
        self._probe_port = probe_port

        # State
        self._status = ConnectionStatus()
        self._latency_history: deque[float] = deque(maxlen=30)
        self._bandwidth_history: deque[float] = deque(maxlen=20)
        self._callbacks: list[Callable[[ConnectionStatus], None]] = []
        self._was_online = False

        # Background thread
        self._running = False
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the background monitoring thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._monitor_loop, daemon=True, name="connectivity-monitor"
        )
        self._thread.start()
        logger.info("ConnectivityMonitor started (interval=%.0fs)", self._check_interval)

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)

    def set_probe_from_url(self, url: str) -> None:
        """Extract host:port from a transport URL for probing."""
        try:
            parsed = urlparse(url)
            self._probe_host = parsed.hostname or ""
            self._probe_port = parsed.port or (443 if parsed.scheme == "https" else 80)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_connectivity_change(self, callback: Callable[[ConnectionStatus], None]) -> None:
        """Register a callback fired on online/offline transitions."""
        self._callbacks.append(callback)

    # ------------------------------------------------------------------
    # Public queries
    # ------------------------------------------------------------------

    @property
    def status(self) -> ConnectionStatus:
        with self._lock:
            return self._status

    def can_sync(self) -> bool:
        """Check if syncing is allowed right now."""
        s = self.status
        if not s.online:
            return False
        policy = self.get_policy()
        return policy.allowed

    def get_policy(self) -> SyncPolicy:
        """Return the current sync policy based on network type."""
        net = self._status.network_type.value
        return self._policies.get(net, self._policies.get("default", SyncPolicy()))

    def record_send(self, bytes_sent: int, elapsed_seconds: float) -> None:
        """Record a completed send for bandwidth estimation."""
        if elapsed_seconds > 0:
            bps = bytes_sent / elapsed_seconds
            self._bandwidth_history.append(bps)
            with self._lock:
                self._status.bandwidth_bps = (
                    statistics.mean(self._bandwidth_history)
                    if self._bandwidth_history else 0.0
                )

    def check_backpressure(self, db_path: str | None = None) -> bool:
        """Check if local storage exceeds the backpressure threshold."""
        if not db_path:
            return False
        try:
            from pathlib import Path

            size = Path(db_path).stat().st_size
            bp = size > self._bp_threshold_bytes
            with self._lock:
                self._status.backpressure = bp
            return bp
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Background loop
    # ------------------------------------------------------------------

    def _monitor_loop(self) -> None:
        while self._running:
            try:
                self._probe()
            except Exception as exc:
                logger.debug("Connectivity probe failed: %s", exc)
            time.sleep(self._check_interval)

    def _probe(self) -> None:
        """Single probe cycle: detect network type, measure latency."""
        net_type = self._detect_network_type()
        latency = self._measure_latency()
        online = latency >= 0

        # Update latency history
        if online:
            self._latency_history.append(latency)

        jitter = 0.0
        if len(self._latency_history) >= 2:
            jitter = statistics.stdev(self._latency_history)

        new_status = ConnectionStatus()
        new_status.online = online
        new_status.network_type = net_type if online else NetworkType.OFFLINE
        new_status.latency_ms = latency if online else 0.0
        new_status.jitter_ms = jitter
        new_status.bandwidth_bps = self._status.bandwidth_bps
        new_status.backpressure = self._status.backpressure
        new_status.timestamp = time.time()

        with self._lock:
            self._status = new_status

        # Fire callbacks on transition
        if online != self._was_online:
            self._was_online = online
            for cb in self._callbacks:
                try:
                    cb(new_status)
                except Exception as exc:
                    logger.warning("Connectivity callback failed: %s", exc)

    def _measure_latency(self) -> float:
        """TCP connect to probe target.  Returns RTT in ms, or -1 if unreachable."""
        if not self._probe_host:
            # No probe target configured — assume online
            return 0.0
        sock = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(self._probe_timeout)
            start = time.monotonic()
            sock.connect((self._probe_host, self._probe_port))
            elapsed = (time.monotonic() - start) * 1000  # ms
            return elapsed
        except (OSError, socket.timeout):
            return -1.0
        finally:
            if sock is not None:
                sock.close()

    def _detect_network_type(self) -> NetworkType:
        """Best-effort network type detection using psutil."""
        try:
            import psutil

            stats = psutil.net_if_stats()
            addrs = psutil.net_if_addrs()
            for iface, st in stats.items():
                if not st.isup:
                    continue
                name_lower = iface.lower()
                # Skip loopback
                if "lo" in name_lower or "loopback" in name_lower:
                    continue
                if iface not in addrs:
                    continue
                # Heuristics based on interface naming conventions
                if any(k in name_lower for k in ("tun", "tap", "vpn", "wg", "utun")):
                    return NetworkType.VPN
                if any(k in name_lower for k in ("wlan", "wi-fi", "wifi", "airport", "en0")):
                    return NetworkType.WIFI
                if any(k in name_lower for k in ("wwan", "pdp_ip", "rmnet", "cellular")):
                    return NetworkType.CELLULAR
                if any(k in name_lower for k in ("eth", "en1", "en2", "enp", "ens")):
                    return NetworkType.WIRED
        except ImportError:
            pass
        except Exception as exc:
            logger.debug("Network type detection failed: %s", exc)
        return NetworkType.UNKNOWN
