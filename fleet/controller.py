"""
Fleet controller implementation with persistence and advanced features.
"""

from __future__ import annotations

import logging
import asyncio
import time
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import asdict

from agent_controller import (
    Controller,
    AgentMetadata,
    Command,
    CommandStatus,
    CommandPriority,
    AgentCapabilities,
    AgentStatus,
    SecureChannel,
)
from storage.fleet_storage import FleetStorage

logger = logging.getLogger(__name__)


class FleetController(Controller):
    """
    Enhanced Controller with SQLite persistence and fleet management integration.
    """

    def __init__(self, config: Dict[str, Any], storage: FleetStorage) -> None:
        # We don't call super().__init__ immediately because it initializes empty state
        # But we need to call it to set up basic structures
        super().__init__(config)
        self.storage = storage

        # Initialize SecureChannel with persistence
        self.secure_channel = SecureChannel()
        self._load_or_generate_keys()

        self._load_state()

    async def start(self) -> None:
        """Start the controller service and initialize command queues."""
        # Initialize command queues for all loaded agents
        for agent_id in self.agents:
            if agent_id not in self.command_queues:
                self.command_queues[agent_id] = asyncio.PriorityQueue()

        # Re-queue pending commands from DB
        for agent_id in self.agents:
            pending_cmds = self.storage.get_pending_commands(agent_id)
            for cmd_data in pending_cmds:
                try:
                    try:
                        priority = CommandPriority[cmd_data["priority"].upper()]
                    except (KeyError, AttributeError):
                        priority = CommandPriority.NORMAL
                    cmd = Command(
                        command_id=cmd_data["id"],
                        agent_id=cmd_data["agent_id"],
                        action=cmd_data["type"],
                        parameters=cmd_data["payload"],
                        priority=priority,
                        timestamp=cmd_data["created_at"],
                        status=CommandStatus.PENDING,
                    )
                    self.commands[cmd.command_id] = cmd
                    queue = self.command_queues.get(agent_id)
                    if queue:
                        seq = next(self._command_counter)
                        await queue.put((cmd.priority.value, seq, cmd))
                except Exception as e:
                    logger.error(f"Failed to re-queue command {cmd_data.get('id')}: {e}")

        await super().start()

    def _load_or_generate_keys(self) -> None:
        """Load controller keys from storage or generate new ones.

        If keys exist in the database, they are loaded into the SecureChannel.
        Otherwise, new keys are generated and persisted.
        """
        try:
            keys_data = self.storage.get_controller_keys()
            if keys_data:
                # Load existing keys from storage
                private_key_pem = keys_data.get("private_key", "")
                public_key_pem = keys_data.get("public_key", "")

                if private_key_pem and public_key_pem:
                    self.secure_channel.private_key = private_key_pem.encode("utf-8")
                    self.secure_channel.public_key = public_key_pem.encode("utf-8")
                    logger.info(
                        "Controller keys loaded from storage (created: %s)",
                        keys_data.get("created_at"),
                    )
                    return
        except Exception as e:
            logger.warning("Failed to load controller keys from storage: %s", e)

        # Generate new keys and persist them
        self.secure_channel.initialize()
        logger.info("Controller keys generated")

        # Persist the newly generated keys
        try:
            private_key = self.secure_channel.private_key
            public_key = self.secure_channel.public_key
            if private_key and public_key:
                self.storage.save_controller_keys(
                    private_key=private_key.decode("utf-8"),
                    public_key=public_key.decode("utf-8"),
                    algorithm="RSA",
                    key_size=2048,
                )
                logger.info("Controller keys persisted to storage")
        except Exception as e:
            logger.error("Failed to persist controller keys: %s", e)

    def get_public_key(self) -> str:
        """Return the controller's public key as PEM string."""
        if self.secure_channel.public_key:
            return self.secure_channel.public_key.decode("utf-8")
        return ""

    def rotate_keys(self) -> bool:
        """Generate and persist new controller keys.

        Returns:
            True if keys were rotated successfully, False otherwise.
        """
        try:
            # Generate new keys
            self.secure_channel.initialize()

            # Persist to storage (will update existing record)
            private_key = self.secure_channel.private_key
            public_key = self.secure_channel.public_key
            if private_key and public_key:
                self.storage.save_controller_keys(
                    private_key=private_key.decode("utf-8"),
                    public_key=public_key.decode("utf-8"),
                    algorithm="RSA",
                    key_size=2048,
                )
                logger.info("Controller keys rotated successfully")
                return True
        except Exception as e:
            logger.error("Failed to rotate controller keys: %s", e)
        return False

    def _load_state(self) -> None:
        """Load agents and commands from persistent storage."""
        try:
            # Load agents
            agents_data = self.storage.list_agents(limit=5000)
            for data in agents_data:
                try:
                    metadata = AgentMetadata(
                        agent_id=data["id"],
                        hostname=data.get("hostname", "unknown"),
                        platform=data.get("platform", "unknown"),
                        version=data.get("version", "unknown"),
                        ip_address=data.get("ip_address", "0.0.0.0"),
                        mac_address=data.get("metadata", {}).get("mac_address", ""),
                        capabilities=AgentCapabilities(
                            **data.get("metadata", {}).get("capabilities", {})
                        ),
                        first_seen=data.get("created_at", time.time()),
                        last_seen=data.get("last_seen_at", time.time()),
                        status=AgentStatus[data.get("status", "OFFLINE").upper()],
                    )
                    self.agents[metadata.agent_id] = metadata
                except Exception as e:
                    logger.error(f"Failed to restore agent {data.get('id')}: {e}")

            # Note: Command queues and pending commands are loaded in start()
            # when the event loop is running
            logger.info(f"Restored {len(self.agents)} agents from storage")

        except Exception as e:
            logger.error(f"Error loading fleet state: {e}")

    # Override register_agent to persist
    async def register_agent(self, metadata: AgentMetadata, transport: Any, public_key: bytes) -> Any:
        # Extract enrollment_key from tags if present
        # Convention: enrollment key is stored as a tag with prefix "enrollment_key:"
        enrollment_key = None
        for tag in metadata.tags:
            if tag.startswith("enrollment_key:"):
                enrollment_key = tag[len("enrollment_key:") :]
                break

        # Persist to DB first (offloaded to thread) — if this fails we don't
        # touch in-memory state at all.
        agent_dict = metadata.to_dict()
        await asyncio.to_thread(
            self.storage.register_agent,
            metadata.agent_id,
            {
                "name": metadata.hostname,
                "public_key": public_key.decode("utf-8", errors="ignore"),
                "status": metadata.status.name,
                "ip_address": metadata.ip_address,
                "hostname": metadata.hostname,
                "platform": metadata.platform,
                "version": metadata.version,
                "metadata": agent_dict,
                "enrollment_key": enrollment_key,
            },
        )

        # Now register in-memory via parent (creates SecureChannel, updates dicts
        # under self._lock).  If this somehow fails, roll back the DB row.
        try:
            channel = await super().register_agent(metadata, transport, public_key)
        except Exception:
            logger.error(
                "In-memory registration failed for agent %s, rolling back DB row",
                metadata.agent_id,
                exc_info=True,
            )
            try:
                await asyncio.to_thread(
                    self.storage.update_agent_status, metadata.agent_id, "UNREGISTERED",
                )
            except Exception:
                pass
            raise
        return channel

    # Override handle_heartbeat to persist
    async def handle_heartbeat(self, agent_id: str, data: Dict[str, Any]) -> None:
        await super().handle_heartbeat(agent_id, data)
        # Record in DB — pass the actual status from the in-memory agent
        # to avoid hardcoding "online" and eliminate the redundant second DB write
        agent = self.agents.get(agent_id)
        agent_status = agent.status.name if agent else "ONLINE"
        await asyncio.to_thread(self.storage.record_heartbeat, agent_id, data, status=agent_status)

    # Override send_command to persist
    def send_command(
        self,
        agent_id: str,
        action: str,
        parameters: Dict[str, Any],
        priority: CommandPriority = CommandPriority.NORMAL,
        timeout: float = 300.0,
    ) -> Optional[str]:
        command_id = super().send_command(agent_id, action, parameters, priority, timeout)
        if command_id:
            self.storage.create_command(
                command_id, agent_id, action, parameters, priority.name.lower()
            )
        return command_id

    # Override handle_command_response to persist
    async def handle_command_response(
        self, agent_id: str, command_id: str, result: Dict[str, Any]
    ) -> None:
        await super().handle_command_response(agent_id, command_id, result)

        command = self.commands.get(command_id)
        if command:
            cmd_status = command.status.name.lower()
            error = command.error_message
            await asyncio.to_thread(
                self.storage.update_command_status, command_id, cmd_status, result, error or ""
            )

    async def send_command_async(
        self,
        agent_id: str,
        action: str,
        parameters: Dict[str, Any],
        priority: CommandPriority = CommandPriority.NORMAL,
        timeout: float = 300.0,
    ) -> Optional[str]:
        """Async version of send_command.

        Offloads the blocking storage.create_command() call to a thread so the
        event loop is not stalled.
        """
        # Acquire the controller lock so the sync super().send_command() —
        # which reads/writes self.agents, self.commands, self.command_queues —
        # does not race with other async methods that hold the same lock.
        async with self._lock:
            command_id = super().send_command(agent_id, action, parameters, priority, timeout)
        if command_id:
            await asyncio.to_thread(
                self.storage.create_command,
                command_id, agent_id, action, parameters, priority.name.lower(),
            )
        return command_id

    def send_command_sync_safe(
        self,
        agent_id: str,
        action: str,
        parameters: Dict[str, Any],
        priority: CommandPriority = CommandPriority.NORMAL,
        timeout: float = 300.0,
    ) -> Optional[str]:
        """Thread-safe command sending from sync context.

        Note: Since send_command() now uses put_nowait() internally, it's already
        sync-safe. This method exists for API consistency.
        """
        return self.send_command(agent_id, action, parameters, priority, timeout)
