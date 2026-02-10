"""
Conflict Resolver — pluggable strategies for bidirectional sync conflicts.

When the server responds with conflicting data (e.g. a config value was
changed both locally and remotely), the resolver decides which version
to keep based on the active strategy.

Built-in strategies:
  * ``LastWriterWins`` — compare timestamps, newest wins (default)
  * ``ServerWins`` — always accept the server version
  * ``ClientWins`` — always keep the local version
  * ``MergeFields`` — field-level merge for dict-like records

All conflicts are journaled in a ``sync_conflicts`` SQLite table for
audit and optional manual review.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Strategy interface
# ---------------------------------------------------------------------------

class ConflictStrategy(ABC):
    """Base class for conflict resolution strategies."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique strategy name (used in config and journal)."""

    @abstractmethod
    def resolve(
        self,
        local: dict[str, Any],
        remote: dict[str, Any],
    ) -> dict[str, Any]:
        """Return the winning version.

        May return a new merged dict (for merge strategies).
        """


# ---------------------------------------------------------------------------
# Built-in strategies
# ---------------------------------------------------------------------------

class LastWriterWins(ConflictStrategy):
    """Compare ``timestamp`` fields; newest wins."""

    @property
    def name(self) -> str:
        return "last_writer_wins"

    def resolve(self, local: dict[str, Any], remote: dict[str, Any]) -> dict[str, Any]:
        local_ts = float(local.get("timestamp", 0))
        remote_ts = float(remote.get("timestamp", 0))
        return remote if remote_ts >= local_ts else local


class ServerWins(ConflictStrategy):
    """Always accept the server version."""

    @property
    def name(self) -> str:
        return "server_wins"

    def resolve(self, local: dict[str, Any], remote: dict[str, Any]) -> dict[str, Any]:
        return remote


class ClientWins(ConflictStrategy):
    """Always keep the local version."""

    @property
    def name(self) -> str:
        return "client_wins"

    def resolve(self, local: dict[str, Any], remote: dict[str, Any]) -> dict[str, Any]:
        return local


class MergeFields(ConflictStrategy):
    """Field-level merge: non-conflicting fields are combined.

    For fields present in both versions, the remote value wins.
    """

    @property
    def name(self) -> str:
        return "merge_fields"

    def resolve(self, local: dict[str, Any], remote: dict[str, Any]) -> dict[str, Any]:
        merged = dict(local)
        merged.update(remote)
        # Preserve the newer timestamp
        if "timestamp" in local and "timestamp" in remote:
            merged["timestamp"] = max(
                float(local["timestamp"]), float(remote["timestamp"])
            )
        return merged


# Strategy registry
_STRATEGIES: dict[str, ConflictStrategy] = {
    "last_writer_wins": LastWriterWins(),
    "server_wins": ServerWins(),
    "client_wins": ClientWins(),
    "merge_fields": MergeFields(),
}


def get_strategy(name: str) -> ConflictStrategy:
    """Look up a strategy by name."""
    if name not in _STRATEGIES:
        raise ValueError(
            f"Unknown conflict strategy '{name}'. "
            f"Available: {', '.join(sorted(_STRATEGIES))}"
        )
    return _STRATEGIES[name]


def register_strategy(strategy: ConflictStrategy) -> None:
    """Register a custom strategy (for plugins)."""
    _STRATEGIES[strategy.name] = strategy


# ---------------------------------------------------------------------------
# Conflict Resolver
# ---------------------------------------------------------------------------

