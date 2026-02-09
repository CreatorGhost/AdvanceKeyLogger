"""
SQLite-based storage for fleet management (agents, commands, configs).
"""

from __future__ import annotations

import json
import sqlite3
import time
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class FleetStorage:
    """Store fleet state, commands, and telemetry in SQLite."""

    def __init__(self, db_path: str = "./data/fleet.db") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row  # Return dict-like rows
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._create_tables()
        logger.info("Fleet storage initialized: %s", self.db_path)

    def _create_tables(self) -> None:
        """Create fleet tables if they don't exist."""
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS agents (
                id TEXT PRIMARY KEY,
                name TEXT,
                public_key TEXT,
                status TEXT DEFAULT 'offline',
                ip_address TEXT,
                hostname TEXT,
                platform TEXT,
                version TEXT,
                metadata TEXT,  -- JSON
                created_at REAL,
                last_seen_at REAL,
                enrollment_key TEXT
            );

            CREATE TABLE IF NOT EXISTS heartbeats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_id TEXT NOT NULL,
                timestamp REAL NOT NULL,
                metrics TEXT,  -- JSON
                ip_address TEXT,
                FOREIGN KEY(agent_id) REFERENCES agents(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS commands (
                id TEXT PRIMARY KEY,
                agent_id TEXT NOT NULL,
                type TEXT NOT NULL,
                payload TEXT,  -- JSON
                status TEXT DEFAULT 'pending', -- pending, sent, completed, failed
                priority TEXT DEFAULT 'medium',
                created_at REAL,
                sent_at REAL,
                completed_at REAL,
                response TEXT,  -- JSON
                error_message TEXT,
                FOREIGN KEY(agent_id) REFERENCES agents(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS agent_tokens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_id TEXT NOT NULL,
                token_hash TEXT NOT NULL,
                token_jti TEXT UNIQUE NOT NULL,
                issued_at REAL,
                expires_at REAL,
                revoked_at REAL,
                FOREIGN KEY(agent_id) REFERENCES agents(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS agent_configs (
                agent_id TEXT NOT NULL,
                key TEXT NOT NULL,
                value TEXT,
                version INTEGER DEFAULT 1,
                updated_at REAL,
                PRIMARY KEY (agent_id, key),
                FOREIGN KEY(agent_id) REFERENCES agents(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                action TEXT NOT NULL,
                target_agent_id TEXT,
                details TEXT, -- JSON
                timestamp REAL,
                ip_address TEXT
            );

            CREATE TABLE IF NOT EXISTS controller_keys (
                id TEXT PRIMARY KEY DEFAULT 'default',
                private_key TEXT NOT NULL,
                public_key TEXT NOT NULL,
                algorithm TEXT DEFAULT 'RSA',
                key_size INTEGER DEFAULT 2048,
                created_at REAL,
                rotated_at REAL
            );

            CREATE INDEX IF NOT EXISTS idx_heartbeats_agent_time 
                ON heartbeats(agent_id, timestamp DESC);
                
            CREATE INDEX IF NOT EXISTS idx_commands_agent_status 
                ON commands(agent_id, status);
                
            CREATE INDEX IF NOT EXISTS idx_audit_timestamp 
                ON audit_logs(timestamp DESC);
        """)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> FleetStorage:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    # --- Agent Methods ---

    def register_agent(self, agent_id: str, data: Dict[str, Any]) -> None:
        """Register or update an agent."""
        now = time.time()
        metadata = json.dumps(data.get("metadata", {}))

        # Check if exists to preserve created_at if updating
        exists = self._conn.execute("SELECT 1 FROM agents WHERE id = ?", (agent_id,)).fetchone()

        if exists:
            self._conn.execute(
                """
                UPDATE agents SET 
                    name = ?, public_key = ?, status = ?, ip_address = ?, 
                    hostname = ?, platform = ?, version = ?, metadata = ?, 
                    last_seen_at = ?
                WHERE id = ?
            """,
                (
                    data.get("name"),
                    data.get("public_key"),
                    data.get("status", "online"),
                    data.get("ip_address"),
                    data.get("hostname"),
                    data.get("platform"),
                    data.get("version"),
                    metadata,
                    now,
                    agent_id,
                ),
            )
        else:
            self._conn.execute(
                """
                INSERT INTO agents (
                    id, name, public_key, status, ip_address, hostname, 
                    platform, version, metadata, created_at, last_seen_at, enrollment_key
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    agent_id,
                    data.get("name"),
                    data.get("public_key"),
                    data.get("status", "online"),
                    data.get("ip_address"),
                    data.get("hostname"),
                    data.get("platform"),
                    data.get("version"),
                    metadata,
                    now,
                    now,
                    data.get("enrollment_key"),
                ),
            )
        self._conn.commit()

    def get_agent(self, agent_id: str) -> Optional[Dict[str, Any]]:
        row = self._conn.execute("SELECT * FROM agents WHERE id = ?", (agent_id,)).fetchone()
        if not row:
            return None
        d = dict(row)
        if d.get("metadata"):
            d["metadata"] = json.loads(d["metadata"])
        return d

    def list_agents(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        cursor = self._conn.execute(
            "SELECT * FROM agents ORDER BY last_seen_at DESC LIMIT ? OFFSET ?", (limit, offset)
        )
        agents = []
        for row in cursor:
            d = dict(row)
            if d.get("metadata"):
                d["metadata"] = json.loads(d["metadata"])
            agents.append(d)
        return agents

    def update_agent_status(self, agent_id: str, status: str, ip: Optional[str] = None) -> None:
        now = time.time()
        if ip:
            self._conn.execute(
                "UPDATE agents SET status = ?, last_seen_at = ?, ip_address = ? WHERE id = ?",
                (status, now, ip, agent_id),
            )
        else:
            self._conn.execute(
                "UPDATE agents SET status = ?, last_seen_at = ? WHERE id = ?",
                (status, now, agent_id),
            )
        self._conn.commit()

    # --- Heartbeat Methods ---

    def record_heartbeat(
        self, agent_id: str, metrics: Dict[str, Any], ip: Optional[str] = None
    ) -> None:
        now = time.time()
        metrics_json = json.dumps(metrics)
        self._conn.execute(
            "INSERT INTO heartbeats (agent_id, timestamp, metrics, ip_address) VALUES (?, ?, ?, ?)",
            (agent_id, now, metrics_json, ip),
        )
        # Also update agent last seen
        self.update_agent_status(agent_id, "online", ip)
        self._conn.commit()

    def get_latest_heartbeat(self, agent_id: str) -> Optional[Dict[str, Any]]:
        row = self._conn.execute(
            "SELECT * FROM heartbeats WHERE agent_id = ? ORDER BY timestamp DESC LIMIT 1",
            (agent_id,),
        ).fetchone()
        if not row:
            return None
        d = dict(row)
        if d.get("metrics"):
            d["metrics"] = json.loads(d["metrics"])
        return d

    # --- Command Methods ---

    def create_command(
        self,
        cmd_id: str,
        agent_id: str,
        type_: str,
        payload: Dict[str, Any],
        priority: str = "medium",
    ) -> None:
        now = time.time()
        payload_json = json.dumps(payload)
        self._conn.execute(
            """
            INSERT INTO commands (id, agent_id, type, payload, status, priority, created_at)
            VALUES (?, ?, ?, ?, 'pending', ?, ?)
        """,
            (cmd_id, agent_id, type_, payload_json, priority, now),
        )
        self._conn.commit()

    def get_pending_commands(self, agent_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Get pending commands for an agent, ordered by priority and time."""
        # Priority sort: high < medium < low (alphabetical works inversely?)
        # Actually high > medium > low.
        # Let's map priority to int for sorting or rely on specific schema.
        # For simplicity, we'll sort by created_at for now, or add a CASE statement.

        cursor = self._conn.execute(
            """
            SELECT * FROM commands 
            WHERE agent_id = ? AND status = 'pending'
            ORDER BY 
                CASE priority
                    WHEN 'high' THEN 1
                    WHEN 'medium' THEN 2
                    WHEN 'low' THEN 3
                    ELSE 4
                END ASC,
                created_at ASC
            LIMIT ?
        """,
            (agent_id, limit),
        )

        commands = []
        for row in cursor:
            d = dict(row)
            if d.get("payload"):
                d["payload"] = json.loads(d["payload"])
            commands.append(d)
        return commands

    def update_command_status(
        self,
        cmd_id: str,
        status: str,
        response: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> None:
        now = time.time()
        update_fields = ["status = ?"]
        params: List[Any] = [status]

        if status == "sent":
            update_fields.append("sent_at = ?")
            params.append(now)
        elif status in ("completed", "failed"):
            update_fields.append("completed_at = ?")
            params.append(now)

        if response:
            update_fields.append("response = ?")
            params.append(json.dumps(response))

        if error:
            update_fields.append("error_message = ?")
            params.append(error)

        params.append(cmd_id)

        sql = f"UPDATE commands SET {', '.join(update_fields)} WHERE id = ?"
        self._conn.execute(sql, params)
        self._conn.commit()

    def get_command(self, cmd_id: str) -> Optional[Dict[str, Any]]:
        row = self._conn.execute("SELECT * FROM commands WHERE id = ?", (cmd_id,)).fetchone()
        if not row:
            return None
        d = dict(row)
        if d.get("payload"):
            d["payload"] = json.loads(d["payload"])
        if d.get("response"):
            d["response"] = json.loads(d["response"])
        return d

    def list_commands(
        self, agent_id: Optional[str] = None, limit: int = 50, offset: int = 0
    ) -> List[Dict[str, Any]]:
        if agent_id:
            sql = "SELECT * FROM commands WHERE agent_id = ? ORDER BY created_at DESC LIMIT ? OFFSET ?"
            params = (agent_id, limit, offset)
        else:
            sql = "SELECT * FROM commands ORDER BY created_at DESC LIMIT ? OFFSET ?"
            params = (limit, offset)

        cursor = self._conn.execute(sql, params)
        commands = []
        for row in cursor:
            d = dict(row)
            if d.get("payload"):
                d["payload"] = json.loads(d["payload"])
            if d.get("response"):
                d["response"] = json.loads(d["response"])
            commands.append(d)
        return commands

    # --- Token Methods ---

    def create_token(
        self, agent_id: str, token_hash: str, jti: str, expires_at: float
    ) -> Optional[int]:
        now = time.time()
        cursor = self._conn.execute(
            """
            INSERT INTO agent_tokens (agent_id, token_hash, token_jti, issued_at, expires_at)
            VALUES (?, ?, ?, ?, ?)
        """,
            (agent_id, token_hash, jti, now, expires_at),
        )
        self._conn.commit()
        return cursor.lastrowid

    def revoke_token(self, jti: str) -> None:
        now = time.time()
        self._conn.execute("UPDATE agent_tokens SET revoked_at = ? WHERE token_jti = ?", (now, jti))
        self._conn.commit()

    def is_token_revoked(self, jti: str) -> bool:
        row = self._conn.execute(
            "SELECT revoked_at FROM agent_tokens WHERE token_jti = ?", (jti,)
        ).fetchone()
        return row and row[0] is not None

    # --- Controller Keys Methods ---

    def save_controller_keys(
        self,
        private_key: str,
        public_key: str,
        key_id: str = "default",
        algorithm: str = "RSA",
        key_size: int = 2048,
    ) -> None:
        """Save or update controller RSA keys.

        Args:
            private_key: PEM-encoded private key string
            public_key: PEM-encoded public key string
            key_id: Key identifier (default: 'default')
            algorithm: Key algorithm (default: 'RSA')
            key_size: Key size in bits (default: 2048)
        """
        now = time.time()
        exists = self._conn.execute(
            "SELECT 1 FROM controller_keys WHERE id = ?", (key_id,)
        ).fetchone()

        if exists:
            self._conn.execute(
                """
                UPDATE controller_keys SET 
                    private_key = ?, public_key = ?, algorithm = ?, 
                    key_size = ?, rotated_at = ?
                WHERE id = ?
            """,
                (private_key, public_key, algorithm, key_size, now, key_id),
            )
            logger.info("Controller keys rotated for key_id: %s", key_id)
        else:
            self._conn.execute(
                """
                INSERT INTO controller_keys 
                    (id, private_key, public_key, algorithm, key_size, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
                (key_id, private_key, public_key, algorithm, key_size, now),
            )
            logger.info("Controller keys saved for key_id: %s", key_id)
        self._conn.commit()

    def get_controller_keys(self, key_id: str = "default") -> Optional[Dict[str, Any]]:
        """Retrieve controller keys by key_id.

        Returns:
            Dict with private_key, public_key, algorithm, key_size, created_at, rotated_at
            or None if no keys found.
        """
        row = self._conn.execute("SELECT * FROM controller_keys WHERE id = ?", (key_id,)).fetchone()
        if not row:
            return None
        return dict(row)

    def delete_controller_keys(self, key_id: str = "default") -> bool:
        """Delete controller keys by key_id.

        Returns:
            True if deleted, False if not found.
        """
        cursor = self._conn.execute("DELETE FROM controller_keys WHERE id = ?", (key_id,))
        self._conn.commit()
        return cursor.rowcount > 0
