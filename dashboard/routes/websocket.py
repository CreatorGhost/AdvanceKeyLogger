"""
WebSocket endpoints for real-time dashboard communication.

Provides WebSocket connections for live dashboard updates and agent communication.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.websockets import WebSocketState

from dashboard.auth import get_current_user
from config.settings import Settings

logger = logging.getLogger(__name__)

# Create router for WebSocket endpoints
ws_router = APIRouter(tags=["websocket"])


_MAX_WS_CONNECTIONS = 200  # Upper bound on total simultaneous WebSocket connections
_MAX_WS_MESSAGE_SIZE = 1_048_576  # 1 MB max inbound WebSocket message


class ConnectionManager:
    """Manage WebSocket connections for dashboard."""

    def __init__(self, max_connections: int = _MAX_WS_CONNECTIONS):
        self.active_connections: set[WebSocket] = set()
        self.agent_connections: dict[str, WebSocket] = {}
        self.dashboard_connections: set[WebSocket] = set()
        self.agent_last_seen: dict[str, float] = {}
        self._lock = asyncio.Lock()
        self.max_connections = max_connections

    async def connect_dashboard(self, websocket: WebSocket) -> bool:
        """Connect dashboard client (with connection limit check under lock).

        Returns True if the connection was accepted and added, False if the
        limit was reached (socket accepted then immediately closed).
        """
        async with self._lock:
            if len(self.active_connections) >= self.max_connections:
                await websocket.accept()
                await websocket.close(code=4008, reason="Connection limit reached")
                return False
            await websocket.accept()
            self.active_connections.add(websocket)
            self.dashboard_connections.add(websocket)
        logger.info("Dashboard client connected")
        return True

    async def connect_agent(self, websocket: WebSocket, agent_id: str) -> bool:
        """Connect agent client, gracefully closing any previous connection.

        Returns True if the connection was accepted and added, False if the
        limit was reached (socket accepted then immediately closed).
        """
        async with self._lock:
            if len(self.active_connections) >= self.max_connections:
                await websocket.accept()
                await websocket.close(code=4008, reason="Connection limit reached")
                return False
            # Close existing connection for this agent if present
            previous = self.agent_connections.get(agent_id)
            if previous is not None:
                try:
                    await previous.close(code=1012, reason="Replaced by new connection")
                except Exception:
                    pass
                self.active_connections.discard(previous)
                logger.info(f"Agent {agent_id} previous connection closed (reconnection)")

            await websocket.accept()
            self.active_connections.add(websocket)
            self.agent_connections[agent_id] = websocket
            self.agent_last_seen[agent_id] = time.time()
            logger.info(f"Agent {agent_id} connected")
        return True

    async def disconnect(self, websocket: WebSocket) -> None:
        """Disconnect client."""
        async with self._lock:
            self.active_connections.discard(websocket)
            self.dashboard_connections.discard(websocket)

            # Remove from agent connections if present
            for agent_id, ws in list(self.agent_connections.items()):
                if ws == websocket:
                    del self.agent_connections[agent_id]
                    self.agent_last_seen[agent_id] = time.time()
                    logger.info(f"Agent {agent_id} disconnected")
                    break

            # Prune stale agent_last_seen entries for agents no longer connected
            # to prevent unbounded memory growth from transient agents.
            _stale_threshold = time.time() - 3600  # 1 hour
            stale = [
                aid for aid, ts in self.agent_last_seen.items()
                if aid not in self.agent_connections and ts < _stale_threshold
            ]
            for aid in stale:
                del self.agent_last_seen[aid]

        logger.info("Client disconnected")

    async def send_personal_message(self, message: str, websocket: WebSocket) -> None:
        """Send message to specific client."""
        if websocket and websocket.client_state == WebSocketState.CONNECTED:
            await websocket.send_text(message)

    async def broadcast_dashboard(self, message: str) -> None:
        """Broadcast message to all dashboard clients concurrently."""
        async with self._lock:
            connections = list(self.dashboard_connections)
        if not connections:
            return

        async def _safe_send(conn: WebSocket) -> WebSocket | None:
            try:
                if conn.client_state == WebSocketState.CONNECTED:
                    await conn.send_text(message)
                    return None
                return conn
            except Exception:
                return conn

        results = await asyncio.gather(*[_safe_send(c) for c in connections])
        # Clean up disconnected connections
        for conn in results:
            if conn is not None:
                await self.disconnect(conn)

    async def send_to_agent(self, agent_id: str, message: str) -> bool:
        """Send message to specific agent."""
        async with self._lock:
            websocket = self.agent_connections.get(agent_id)
            if not websocket or websocket.client_state != WebSocketState.CONNECTED:
                return False
            # Send under lock to prevent using a stale reference
            try:
                await websocket.send_text(message)
                return True
            except (WebSocketDisconnect, Exception) as exc:
                logger.warning("send_to_agent(%s) failed: %s", agent_id, exc)
                if self.agent_connections.get(agent_id) is websocket:
                    del self.agent_connections[agent_id]
                self.active_connections.discard(websocket)
                return False

    async def get_dashboard_clients(self) -> int:
        """Get count of dashboard clients."""
        async with self._lock:
            return len(self.dashboard_connections)

    async def get_agent_snapshot(self) -> list[tuple[str, Any]]:
        """Return a snapshot of agent connections under lock."""
        async with self._lock:
            return list(self.agent_connections.items())

    async def get_agent_clients(self) -> dict[str, Any]:
        """Get agent client information."""
        async with self._lock:
            items = list(self.agent_connections.items())
            last_seen_snapshot = dict(self.agent_last_seen)
        return {
            agent_id: {
                "connected": (ws.client_state == WebSocketState.CONNECTED if ws else False),
                "last_seen": last_seen_snapshot.get(agent_id, 0.0),
            }
            for agent_id, ws in items
        }

    async def update_agent_last_seen(self, agent_id: str) -> None:
        """Update the last_seen timestamp for an agent."""
        async with self._lock:
            self.agent_last_seen[agent_id] = time.time()


# Global connection manager
manager = ConnectionManager()


def _validate_origin(websocket: WebSocket) -> bool:
    """Validate WebSocket Origin header against allowed origins.

    Returns True if origin is acceptable, False otherwise.
    If no Origin header is present (e.g. non-browser clients), allow by default.
    """
    origin = websocket.headers.get("origin")
    if not origin:
        # Non-browser clients (agents) may not send Origin
        return True

    # Load allowed origins from settings; default allows same-host connections
    try:
        settings = Settings()
        allowed = settings.get("dashboard.allowed_origins", [])
    except Exception:
        allowed = []

    if not allowed:
        # If no allow-list configured, accept same-host origins.
        # Parse the Origin URL so we compare host[:port] correctly,
        # regardless of scheme or default-port omission.
        host_header = websocket.headers.get("host", "")
        if not host_header:
            return True
        parsed = urlparse(origin)
        # netloc is host[:port] from the Origin URL
        origin_netloc = parsed.netloc or ""
        return origin_netloc == host_header

    return origin in allowed


def _extract_ws_token(websocket: WebSocket) -> str | None:
    """Extract auth token from WebSocket headers or query params."""
    # Try Authorization header first
    auth_header = websocket.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        return auth_header[7:].strip()
    # Fall back to query param
    return websocket.query_params.get("token")


def _validate_session_token(token: str) -> str | None:
    """Validate a session token and return username, or None if invalid.

    Tries dashboard session tokens first, then falls back to fleet JWT tokens
    so that agents connecting via WebSocket transport can authenticate.
    """
    from dashboard.auth import _sessions, _sessions_lock, _SESSION_TTL
    import time as _time

    # Try dashboard session token first (must hold the lock – WebSocket handlers
    # run concurrently with HTTP request handlers that mutate _sessions).
    with _sessions_lock:
        session = _sessions.get(token)
        if session:
            if _time.time() - session["created"] > _SESSION_TTL:
                _sessions.pop(token, None)
            else:
                return session["username"]

    # Fall back to fleet JWT token validation
    try:
        from fleet.auth import FleetAuth

        # Try to get the app's fleet_auth instance via the global fleet_controller reference
        if _fleet_controller and hasattr(_fleet_controller, "config"):
            jwt_secret = _fleet_controller.config.get("jwt_secret")
            if not jwt_secret:
                return None
            auth = FleetAuth(jwt_secret)
            agent_id = auth.verify_token(token, expected_type="access")
            if agent_id:
                return agent_id
    except ImportError:
        pass
    except Exception:
        pass

    return None


@ws_router.websocket("/ws/dashboard")
async def websocket_dashboard_endpoint(websocket: WebSocket) -> None:
    """WebSocket endpoint for dashboard clients (authenticated)."""
    # Validate Origin header to prevent cross-site WebSocket hijacking
    if not _validate_origin(websocket):
        await websocket.accept()
        await websocket.close(code=4002, reason="Origin not allowed")
        return

    # Must accept before sending close with reason (WebSocket protocol)
    token = _extract_ws_token(websocket)
    if not token:
        await websocket.accept()
        await websocket.close(code=4001, reason="Missing authentication token")
        return

    user = _validate_session_token(token)
    if not user:
        await websocket.accept()
        await websocket.close(code=4003, reason="Invalid or expired token")
        return

    # connect_dashboard checks the connection limit atomically under the lock.
    connected = await manager.connect_dashboard(websocket)
    if not connected:
        return

    try:
        while True:
            data = await websocket.receive_text()

            # Reject oversized messages
            if len(data) > _MAX_WS_MESSAGE_SIZE:
                logger.warning("Dashboard WS message too large (%d bytes), dropping", len(data))
                continue

            await _process_dashboard_command(data, websocket)

    except WebSocketDisconnect:
        await manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"Dashboard WebSocket error: {e}")
        try:
            await websocket.close()
        except Exception:
            pass
        await manager.disconnect(websocket)


@ws_router.websocket("/ws/agent/{agent_id}")
async def websocket_agent_endpoint(websocket: WebSocket, agent_id: str) -> None:
    """WebSocket endpoint for agent clients (authenticated)."""
    # Validate Origin header to prevent cross-site WebSocket hijacking
    if not _validate_origin(websocket):
        await websocket.accept()
        await websocket.close(code=4002, reason="Origin not allowed")
        return

    # Extract token before accepting so we can reject early
    token = _extract_ws_token(websocket)

    # Must accept before sending close with reason (WebSocket protocol)
    if not token:
        await websocket.accept()
        await websocket.close(code=4001, reason="Missing authentication token")
        await manager.disconnect(websocket)
        return

    agent_user = _validate_session_token(token)
    if not agent_user:
        await websocket.accept()
        await websocket.close(code=4003, reason="Invalid or expired token")
        await manager.disconnect(websocket)
        return

    # For fleet JWT tokens, ensure the authenticated identity matches the URL agent_id
    # to prevent one agent from connecting as another. Dashboard admin users are allowed
    # to connect to any agent channel for management purposes.
    from dashboard.auth import _sessions as _dash_sessions, _sessions_lock as _dash_lock
    with _dash_lock:
        is_dashboard_user = token in _dash_sessions
    if not is_dashboard_user and agent_user != agent_id:
        await websocket.accept()
        await websocket.close(code=4003, reason="Token identity does not match agent_id")
        await manager.disconnect(websocket)
        return

    # connect_agent checks the connection limit atomically under the lock.
    connected = await manager.connect_agent(websocket, agent_id)
    if not connected:
        return

    try:
        while True:
            data = await websocket.receive_text()

            # Reject oversized messages
            if len(data) > _MAX_WS_MESSAGE_SIZE:
                logger.warning("Agent %s WS message too large (%d bytes), dropping", agent_id, len(data))
                continue

            await _process_agent_message(data, agent_id)

    except WebSocketDisconnect:
        await manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"Agent {agent_id} WebSocket error: {e}")
        try:
            await websocket.close()
        except Exception:
            pass
        await manager.disconnect(websocket)


async def _process_dashboard_command(data: str, websocket: WebSocket) -> None:
    """Process command from dashboard."""
    try:
        command = json.loads(data)
        action = command.get("action")

        if action == "get_status":
            # Collect system resource metrics
            system_info = {}
            try:
                import psutil

                system_info = {
                    "cpu_percent": psutil.cpu_percent(interval=0),
                    "memory_percent": psutil.virtual_memory().percent,
                    "disk_percent": psutil.disk_usage("/").percent,
                }
            except Exception:
                pass

            # Send dashboard status
            status = {
                "clients": await manager.get_dashboard_clients(),
                "agents": await manager.get_agent_clients(),
                "system": system_info,
                "timestamp": time.time(),
            }
            await websocket.send_text(json.dumps({"type": "status", "data": status}))

        elif action == "broadcast":
            # Broadcast message to all agents
            message = command.get("message", "")
            await _broadcast_to_agents(message)

        elif action == "send_to_agent" or action == "command":
            # "command" is an alias for "send_to_agent" (frontend uses "command")
            # Validate agent_id before sending
            agent_id = command.get("agent_id")
            if not agent_id:
                response = {
                    "type": "command_result",
                    "success": False,
                    "error": "missing agent_id",
                }
                await websocket.send_text(json.dumps(response))
                return

            # Support both message (raw) and action/parameters (structured command)
            cmd_action = command.get("action_type") or command.get("action")
            parameters = command.get("parameters", {})
            message = command.get("message") or json.dumps(
                {
                    "action": cmd_action,
                    "parameters": parameters,
                }
            )
            success = await manager.send_to_agent(agent_id, message)
            import secrets as _secrets
            response = {
                "type": "command_result",
                "command_id": command.get("command_id") or _secrets.token_hex(8),
                "success": success,
                "agent_id": agent_id,
                "message": message,
            }
            await websocket.send_text(json.dumps(response))

        elif action == "get_captures":
            # Get recent captures (would integrate with storage system)
            # For now, return mock data
            captures = await _get_recent_captures()
            await websocket.send_text(json.dumps({"type": "captures", "data": captures}))

        else:
            logger.warning(f"Unknown dashboard command: {action}")

    except json.JSONDecodeError:
        logger.error("Invalid JSON from dashboard")
    except Exception as e:
        logger.error(f"Error processing dashboard command: {e}")


async def _process_agent_message(data: str, agent_id: str) -> None:
    """Process message from agent."""
    try:
        message = json.loads(data)
        message_type = message.get("type")

        # ProtocolMessage uses "payload" key, plain messages use "data".
        # Support both so agents using either transport format work correctly.
        # Use key-presence checks instead of truthiness so that legitimate
        # falsy values (e.g. an empty dict {}) are not silently skipped.
        def _get_payload(fallback=None):
            if fallback is None:
                fallback = {}
            if "data" in message:
                return message["data"]
            if "payload" in message:
                return message["payload"]
            return fallback

        if message_type == "heartbeat":
            # Update agent status and last_seen
            status_data = _get_payload()
            await manager.update_agent_last_seen(agent_id)
            await _update_agent_status(agent_id, status_data)

            # Broadcast to dashboard
            broadcast_data = {
                "type": "agent_status",
                "agent_id": agent_id,
                "status": status_data,
                "timestamp": time.time(),
            }
            await manager.broadcast_dashboard(json.dumps(broadcast_data))

        elif message_type == "capture":
            # Handle capture data
            capture_data = _get_payload()
            await manager.update_agent_last_seen(agent_id)
            await _handle_capture_data(agent_id, capture_data)

            # Broadcast to dashboard — flatten capture fields so frontend
            # can access data.capture_type, data.data, data.status directly
            broadcast_data = {
                "type": "new_capture",
                "agent_id": agent_id,
                "capture_type": capture_data.get("type", "unknown"),
                "data": capture_data.get("data", ""),
                "status": capture_data.get("status", "pending"),
                "timestamp": time.time(),
            }
            await manager.broadcast_dashboard(json.dumps(broadcast_data))

        elif message_type == "command_response":
            # Handle command response from agent
            response_data = _get_payload()
            await manager.update_agent_last_seen(agent_id)
            await _handle_command_response(agent_id, response_data)

        else:
            logger.warning(f"Unknown agent message type: {message_type}")

    except json.JSONDecodeError:
        logger.error("Invalid JSON from agent")
    except Exception as e:
        logger.error(f"Error processing agent message: {e}")


async def _broadcast_to_agents(message: str) -> None:
    """Broadcast message to all connected agents."""
    agents = await manager.get_agent_snapshot()
    for _agent_id, websocket in agents:
        if websocket and websocket.client_state == WebSocketState.CONNECTED:
            try:
                await websocket.send_text(message)
            except Exception:
                continue


# Storage reference for handlers (set by app initialization)
_storage = None
_fleet_storage = None
_fleet_controller = None


def set_storage_references(storage=None, fleet_storage=None, fleet_controller=None):
    """Set storage references for WebSocket handlers."""
    global _storage, _fleet_storage, _fleet_controller
    _storage = storage
    _fleet_storage = fleet_storage
    _fleet_controller = fleet_controller


async def _get_recent_captures() -> list[dict[str, Any]]:
    """Get recent captures from storage."""
    # Try to use real storage if available
    if _storage is not None:
        try:
            pending = await asyncio.to_thread(_storage.get_pending, 10)
            return [
                {
                    "id": item.get("id", f"capture_{i}"),
                    "type": item.get("capture_type", "unknown"),
                    "data": item.get("data", "")[:100],  # Truncate for preview
                    "timestamp": item.get("timestamp", time.time()),
                    "agent_id": item.get("agent_id", "local"),
                    "status": item.get("status", "pending"),
                }
                for i, item in enumerate(pending)
            ]
        except Exception as e:
            logger.warning(f"Failed to get captures from storage: {e}")

    # No storage configured or storage query failed — return empty list rather
    # than fabricated mock data which would be misleading in a production dashboard.
    return []


async def _update_agent_status(agent_id: str, status_data: dict[str, Any]) -> None:
    """Update agent status in storage."""
    # Update in fleet storage if available
    if _fleet_storage is not None:
        try:
            status = status_data.get("status", "ONLINE")
            await asyncio.to_thread(_fleet_storage.update_agent_status, agent_id, status)
            logger.debug(f"Agent {agent_id} status updated to {status} in DB")
        except Exception as e:
            logger.warning(f"Failed to update agent status in DB: {e}")
    else:
        logger.debug(f"Agent {agent_id} status updated (keys: {list(status_data.keys())})")


async def _handle_capture_data(agent_id: str, capture_data: dict[str, Any]) -> None:
    """Handle capture data from agent and persist to storage."""
    capture_type = capture_data.get("type", "unknown")
    data = capture_data.get("data", "")

    # Persist to storage if available
    if _storage is not None:
        try:
            await asyncio.to_thread(
                _storage.insert,
                capture_type=capture_type,
                data=str(data),
            )
            logger.debug(f"Agent {agent_id} capture stored (type={capture_type})")
        except Exception as e:
            logger.warning(f"Failed to store capture data: {e}")
    else:
        logger.debug(
            "Agent %s sent capture (type=%s, size=%d)",
            agent_id,
            capture_type,
            len(str(capture_data)),
        )


async def _handle_command_response(agent_id: str, response_data: dict[str, Any]) -> None:
    """Handle command response from agent and update in controller."""
    cmd_id = response_data.get("command_id", "unknown")
    status = response_data.get("status", "unknown")

    logger.info("Agent %s command response (command_id=%s, status=%s)", agent_id, cmd_id, status)

    # Forward to fleet controller if available
    if _fleet_controller is not None:
        try:
            # Normalize to match the REST API's CommandResponseRequest contract.
            # The controller checks result.get("success", False) and result.get("error")
            # at the top level.  req.model_dump() from the REST path produces
            # {"result": {...}, "success": bool, "error": str|None}, so we must
            # build the same shape here — the raw response_data dict from a WebSocket
            # agent may carry extra keys (command_id, status) or nest success/error
            # inside "result" rather than at the top level.
            normalized = {
                "result": response_data.get("result", {}),
                "success": response_data.get("success", False),
                "error": response_data.get("error"),
            }
            await _fleet_controller.handle_command_response(agent_id, cmd_id, normalized)
            logger.debug(f"Command response forwarded to controller")
        except Exception as e:
            logger.warning(f"Failed to forward command response to controller: {e}")
    else:
        logger.debug("Agent %s full command response: %s", agent_id, response_data)