class ConflictResolver:
    """Resolve conflicts and journal outcomes.

    Config keys (under ``sync.conflict``):
      * ``default_strategy`` — name of the default strategy (default ``last_writer_wins``)
      * ``auto_resolve_captures`` — auto-resolve append-only capture conflicts (default True)
      * ``queue_config_conflicts`` — queue mutable-data conflicts for manual review (default True)
    """

    def __init__(
        self,
        conn: sqlite3.Connection,
        config: dict[str, Any] | None = None,
    ) -> None:
        cfg = (config or {}).get("sync", {}).get("conflict", {})
        self._default_strategy_name = cfg.get("default_strategy", "last_writer_wins")
        self._auto_captures = bool(cfg.get("auto_resolve_captures", True))
        self._queue_configs = bool(cfg.get("queue_config_conflicts", True))

        self._conn = conn
        self._lock = threading.Lock()
        self._create_tables()

    def _create_tables(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS sync_conflicts (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                record_type     TEXT NOT NULL,
                record_id       TEXT,
                local_data      TEXT NOT NULL,
                remote_data     TEXT NOT NULL,
                resolved_data   TEXT,
                strategy_used   TEXT,
                auto_resolved   INTEGER DEFAULT 0,
                resolution_status TEXT DEFAULT 'PENDING',
                created_at      REAL NOT NULL,
                resolved_at     REAL
            );
            CREATE INDEX IF NOT EXISTS idx_sc_status
                ON sync_conflicts(resolution_status);
        """)
        self._conn.commit()

    # ------------------------------------------------------------------
    # Resolution
    # ------------------------------------------------------------------

    def resolve(
        self,
        local: dict[str, Any],
        remote: dict[str, Any],
        record_type: str = "capture",
        record_id: str = "",
        strategy_name: str | None = None,
    ) -> dict[str, Any]:
        """Resolve a conflict between local and remote versions.

        Returns the winning version and journals the outcome.
        """
        # Content-hash dedup: if both versions are identical, no conflict
        if _content_equal(local, remote):
            return local

        # Decide strategy
        sname = strategy_name or self._default_strategy_name
        strategy = get_strategy(sname)

        # Auto-resolve captures, queue configs for review
        auto = True
        if record_type in ("config", "profile") and self._queue_configs:
            auto = False
        if record_type == "capture" and self._auto_captures:
            auto = True

        result = strategy.resolve(local, remote)
        status = "RESOLVED" if auto else "PENDING_REVIEW"

        # Journal the conflict
        self._journal(
            record_type=record_type,
            record_id=record_id,
            local=local,
            remote=remote,
            resolved=result if auto else None,
            strategy=sname,
            auto=auto,
            status=status,
        )

        if not auto:
            logger.info(
                "Conflict queued for manual review: %s/%s (strategy=%s)",
                record_type, record_id, sname,
            )
            # For un-auto-resolved conflicts, return local (preserve current state)
            return local

        logger.debug(
            "Conflict auto-resolved: %s/%s (strategy=%s)", record_type, record_id, sname
        )
        return result

    def resolve_manual(self, conflict_id: int, chosen_data: dict[str, Any]) -> None:
        """Manually resolve a queued conflict."""
        now = time.time()
        with self._lock:
            self._conn.execute(
                "UPDATE sync_conflicts SET resolved_data = ?, resolution_status = ?, "
                "resolved_at = ? WHERE id = ?",
                (json.dumps(chosen_data), "RESOLVED", now, conflict_id),
            )
            self._conn.commit()

    def rollback(self, conflict_id: int) -> dict[str, Any] | None:
        """Rollback a resolution by returning the local (pre-resolution) data."""
        with self._lock:
            row = self._conn.execute(
                "SELECT local_data FROM sync_conflicts WHERE id = ?", (conflict_id,)
            ).fetchone()
        if not row:
            return None
        return json.loads(row["local_data"])

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_pending_reviews(self, limit: int = 50) -> list[dict[str, Any]]:
        """Return conflicts pending manual review."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM sync_conflicts WHERE resolution_status = 'PENDING_REVIEW' "
                "ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_journal(self, limit: int = 100) -> list[dict[str, Any]]:
        """Return recent conflict journal entries."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM sync_conflicts ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_stats(self) -> dict[str, int]:
        """Return counts by resolution status."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT resolution_status, COUNT(*) as cnt "
                "FROM sync_conflicts GROUP BY resolution_status"
            ).fetchall()
        return {r["resolution_status"]: r["cnt"] for r in rows}

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _journal(
        self,
        record_type: str,
        record_id: str,
        local: dict[str, Any],
        remote: dict[str, Any],
        resolved: dict[str, Any] | None,
        strategy: str,
        auto: bool,
        status: str,
    ) -> None:
        now = time.time()
        with self._lock:
            self._conn.execute(
                """INSERT INTO sync_conflicts
                   (record_type, record_id, local_data, remote_data, resolved_data,
                    strategy_used, auto_resolved, resolution_status, created_at, resolved_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    record_type,
                    record_id,
                    json.dumps(local),
                    json.dumps(remote),
                    json.dumps(resolved) if resolved else None,
                    strategy,
                    1 if auto else 0,
                    status,
                    now,
                    now if auto else None,
                ),
            )
            self._conn.commit()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _content_equal(a: dict[str, Any], b: dict[str, Any]) -> bool:
    """Check if two records are semantically identical (ignoring metadata)."""
    # Compare the serialised data — fast and handles nested structures
    try:
        return json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    except (TypeError, ValueError):
        return a == b
