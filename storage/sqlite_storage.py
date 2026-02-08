"""
SQLite-based structured storage for capture metadata.

Stores capture records (type, data, file path, timestamps) in a
queryable SQLite database. Useful for keystroke logs and metadata.

Usage:
    from storage.sqlite_storage import SQLiteStorage

    db = SQLiteStorage("./data/captures.db")
    row_id = db.insert("keystroke", data="hello world")
    pending = db.get_pending(limit=50)
    db.mark_sent([r["id"] for r in pending])
    db.close()
"""
from __future__ import annotations

import json
import sqlite3
import time
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class SQLiteStorage:
    """Store capture metadata and small data blobs in SQLite."""

    def __init__(self, db_path: str = "./data/captures.db") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")  # Better concurrent access
        self._create_tables()
        logger.info("SQLite storage initialized: %s", self.db_path)

    def _create_tables(self) -> None:
        """Create tables and indexes if they don't exist."""
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS captures (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT NOT NULL,
                data TEXT DEFAULT '',
                file_path TEXT DEFAULT '',
                file_size INTEGER DEFAULT 0,
                timestamp REAL NOT NULL,
                sent INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS biometrics_profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                profile_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                sample_size INTEGER NOT NULL,
                avg_dwell_ms REAL NOT NULL,
                avg_flight_ms REAL NOT NULL,
                error_rate REAL NOT NULL,
                profile_json TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_captures_sent
                ON captures(sent);

            CREATE INDEX IF NOT EXISTS idx_captures_timestamp
                ON captures(timestamp);

            CREATE INDEX IF NOT EXISTS idx_captures_type
                ON captures(type);

            CREATE INDEX IF NOT EXISTS idx_profiles_created_at
                ON biometrics_profiles(created_at);
        """)
        self._conn.commit()

    def insert(
        self,
        capture_type: str,
        data: str = "",
        file_path: str = "",
        file_size: int = 0,
    ) -> int:
        """
        Insert a capture record.

        Args:
            capture_type: Type of capture (e.g. "keystroke", "screenshot").
            data: Text data (keystrokes, window names, etc.).
            file_path: Path to associated file (screenshots, etc.).
            file_size: Size of associated file in bytes.

        Returns:
            The row ID of the inserted record.
        """
        cursor = self._conn.execute(
            "INSERT INTO captures (type, data, file_path, file_size, timestamp) "
            "VALUES (?, ?, ?, ?, ?)",
            (capture_type, data, file_path, file_size, time.time()),
        )
        self._conn.commit()
        return cursor.lastrowid

    def get_pending(self, limit: int = 50) -> list[dict]:
        """
        Get unsent captures, oldest first.

        Args:
            limit: Maximum number of records to return.

        Returns:
            List of dicts with keys: id, type, data, file_path, timestamp.
        """
        cursor = self._conn.execute(
            "SELECT id, type, data, file_path, file_size, timestamp "
            "FROM captures WHERE sent = 0 "
            "ORDER BY timestamp ASC LIMIT ?",
            (limit,),
        )
        columns = ["id", "type", "data", "file_path", "file_size", "timestamp"]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def mark_sent(self, ids: list[int]) -> None:
        """Mark captures as successfully sent."""
        if not ids:
            return
        placeholders = ",".join("?" * len(ids))
        self._conn.execute(
            f"UPDATE captures SET sent = 1 WHERE id IN ({placeholders})",
            ids,
        )
        self._conn.commit()
        logger.debug("Marked %d records as sent", len(ids))

    def count_pending(self) -> int:
        """Count unsent captures."""
        cursor = self._conn.execute("SELECT COUNT(*) FROM captures WHERE sent = 0")
        return cursor.fetchone()[0]

    def count_total(self) -> int:
        """Count all captures."""
        cursor = self._conn.execute("SELECT COUNT(*) FROM captures")
        return cursor.fetchone()[0]

    def purge_sent(self, older_than_seconds: int = 86400) -> int:
        """
        Delete sent records older than a given age.

        Args:
            older_than_seconds: Delete records older than this (default 24h).

        Returns:
            Number of records deleted.
        """
        cutoff = time.time() - older_than_seconds
        cursor = self._conn.execute(
            "DELETE FROM captures WHERE sent = 1 AND timestamp < ?",
            (cutoff,),
        )
        self._conn.commit()
        deleted = cursor.rowcount
        if deleted:
            logger.info("Purged %d sent records older than %ds", deleted, older_than_seconds)
        return deleted

    def insert_profile(self, profile: dict) -> int:
        """
        Insert a biometrics profile.

        Args:
            profile: Biometrics profile dict (see biometrics.models.BiometricsProfile.to_dict).

        Returns:
            The row ID of the inserted profile.
        """
        cursor = self._conn.execute(
            "INSERT INTO biometrics_profiles "
            "(profile_id, created_at, sample_size, avg_dwell_ms, avg_flight_ms, error_rate, profile_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                profile.get("profile_id", ""),
                profile.get("created_at", ""),
                int(profile.get("sample_size", 0)),
                float(profile.get("avg_dwell_ms", 0.0)),
                float(profile.get("avg_flight_ms", 0.0)),
                float(profile.get("error_rate", 0.0)),
                json.dumps(profile),
            ),
        )
        self._conn.commit()
        return cursor.lastrowid

    def get_latest_profile(self) -> dict | None:
        """Return the most recently created biometrics profile."""
        cursor = self._conn.execute(
            "SELECT profile_json FROM biometrics_profiles ORDER BY created_at DESC LIMIT 1"
        )
        row = cursor.fetchone()
        if not row:
            return None
        try:
            return json.loads(row[0])
        except Exception:
            return None

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()
        logger.debug("SQLite storage closed")

    def __enter__(self) -> SQLiteStorage:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        self.close()
