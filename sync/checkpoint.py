"""
Checkpoint Manager — resumable transfers with crash recovery.

Before sending a batch, the engine writes a checkpoint describing the
batch manifest (record IDs, total size, content digest).  If the process
crashes mid-send, the next startup recovers incomplete checkpoints and
re-queues the unfinished records.

Checkpoint lifecycle::

    CREATED  →  SENDING  →  COMPLETED
                   ↓
               FAILED  (records returned to ledger for retry)

Storage: ``sync_checkpoints`` table in the same SQLite database.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class CheckpointState(str, Enum):
    CREATED = "CREATED"
    SENDING = "SENDING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class CheckpointManager:
    """Manage per-batch checkpoints for resumable syncing.

    Config keys (under ``sync.checkpoint``):
      * ``enabled`` — master toggle (default True)
      * ``retention_hours`` — how long to keep completed checkpoints (default 24)
    """

    def __init__(
        self,
        conn: sqlite3.Connection,
        config: dict[str, Any] | None = None,
    ) -> None:
        cfg = (config or {}).get("sync", {}).get("checkpoint", {})
        self._enabled = bool(cfg.get("enabled", True))
        self._retention_hours = int(cfg.get("retention_hours", 24))
        self._conn = conn
        self._lock = threading.Lock()
        self._create_tables()

        # In-memory progress tracking for the current batch
        self._current_batch_id: str | None = None
        self._current_total: int = 0
        self._current_synced: int = 0

    def _create_tables(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS sync_checkpoints (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                batch_id    TEXT    NOT NULL UNIQUE,
                state       TEXT    NOT NULL DEFAULT 'CREATED',
                record_ids  TEXT    NOT NULL,
                total_count INTEGER NOT NULL,
                total_bytes INTEGER DEFAULT 0,
                content_digest TEXT,
                synced_ids  TEXT,
                error       TEXT,
                created_at  REAL    NOT NULL,
                completed_at REAL
            );
            CREATE INDEX IF NOT EXISTS idx_cp_state
                ON sync_checkpoints(state);
            CREATE INDEX IF NOT EXISTS idx_cp_batch_id
                ON sync_checkpoints(batch_id);
        """)
        self._conn.commit()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def create(
        self,
        batch_id: str,
        record_ids: list[int],
        total_bytes: int = 0,
        content_digest: str = "",
    ) -> None:
        """Create a checkpoint before sending a batch."""
        if not self._enabled:
            return
        now = time.time()
        ids_json = json.dumps(record_ids)
        with self._lock:
            self._conn.execute(
                """INSERT OR REPLACE INTO sync_checkpoints
                   (batch_id, state, record_ids, total_count, total_bytes,
                    content_digest, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (batch_id, CheckpointState.CREATED.value, ids_json,
                 len(record_ids), total_bytes, content_digest, now),
            )
            self._conn.commit()

        self._current_batch_id = batch_id
        self._current_total = len(record_ids)
        self._current_synced = 0

    def mark_sending(self, batch_id: str) -> None:
        """Transition checkpoint to SENDING state."""
        if not self._enabled:
            return
        with self._lock:
            self._conn.execute(
                "UPDATE sync_checkpoints SET state = ? WHERE batch_id = ?",
                (CheckpointState.SENDING.value, batch_id),
            )
            self._conn.commit()

    def mark_completed(self, batch_id: str) -> None:
        """Transition checkpoint to COMPLETED state."""
        if not self._enabled:
            return
        now = time.time()
        with self._lock:
            self._conn.execute(
                "UPDATE sync_checkpoints SET state = ?, completed_at = ? WHERE batch_id = ?",
                (CheckpointState.COMPLETED.value, now, batch_id),
            )
            self._conn.commit()

        if batch_id == self._current_batch_id:
            self._current_synced = self._current_total
            self._current_batch_id = None

    def mark_failed(self, batch_id: str, error: str, synced_ids: list[int] | None = None) -> None:
        """Transition checkpoint to FAILED, optionally recording partial success."""
        if not self._enabled:
            return
        now = time.time()
        synced_json = json.dumps(synced_ids) if synced_ids else None
        with self._lock:
            self._conn.execute(
                "UPDATE sync_checkpoints SET state = ?, error = ?, "
                "synced_ids = ?, completed_at = ? WHERE batch_id = ?",
                (CheckpointState.FAILED.value, error, synced_json, now, batch_id),
            )
            self._conn.commit()

        if batch_id == self._current_batch_id:
            self._current_synced = len(synced_ids) if synced_ids else 0
            self._current_batch_id = None

    # ------------------------------------------------------------------
    # Crash recovery
    # ------------------------------------------------------------------

    def recover(self) -> list[dict[str, Any]]:
        """Scan for incomplete checkpoints (CREATED or SENDING) from a previous
        run and return their record ID lists so the sync engine can re-queue them.

        Returns a list of dicts: ``[{"batch_id": ..., "record_ids": [...], "state": ...}]``
        """
        if not self._enabled:
            return []
        with self._lock:
            rows = self._conn.execute(
                "SELECT batch_id, record_ids, synced_ids, state FROM sync_checkpoints "
                "WHERE state IN (?, ?)",
                (CheckpointState.CREATED.value, CheckpointState.SENDING.value),
            ).fetchall()

        recovered = []
        for row in rows:
            record_ids = json.loads(row["record_ids"])
            synced_ids = json.loads(row["synced_ids"]) if row["synced_ids"] else []
            # Only return IDs that weren't synced yet
            remaining = [rid for rid in record_ids if rid not in synced_ids]
            if remaining:
                recovered.append({
                    "batch_id": row["batch_id"],
                    "record_ids": remaining,
                    "state": row["state"],
                })

        if recovered:
            logger.info("Recovered %d incomplete checkpoints from previous run", len(recovered))
            # Mark them as FAILED so the ledger can re-queue
            with self._lock:
                self._conn.execute(
                    "UPDATE sync_checkpoints SET state = ?, error = ? "
                    "WHERE state IN (?, ?)",
                    (CheckpointState.FAILED.value, "recovered_after_crash",
                     CheckpointState.CREATED.value, CheckpointState.SENDING.value),
                )
                self._conn.commit()

        return recovered

    # ------------------------------------------------------------------
    # Progress reporting
    # ------------------------------------------------------------------

    def get_progress(self) -> dict[str, Any]:
        """Return current batch progress (for dashboard display)."""
        return {
            "batch_id": self._current_batch_id,
            "total": self._current_total,
            "synced": self._current_synced,
            "percent": (
                round(self._current_synced / self._current_total * 100, 1)
                if self._current_total > 0 else 0.0
            ),
            "active": self._current_batch_id is not None,
        }

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def prune(self) -> int:
        """Delete completed/failed checkpoints older than retention period."""
        cutoff = time.time() - self._retention_hours * 3600
        with self._lock:
            cursor = self._conn.execute(
                "DELETE FROM sync_checkpoints WHERE state IN (?, ?) AND completed_at < ?",
                (CheckpointState.COMPLETED.value, CheckpointState.FAILED.value, cutoff),
            )
            self._conn.commit()
            return cursor.rowcount
