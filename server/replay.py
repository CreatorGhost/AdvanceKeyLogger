"""
Replay protection for envelopes — with optional SQLite persistence.

The in-memory cache provides fast lookups. When ``db_path`` is provided,
seen IDs and sequence numbers are also persisted to SQLite so they survive
server restarts.

Usage::

    cache = ReplayCache(ttl_seconds=3600, db_path="./server_data/replay.db")
    if cache.seen("envelope-id-123"):
        reject_as_replay()
"""
from __future__ import annotations

import logging
import sqlite3
import threading
import time
from pathlib import Path

logger = logging.getLogger(__name__)


class ReplayCache:
    """Replay detection with optional disk persistence.

    Parameters
    ----------
    ttl_seconds : int
        How long to remember envelope IDs (default 1 hour).
    max_entries : int
        Maximum in-memory cache size.
    db_path : str or None
        Path to SQLite persistence file. None = in-memory only.
    """

    def __init__(
        self,
        ttl_seconds: int = 3600,
        max_entries: int = 10000,
        db_path: str | None = None,
    ) -> None:
        self._ttl = ttl_seconds
        self._max_entries = max_entries
        self._seen: dict[str, float] = {}
        self._lock = threading.Lock()

        # SQLite persistence
        self._db: sqlite3.Connection | None = None
        if db_path:
            try:
                path = Path(db_path)
                path.parent.mkdir(parents=True, exist_ok=True)
                self._db = sqlite3.connect(str(path), check_same_thread=False)
                self._db.execute("PRAGMA journal_mode=WAL")
                self._db.execute("""
                    CREATE TABLE IF NOT EXISTS replay_cache (
                        envelope_id TEXT PRIMARY KEY,
                        seen_at REAL NOT NULL
                    )
                """)
                self._db.execute("""
                    CREATE TABLE IF NOT EXISTS sequence_tracker (
                        sender_key TEXT PRIMARY KEY,
                        last_sequence INTEGER NOT NULL
                    )
                """)
                self._db.commit()
                # Load persisted entries into memory
                self._load_from_db()
                logger.info("Replay cache persistence enabled: %s", path)
            except Exception as exc:
                logger.warning("Replay cache DB init failed (in-memory only): %s", exc)
                self._db = None

    def seen(self, envelope_id: str) -> bool:
        """Check if an envelope ID has been seen before. Records it if not."""
        now = time.time()
        with self._lock:
            self._purge(now)
            if envelope_id in self._seen:
                return True
            if len(self._seen) >= self._max_entries:
                self._purge(now, force=True)
            self._seen[envelope_id] = now
            self._persist_id(envelope_id, now)
            return False

    def get_last_sequence(self, sender_key: str) -> int | None:
        """Get the last known sequence number for a sender."""
        if self._db is None:
            return None
        try:
            cursor = self._db.execute(
                "SELECT last_sequence FROM sequence_tracker WHERE sender_key = ?",
                (sender_key,),
            )
            row = cursor.fetchone()
            return row[0] if row else None
        except Exception:
            return None

    def update_sequence(self, sender_key: str, sequence: int) -> None:
        """Update the last sequence number for a sender (persisted)."""
        if self._db is None:
            return
        try:
            self._db.execute(
                "INSERT OR REPLACE INTO sequence_tracker (sender_key, last_sequence) "
                "VALUES (?, ?)",
                (sender_key, sequence),
            )
            self._db.commit()
        except Exception as exc:
            logger.debug("Failed to persist sequence: %s", exc)

    def close(self) -> None:
        if self._db:
            try:
                self._db.close()
            except Exception:
                pass
            self._db = None

    # ── Internal ─────────────────────────────────────────────────

    def _purge(self, now: float, force: bool = False) -> None:
        if not self._seen:
            return
        cutoff = now - self._ttl
        to_delete = [k for k, ts in self._seen.items() if ts < cutoff]
        for key in to_delete:
            self._seen.pop(key, None)
        if force and self._seen:
            sorted_items = sorted(self._seen.items(), key=lambda item: item[1])
            for key, _ in sorted_items[: max(1, len(sorted_items) // 3)]:
                self._seen.pop(key, None)

        # Also purge from DB
        if self._db and to_delete:
            try:
                self._db.executemany(
                    "DELETE FROM replay_cache WHERE envelope_id = ?",
                    [(k,) for k in to_delete],
                )
                self._db.commit()
            except Exception:
                pass

    def _persist_id(self, envelope_id: str, seen_at: float) -> None:
        if self._db is None:
            return
        try:
            self._db.execute(
                "INSERT OR IGNORE INTO replay_cache (envelope_id, seen_at) VALUES (?, ?)",
                (envelope_id, seen_at),
            )
            self._db.commit()
        except Exception:
            pass

    def _load_from_db(self) -> None:
        """Load unexpired entries from SQLite into memory on startup."""
        if self._db is None:
            return
        try:
            cutoff = time.time() - self._ttl
            # Clean expired entries
            self._db.execute("DELETE FROM replay_cache WHERE seen_at < ?", (cutoff,))
            self._db.commit()
            # Load remaining
            cursor = self._db.execute("SELECT envelope_id, seen_at FROM replay_cache")
            for row in cursor.fetchall():
                self._seen[row[0]] = row[1]
            logger.debug("Loaded %d replay cache entries from disk", len(self._seen))
        except Exception as exc:
            logger.debug("Failed to load replay cache from disk: %s", exc)
