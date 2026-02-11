"""
Session Store — SQLite persistence for recording sessions, frames, and events.

Three tables:

* ``sessions`` — one row per recording session (start/stop, metadata)
* ``session_frames`` — screenshot frames with file paths and offsets
* ``session_events`` — keyboard, mouse, and window events with timestamps

All timestamps are stored as offsets (seconds) from the session start time
so the replay player can seek by relative position.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)


class SessionStore:
    """SQLite storage for session recordings.

    Uses the same database file as the main captures DB (or a dedicated one).
    Creates its own tables on first use.
    """

    def __init__(self, db_path: str = "./data/sessions.db") -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._lock = threading.Lock()
        self._create_tables()
        logger.info("SessionStore initialized: %s", self._db_path)

    def _create_tables(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                id          TEXT PRIMARY KEY,
                status      TEXT NOT NULL DEFAULT 'recording',
                started_at  REAL NOT NULL,
                stopped_at  REAL,
                duration    REAL DEFAULT 0,
                frame_count INTEGER DEFAULT 0,
                event_count INTEGER DEFAULT 0,
                thumbnail   TEXT,
                metadata    TEXT DEFAULT '{}',
                tags        TEXT DEFAULT '[]'
            );

            CREATE TABLE IF NOT EXISTS session_frames (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id  TEXT NOT NULL,
                offset_sec  REAL NOT NULL,
                file_path   TEXT NOT NULL,
                file_size   INTEGER DEFAULT 0,
                width       INTEGER DEFAULT 0,
                height      INTEGER DEFAULT 0,
                trigger     TEXT DEFAULT 'event',
                timestamp   REAL NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions(id)
            );

            CREATE TABLE IF NOT EXISTS session_events (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id  TEXT NOT NULL,
                offset_sec  REAL NOT NULL,
                event_type  TEXT NOT NULL,
                data        TEXT NOT NULL DEFAULT '{}',
                timestamp   REAL NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions(id)
            );

            CREATE INDEX IF NOT EXISTS idx_sf_session
                ON session_frames(session_id);
            CREATE INDEX IF NOT EXISTS idx_sf_offset
                ON session_frames(session_id, offset_sec);
            CREATE INDEX IF NOT EXISTS idx_se_session
                ON session_events(session_id);
            CREATE INDEX IF NOT EXISTS idx_se_offset
                ON session_events(session_id, offset_sec);
            CREATE INDEX IF NOT EXISTS idx_sessions_status
                ON sessions(status);
            CREATE INDEX IF NOT EXISTS idx_sessions_started
                ON sessions(started_at);
        """)
        self._conn.commit()

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------

    def create_session(self, metadata: dict[str, Any] | None = None) -> str:
        """Create a new recording session.  Returns the session ID."""
        session_id = uuid4().hex[:12]
        now = time.time()
        with self._lock:
            self._conn.execute(
                "INSERT INTO sessions (id, status, started_at, metadata) VALUES (?, ?, ?, ?)",
                (session_id, "recording", now, json.dumps(metadata or {})),
            )
            self._conn.commit()
        logger.info("Session created: %s", session_id)
        return session_id

    def stop_session(self, session_id: str) -> None:
        """Mark a session as stopped and compute duration/counts."""
        now = time.time()
        with self._lock:
            row = self._conn.execute(
                "SELECT started_at FROM sessions WHERE id = ?", (session_id,)
            ).fetchone()
            if not row:
                return
            duration = now - row["started_at"]
            frame_count = self._conn.execute(
                "SELECT COUNT(*) FROM session_frames WHERE session_id = ?",
                (session_id,),
            ).fetchone()[0]
            event_count = self._conn.execute(
                "SELECT COUNT(*) FROM session_events WHERE session_id = ?",
                (session_id,),
            ).fetchone()[0]

            # Use first frame as thumbnail
            thumb_row = self._conn.execute(
                "SELECT file_path FROM session_frames WHERE session_id = ? "
                "ORDER BY offset_sec ASC LIMIT 1",
                (session_id,),
            ).fetchone()
            thumbnail = thumb_row["file_path"] if thumb_row else None

            self._conn.execute(
                "UPDATE sessions SET status = ?, stopped_at = ?, duration = ?, "
                "frame_count = ?, event_count = ?, thumbnail = ? WHERE id = ?",
                ("stopped", now, duration, frame_count, event_count, thumbnail, session_id),
            )
            self._conn.commit()
        logger.info(
            "Session stopped: %s (%.1fs, %d frames, %d events)",
            session_id, duration, frame_count, event_count,
        )

    def delete_session(self, session_id: str) -> None:
        """Delete a session and all its frames/events."""
        with self._lock:
            # Get frame paths for cleanup
            rows = self._conn.execute(
                "SELECT file_path FROM session_frames WHERE session_id = ?",
                (session_id,),
            ).fetchall()
            for row in rows:
                try:
                    Path(row["file_path"]).unlink(missing_ok=True)
                except Exception:
                    pass
            self._conn.execute("DELETE FROM session_events WHERE session_id = ?", (session_id,))
            self._conn.execute("DELETE FROM session_frames WHERE session_id = ?", (session_id,))
            self._conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            self._conn.commit()

    # ------------------------------------------------------------------
    # Frame operations
    # ------------------------------------------------------------------

    def add_frame(
        self,
        session_id: str,
        offset_sec: float,
        file_path: str,
        file_size: int = 0,
        width: int = 0,
        height: int = 0,
        trigger: str = "event",
    ) -> int:
        """Record a screenshot frame.  Returns the frame row ID."""
        now = time.time()
        with self._lock:
            cursor = self._conn.execute(
                "INSERT INTO session_frames "
                "(session_id, offset_sec, file_path, file_size, width, height, trigger, timestamp) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (session_id, offset_sec, file_path, file_size, width, height, trigger, now),
            )
            self._conn.commit()
            return cursor.lastrowid  # type: ignore[return-value]

    def get_frames(self, session_id: str) -> list[dict[str, Any]]:
        """Return all frames for a session ordered by offset."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM session_frames WHERE session_id = ? ORDER BY offset_sec ASC",
                (session_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Event operations
    # ------------------------------------------------------------------

    def add_event(
        self,
        session_id: str,
        offset_sec: float,
        event_type: str,
        data: dict[str, Any] | str = "",
    ) -> int:
        """Record an input event.  Returns the event row ID."""
        now = time.time()
        data_str = json.dumps(data) if isinstance(data, dict) else str(data)
        with self._lock:
            cursor = self._conn.execute(
                "INSERT INTO session_events "
                "(session_id, offset_sec, event_type, data, timestamp) "
                "VALUES (?, ?, ?, ?, ?)",
                (session_id, offset_sec, event_type, data_str, now),
            )
            self._conn.commit()
            return cursor.lastrowid  # type: ignore[return-value]

    def add_events_batch(self, events: list[tuple[str, float, str, str]]) -> int:
        """Bulk insert events.  Each tuple: (session_id, offset, type, data_json).
        Returns the number inserted."""
        now = time.time()
        with self._lock:
            try:
                self._conn.execute("BEGIN")
                for session_id, offset_sec, event_type, data_str in events:
                    self._conn.execute(
                        "INSERT INTO session_events "
                        "(session_id, offset_sec, event_type, data, timestamp) "
                        "VALUES (?, ?, ?, ?, ?)",
                        (session_id, offset_sec, event_type, data_str, now),
                    )
                self._conn.commit()
                return len(events)
            except Exception:
                self._conn.rollback()
                raise

    def get_events(
        self, session_id: str, event_type: str | None = None
    ) -> list[dict[str, Any]]:
        """Return events for a session, optionally filtered by type."""
        params: list[Any] = [session_id]
        sql = "SELECT * FROM session_events WHERE session_id = ?"
        if event_type:
            sql += " AND event_type = ?"
            params.append(event_type)
        sql += " ORDER BY offset_sec ASC"
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Session queries
    # ------------------------------------------------------------------

    def list_sessions(
        self, limit: int = 50, status: str | None = None
    ) -> list[dict[str, Any]]:
        """Return recent sessions, newest first."""
        params: list[Any] = []
        sql = "SELECT * FROM sessions"
        if status:
            sql += " WHERE status = ?"
            params.append(status)
        sql += " ORDER BY started_at DESC LIMIT ?"
        params.append(limit)
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        """Return a single session by ID."""
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM sessions WHERE id = ?", (session_id,)
            ).fetchone()
        return dict(row) if row else None

    def get_timeline(self, session_id: str) -> dict[str, Any]:
        """Return the full timeline data for replay: session + frames + events."""
        session = self.get_session(session_id)
        if not session:
            return {}
        frames = self.get_frames(session_id)
        events = self.get_events(session_id)
        return {
            "session": session,
            "frames": frames,
            "events": events,
        }

    def get_stats(self) -> dict[str, Any]:
        """Return aggregate statistics."""
        with self._lock:
            total = self._conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
            recording = self._conn.execute(
                "SELECT COUNT(*) FROM sessions WHERE status = 'recording'"
            ).fetchone()[0]
            total_frames = self._conn.execute("SELECT COUNT(*) FROM session_frames").fetchone()[0]
            total_events = self._conn.execute("SELECT COUNT(*) FROM session_events").fetchone()[0]
        return {
            "total_sessions": total,
            "recording": recording,
            "total_frames": total_frames,
            "total_events": total_events,
        }

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def purge_old(self, older_than_seconds: int = 604800) -> int:
        """Delete stopped sessions older than the given age (default 7 days)."""
        cutoff = time.time() - older_than_seconds
        with self._lock:
            rows = self._conn.execute(
                "SELECT id FROM sessions WHERE status = 'stopped' AND stopped_at < ?",
                (cutoff,),
            ).fetchall()
        deleted = 0
        for row in rows:
            self.delete_session(row["id"])
            deleted += 1
        return deleted

    def close(self) -> None:
        self._conn.close()
