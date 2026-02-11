"""
Sync Engine — orchestrator for the offline-first sync pipeline.

Coordinates the :class:`SyncLedger`, :class:`ConnectivityMonitor`,
:class:`CheckpointManager`, and :class:`ConflictResolver` into a single
``process_pending()`` call that the main loop invokes each cycle.

Features:
  * State machine: IDLE → SYNCING → PAUSED → ERROR
  * Priority-based sync (CRITICAL → NORMAL → LOW)
  * Adaptive batch sizing (grows on success, shrinks on failure)
  * zlib compression with configurable threshold
  * SHA-256 integrity verification per batch
  * Rolling health metrics (success rate, latency, throughput, queue depth)
  * Graceful degradation with exponential backoff
  * Scheduling modes: immediate / interval / manual
  * Drop-in replacement for the old get_pending → send → mark_sent loop
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
import zlib
from collections import deque
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable
from uuid import uuid4

from sync.ledger import SyncLedger, SyncState
from sync.connectivity import ConnectivityMonitor, ConnectionStatus
from sync.checkpoint import CheckpointManager
from sync.conflict_resolver import ConflictResolver

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Engine state machine
# ---------------------------------------------------------------------------

class SyncEngineState(str, Enum):
    IDLE = "IDLE"
    SYNCING = "SYNCING"
    PAUSED = "PAUSED"
    ERROR = "ERROR"


# ---------------------------------------------------------------------------
# Health metrics
# ---------------------------------------------------------------------------

@dataclass
class SyncHealth:
    """Rolling health metrics for the sync engine."""

    state: str = "IDLE"
    total_synced: int = 0
    total_failed: int = 0
    consecutive_failures: int = 0
    success_rate: float = 1.0
    avg_latency_ms: float = 0.0
    throughput_bps: float = 0.0
    queue_depth: int = 0
    oldest_unsynced_age: float = 0.0
    current_batch_size: int = 0
    last_sync_at: float = 0.0
    last_error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "total_synced": self.total_synced,
            "total_failed": self.total_failed,
            "consecutive_failures": self.consecutive_failures,
            "success_rate": round(self.success_rate, 3),
            "avg_latency_ms": round(self.avg_latency_ms, 1),
            "throughput_bps": round(self.throughput_bps, 0),
            "queue_depth": self.queue_depth,
            "oldest_unsynced_age": round(self.oldest_unsynced_age, 1),
            "current_batch_size": self.current_batch_size,
            "last_sync_at": self.last_sync_at,
            "last_error": self.last_error,
        }


# ---------------------------------------------------------------------------
# Sync Engine
# ---------------------------------------------------------------------------

class SyncEngine:
    """Orchestrate offline-first sync with adaptive batching and resilience.

    Parameters
    ----------
    config : dict
        Full application config (reads the ``sync`` section).
    sqlite_store : SQLiteStorage
        The existing SQLite storage instance (for access to ``_conn``).
    transport : BaseTransport
        The transport instance used to send data.
    build_payload : callable, optional
        ``(batch_items, config, sys_info) -> (payload_bytes, metadata, file_paths)``
        Reuses the existing ``_build_report_bundle`` from main.py.
    apply_encryption : callable, optional
        ``(payload, metadata, config, data_dir, e2e_protocol) -> (payload, metadata)``
        Reuses the existing ``_apply_encryption`` from main.py.
    """

    def __init__(
        self,
        config: dict[str, Any],
        sqlite_store: Any,
        transport: Any,
        build_payload: Callable | None = None,
        apply_encryption: Callable | None = None,
        sys_info: dict[str, Any] | None = None,
        e2e_protocol: Any = None,
    ) -> None:
        cfg = config.get("sync", {})

        # Core config
        self._config = config
        self._mode = cfg.get("mode", "immediate")
        self._interval = float(cfg.get("interval_seconds", 10))
        self._max_batch = int(cfg.get("max_batch_size", 50))
        self._min_batch = int(cfg.get("min_batch_size", 5))
        self._max_batch_mb = float(cfg.get("max_batch_mb", 10))
        self._compression = bool(cfg.get("compression", True))
        self._compress_threshold = int(cfg.get("compression_threshold_bytes", 1024))
        self._integrity_check = bool(cfg.get("integrity_check", True))
        self._backoff_base = float(cfg.get("retry_backoff_base", 2.0))
        self._backoff_max = float(cfg.get("retry_backoff_max", 300))

        # Dependencies
        self._store = sqlite_store
        self._transport = transport
        self._build_payload = build_payload
        self._apply_encryption = apply_encryption
        self._sys_info = sys_info or {}
        self._e2e_protocol = e2e_protocol

        # Sub-components (initialised against the same DB connection)
        conn = sqlite_store._conn  # share the connection
        self._ledger = SyncLedger(conn, config)
        self._checkpoint = CheckpointManager(conn, config)
        self._conflict = ConflictResolver(conn, config)
        self._connectivity = ConnectivityMonitor(config)

        # State
        self._state = SyncEngineState.IDLE
        self._health = SyncHealth()
        self._current_batch_size = self._min_batch
        self._last_sync_time = 0.0
        self._consecutive_failures = 0
        self._backoff_until = 0.0

        # Rolling metrics windows
        self._latency_window: deque[float] = deque(maxlen=50)
        self._throughput_window: deque[float] = deque(maxlen=50)
        self._success_window: deque[bool] = deque(maxlen=100)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the sync engine (connectivity monitor, crash recovery)."""
        # Set probe target from transport URL
        url = self._config.get("transport", {}).get(
            self._config.get("transport", {}).get("method", "http"), {}
        ).get("url", "")
        if url:
            self._connectivity.set_probe_from_url(url)

        self._connectivity.on_connectivity_change(self._on_connectivity_change)
        self._connectivity.start()

        # Crash recovery: re-queue incomplete checkpoints
        recovered = self._checkpoint.recover()
        if recovered:
            for cp in recovered:
                logger.info(
                    "Recovering batch %s: %d records to re-queue",
                    cp["batch_id"], len(cp["record_ids"]),
                )
                # Reset ledger entries to PENDING
                for rid in cp["record_ids"]:
                    try:
                        self._ledger._conn.execute(
                            "UPDATE sync_ledger SET sync_state = ?, batch_id = NULL "
                            "WHERE id = ? AND sync_state IN (?, ?)",
                            (SyncState.PENDING.value, rid,
                             SyncState.IN_FLIGHT.value, SyncState.QUEUED.value),
                        )
                    except Exception as exc:
                        logger.warning(
                            "Crash recovery reset failed for record %s: %s",
                            rid, exc,
                        )
                self._ledger._conn.commit()

        logger.info("SyncEngine started (mode=%s)", self._mode)

    def stop(self) -> None:
        """Graceful shutdown."""
        self._connectivity.stop()
        self._checkpoint.prune()
        self._ledger.purge_synced()
        logger.info("SyncEngine stopped")

    # ------------------------------------------------------------------
    # Main entry point — called from the main loop
    # ------------------------------------------------------------------

    def process_pending(self) -> bool:
        """Process one batch of pending records.

        Returns True if records were synced, False otherwise.
        This is the **drop-in replacement** for the old
        ``get_pending → send → mark_sent`` pattern.
        """
        # Scheduling gate
        if not self._should_sync():
            return False

        # Connectivity gate
        if not self._connectivity.can_sync():
            if self._state != SyncEngineState.PAUSED:
                self._state = SyncEngineState.PAUSED
                self._health.state = self._state.value
                logger.debug("Sync paused: no connectivity")
            return False

        # Backoff gate
        if time.time() < self._backoff_until:
            return False

        # Register any new captures in the ledger
        self._register_new_captures()

        # Fetch pending records (priority-ordered)
        pending = self._ledger.get_pending(limit=self._current_batch_size)
        if not pending:
            self._state = SyncEngineState.IDLE
            self._health.state = self._state.value
            return False

        # Execute sync
        self._state = SyncEngineState.SYNCING
        self._health.state = self._state.value
        batch_id = f"batch_{uuid4().hex[:12]}"

        try:
            success = self._sync_batch(batch_id, pending)
        except Exception as exc:
            logger.error("Sync batch %s failed with exception: %s", batch_id, exc)
            self._record_failure(batch_id, str(exc))
            return False

        if success:
            self._record_success(batch_id, len(pending))
            return True
        else:
            return False

    # ------------------------------------------------------------------
    # Core sync logic
    # ------------------------------------------------------------------

    def _sync_batch(self, batch_id: str, records: list[dict[str, Any]]) -> bool:
        """Send a batch of records through the transport.

        Returns True on success.
        """
        ledger_ids = [r["id"] for r in records]

        # 1. Mark QUEUED in ledger
        self._ledger.mark_queued(ledger_ids, batch_id)

        # 2. Build the batch items (compatible with existing _build_report_bundle)
        batch_items = []
        for r in records:
            batch_items.append({
                "type": r.get("type", "unknown"),
                "data": r.get("data", ""),
                "file_path": r.get("file_path", ""),
                "file_size": r.get("file_size", 0),
                "timestamp": r.get("capture_ts", time.time()),
                "id": r.get("capture_id"),
            })

        # 3. Create checkpoint
        total_bytes = sum(len(str(item.get("data", ""))) for item in batch_items)
        payload_for_hash = json.dumps(batch_items, sort_keys=True, default=str)
        content_digest = hashlib.sha256(payload_for_hash.encode()).hexdigest()

        self._checkpoint.create(
            batch_id=batch_id,
            record_ids=ledger_ids,
            total_bytes=total_bytes,
            content_digest=content_digest,
        )

        # 4. Mark IN_FLIGHT
        self._ledger.mark_in_flight(batch_id)
        self._checkpoint.mark_sending(batch_id)

        # 5. Build payload using the existing bundle builder or simple JSON
        start_time = time.monotonic()

        if self._build_payload:
            payload, metadata, file_paths = self._build_payload(
                batch_items, self._config, self._sys_info
            )
            if self._apply_encryption:
                data_dir = self._config.get("data_dir", "./data")
                payload, metadata = self._apply_encryption(
                    payload, metadata, self._config, data_dir,
                    e2e_protocol=self._e2e_protocol,
                )
        else:
            # Standalone mode: simple JSON payload
            payload = json.dumps(batch_items, default=str).encode("utf-8")
            metadata = {"content_type": "application/json", "batch_id": batch_id}
            file_paths = []

        # 6. Compress if enabled and worthwhile
        if self._compression and len(payload) > self._compress_threshold:
            compressed = zlib.compress(payload, level=6)
            if len(compressed) < len(payload) * 0.9:
                payload = compressed
                metadata["compression"] = "zlib"

        # 7. Add integrity digest
        if self._integrity_check:
            metadata["content_digest"] = hashlib.sha256(payload).hexdigest()
            metadata["batch_id"] = batch_id

        # 8. Send via transport
        try:
            success = self._transport.send(payload, metadata)
        except Exception as exc:
            logger.error("Transport send failed: %s", exc)
            success = False

        elapsed = time.monotonic() - start_time
        elapsed_ms = elapsed * 1000

        # 9. Record outcome
        if success:
            synced = self._ledger.mark_synced(batch_id)
            self._checkpoint.mark_completed(batch_id)
            self._connectivity.record_send(len(payload), elapsed)

            # Track metrics
            self._latency_window.append(elapsed_ms)
            self._throughput_window.append(len(payload) / elapsed if elapsed > 0 else 0)
            self._success_window.append(True)

            logger.info(
                "Batch %s synced: %d records, %d bytes in %.0fms",
                batch_id, synced, len(payload), elapsed_ms,
            )

            # Clean up associated files
            if file_paths:
                _cleanup_files(file_paths)

            return True
        else:
            error = "Transport send returned False"
            self._ledger.mark_failed(batch_id, error)
            self._checkpoint.mark_failed(batch_id, error)
            self._success_window.append(False)
            self._record_failure(batch_id, error)
            return False

    # ------------------------------------------------------------------
    # Registration — bridge between SQLite captures and the ledger
    # ------------------------------------------------------------------

    def _register_new_captures(self) -> None:
        """Register untracked captures from the captures table into the ledger."""
        try:
            pending = self._store.get_pending(limit=200)
            if pending:
                registered = self._ledger.register_batch(pending)
                if registered > 0:
                    logger.debug("Registered %d new captures in sync ledger", registered)
        except Exception as exc:
            logger.warning("Failed to register new captures: %s", exc)

    # ------------------------------------------------------------------
    # Scheduling
    # ------------------------------------------------------------------

    def _should_sync(self) -> bool:
        """Check if the engine should attempt a sync this cycle."""
        if self._mode == "manual":
            return False  # only triggered by explicit call to force_sync()
        if self._mode == "immediate":
            return True
        if self._mode == "interval":
            return time.time() - self._last_sync_time >= self._interval
        return True  # default to immediate

    def force_sync(self) -> bool:
        """Trigger a sync regardless of scheduling mode.

        Useful for fleet commands like "sync now".
        """
        old_mode = self._mode
        self._mode = "immediate"
        self._backoff_until = 0  # clear any backoff
        result = self.process_pending()
        self._mode = old_mode
        return result

    # ------------------------------------------------------------------
    # Adaptive batch sizing
    # ------------------------------------------------------------------

    def _grow_batch(self) -> None:
        """Increase batch size after success (up to max)."""
        new = min(self._current_batch_size + max(self._current_batch_size // 4, 1), self._max_batch)
        if new != self._current_batch_size:
            self._current_batch_size = new
            logger.debug("Batch size grown to %d", self._current_batch_size)

    def _shrink_batch(self) -> None:
        """Halve batch size after failure (down to min)."""
        new = max(self._current_batch_size // 2, self._min_batch)
        if new != self._current_batch_size:
            self._current_batch_size = new
            logger.debug("Batch size shrunk to %d", self._current_batch_size)

    # ------------------------------------------------------------------
    # Success / failure tracking
    # ------------------------------------------------------------------

    def _record_success(self, batch_id: str, count: int) -> None:
        self._consecutive_failures = 0
        self._backoff_until = 0
        self._last_sync_time = time.time()
        self._state = SyncEngineState.IDLE

        self._health.total_synced += count
        self._health.consecutive_failures = 0
        self._health.last_sync_at = self._last_sync_time
        self._health.last_error = ""
        self._grow_batch()
        self._update_health()

    def _record_failure(self, batch_id: str, error: str) -> None:
        self._consecutive_failures += 1
        self._shrink_batch()

        # Exponential backoff
        delay = min(
            self._backoff_base ** self._consecutive_failures,
            self._backoff_max,
        )
        self._backoff_until = time.time() + delay

        self._health.total_failed += 1
        self._health.consecutive_failures = self._consecutive_failures
        self._health.last_error = error

        if self._consecutive_failures >= 5:
            self._state = SyncEngineState.ERROR
            logger.warning(
                "SyncEngine entering ERROR state after %d failures (backoff %.0fs)",
                self._consecutive_failures, delay,
            )
        else:
            self._state = SyncEngineState.PAUSED

        self._health.state = self._state.value
        self._update_health()

    def _on_connectivity_change(self, status: ConnectionStatus) -> None:
        """Callback from ConnectivityMonitor on network transitions."""
        if status.online and self._state == SyncEngineState.PAUSED:
            logger.info("Connectivity restored — resuming sync")
            self._state = SyncEngineState.IDLE
            self._backoff_until = 0  # clear backoff on reconnect
            self._health.state = self._state.value

    # ------------------------------------------------------------------
    # Health metrics
    # ------------------------------------------------------------------

    def _update_health(self) -> None:
        """Recompute rolling health metrics."""
        h = self._health
        h.current_batch_size = self._current_batch_size

        if self._success_window:
            h.success_rate = sum(1 for s in self._success_window if s) / len(self._success_window)
        if self._latency_window:
            h.avg_latency_ms = sum(self._latency_window) / len(self._latency_window)
        if self._throughput_window:
            h.throughput_bps = sum(self._throughput_window) / len(self._throughput_window)

        # Queue depth from ledger
        try:
            stats = self._ledger.get_stats()
            h.queue_depth = (
                stats.get(SyncState.PENDING.value, 0)
                + stats.get(SyncState.FAILED.value, 0)
            )
            h.oldest_unsynced_age = stats.get("oldest_unsynced_age", 0.0)
        except Exception:
            pass

    def get_health(self) -> SyncHealth:
        """Return current health metrics (for dashboard / heartbeat)."""
        self._update_health()
        return self._health

    def get_status(self) -> dict[str, Any]:
        """Return comprehensive status dict."""
        self._update_health()
        return {
            "engine": self._health.to_dict(),
            "connectivity": self._connectivity.status.to_dict(),
            "checkpoint": self._checkpoint.get_progress(),
            "ledger": self._ledger.get_stats(),
            "conflict": self._conflict.get_stats(),
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cleanup_files(file_paths: list[str]) -> None:
    """Remove temporary files after successful sync."""
    from pathlib import Path

    for fp in file_paths:
        try:
            p = Path(fp)
            if p.exists():
                p.unlink()
        except Exception:
            pass
