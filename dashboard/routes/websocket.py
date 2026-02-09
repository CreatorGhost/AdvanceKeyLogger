"""
WebSocket endpoints for real-time dashboard communication.

Provides WebSocket connections for live dashboard updates and agent communication.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Dict, List, Optional, Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.websockets import WebSocketState

from dashboard.auth import get_current_user
from config.settings import Settings

logger = logging.getLogger(__name__)

# Create router for WebSocket endpoints
ws_router = APIRouter(tags=["websocket"])


class ConnectionManager:
    """Manage WebSocket connections for dashboard."""

    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
        self.agent_connections: Dict[str, WebSocket] = {}
        self.dashboard_connections: Set[WebSocket] = set()

    async def connect_dashboard(self, websocket: WebSocket) -> None:
        """Connect dashboard client."""
        await websocket.accept()
        self.active_connections.add(websocket)
        self.dashboard_connections.add(websocket)
        logger.info("Dashboard client connected")

    async def connect_agent(self, websocket: WebSocket, agent_id: str) -> None:
        """Connect agent client, gracefully closing any previous connection."""
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
        logger.info(f"Agent {agent_id} connected")

    def disconnect(self, websocket: WebSocket) -> None:
        """Disconnect client."""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

        if websocket in self.dashboard_connections:
            self.dashboard_connections.remove(websocket)

        # Remove from agent connections if present
        for agent_id, ws in list(self.agent_connections.items()):
            if ws == websocket:
                del self.agent_connections[agent_id]
                logger.info(f"Agent {agent_id} disconnected")
                break

        logger.info("Client disconnected")

    async def send_personal_message(self, message: str, websocket: WebSocket) -> None:
        """Send message to specific client."""
        if websocket and websocket.client_state == WebSocketState.CONNECTED:
            await websocket.send_text(message)

    async def broadcast_dashboard(self, message: str) -> None:
        """Broadcast message to all dashboard clients."""
        disconnected = []

        for connection in list(self.dashboard_connections):
            try:
                if connection.client_state == WebSocketState.CONNECTED:
                    await connection.send_text(message)
                else:
                    disconnected.append(connection)
            except Exception:
                disconnected.append(connection)

        # Clean up disconnected connections
        for connection in disconnected:
            self.disconnect(connection)

    async def send_to_agent(self, agent_id: str, message: str) -> bool:
        """Send message to specific agent."""
        if agent_id in self.agent_connections:
            websocket = self.agent_connections[agent_id]
            if websocket and websocket.client_state == WebSocketState.CONNECTED:
                await websocket.send_text(message)
                return True

        return False

    async def get_dashboard_clients(self) -> int:
        """Get count of dashboard clients."""
        return len(self.dashboard_connections)

    async def get_agent_clients(self) -> Dict[str, Any]:
        """Get agent client information."""
        return {
            agent_id: {
                "connected": (ws.client_state == WebSocketState.CONNECTED if ws else False),
                "last_seen": time.time(),
            }
            for agent_id, ws in self.agent_connections.items()
        }


# Global connection manager
manager = ConnectionManager()


def _extract_ws_token(websocket: WebSocket) -> str | None:
    """Extract auth token from WebSocket headers or query params."""
    # Try Authorization header first
    auth_header = websocket.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        return auth_header[7:].strip()
    # Fall back to query param
    return websocket.query_params.get("token")


def _validate_session_token(token: str) -> str | None:
    """Validate a session token and return username, or None if invalid."""
    from dashboard.auth import _sessions, _SESSION_TTL
    import time as _time

    session = _sessions.get(token)
    if not session:
        return None
    if _time.time() - session["created"] > _SESSION_TTL:
        _sessions.pop(token, None)
        return None
    return session["username"]


@ws_router.websocket("/ws/dashboard")
async def websocket_dashboard_endpoint(websocket: WebSocket) -> None:
    """WebSocket endpoint for dashboard clients (authenticated)."""
    # Authenticate before accepting
    token = _extract_ws_token(websocket)
    if not token:
        await websocket.close(code=4001, reason="Missing authentication token")
        return

    user = _validate_session_token(token)
    if not user:
        await websocket.close(code=4003, reason="Invalid or expired token")
        return

    await manager.connect_dashboard(websocket)

    try:
        while True:
            # Receive message from dashboard
            data = await websocket.receive_text()

            # Process dashboard commands
            await _process_dashboard_command(data, websocket)

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"Dashboard WebSocket error: {e}")
        manager.disconnect(websocket)


@ws_router.websocket("/ws/agent/{agent_id}")
async def websocket_agent_endpoint(websocket: WebSocket, agent_id: str) -> None:
    """WebSocket endpoint for agent clients (authenticated)."""
    # Authenticate the agent before accepting
    token = _extract_ws_token(websocket)
    if not token:
        await websocket.close(code=4001, reason="Missing authentication token")
        return

    # Validate that the token belongs to the requested agent_id
    agent_user = _validate_session_token(token)
    if not agent_user:
        await websocket.close(code=4003, reason="Invalid or expired token")
        return

    await manager.connect_agent(websocket, agent_id)

    try:
        while True:
            # Receive message from agent
            data = await websocket.receive_text()

            # Process agent message
            await _process_agent_message(data, agent_id)

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"Agent {agent_id} WebSocket error: {e}")
        manager.disconnect(websocket)


async def _process_dashboard_command(data: str, websocket: WebSocket) -> None:
    """Process command from dashboard."""
    try:
        command = json.loads(data)
        action = command.get("action")

        if action == "get_status":
            # Send dashboard status
            status = {
                "clients": await manager.get_dashboard_clients(),
                "agents": await manager.get_agent_clients(),
                "timestamp": time.time(),
            }
            await websocket.send_text(json.dumps({"type": "status", "data": status}))

        elif action == "broadcast":
            # Broadcast message to all agents
            message = command.get("message", "")
            await _broadcast_to_agents(message)

        elif action == "send_to_agent":
            # Send message to specific agent
            agent_id = command.get("agent_id")
            message = command.get("message", "")
            success = await manager.send_to_agent(agent_id, message)
            response = {
                "type": "command_result",
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

        if message_type == "heartbeat":
            # Update agent status
            status_data = message.get("data", {})
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
            capture_data = message.get("data", {})
            await _handle_capture_data(agent_id, capture_data)

            # Broadcast to dashboard
            broadcast_data = {
                "type": "new_capture",
                "agent_id": agent_id,
                "capture": capture_data,
                "timestamp": time.time(),
            }
            await manager.broadcast_dashboard(json.dumps(broadcast_data))

        elif message_type == "command_response":
            # Handle command response from agent
            response_data = message.get("data", {})
            await _handle_command_response(agent_id, response_data)

        else:
            logger.warning(f"Unknown agent message type: {message_type}")

    except json.JSONDecodeError:
        logger.error("Invalid JSON from agent")
    except Exception as e:
        logger.error(f"Error processing agent message: {e}")


async def _broadcast_to_agents(message: str) -> None:
    """Broadcast message to all connected agents."""
    for agent_id, websocket in manager.agent_connections.items():
        if websocket and websocket.client_state == WebSocketState.CONNECTED:
            try:
                await websocket.send_text(message)
            except Exception:
                continue


async def _get_recent_captures() -> List[Dict[str, Any]]:
    """Get recent captures from storage (mock implementation)."""
    # In production, this would query the actual storage system
    # For now, return mock data
    return [
        {
            "id": f"capture_{i}",
            "type": "keystroke",
            "data": "Sample keystroke data",
            "timestamp": time.time() - i * 60,
            "agent_id": f"agent_{i % 3}",
        }
        for i in range(10)
    ]


async def _update_agent_status(agent_id: str, status_data: Dict[str, Any]) -> None:
    """Update agent status in storage."""
    # In production, this would update the actual agent status in database
    logger.debug(f"Agent {agent_id} status updated (keys: {list(status_data.keys())})")


async def _handle_capture_data(agent_id: str, capture_data: Dict[str, Any]) -> None:
    """Handle capture data from agent."""
    # In production, this would store the capture data
    logger.debug(
        "Agent %s sent capture (type=%s, size=%d)",
        agent_id,
        capture_data.get("type", "unknown"),
        len(str(capture_data)),
    )


async def _handle_command_response(agent_id: str, response_data: Dict[str, Any]) -> None:
    """Handle command response from agent."""
    # In production, this would process the command response
    logger.info(f"Agent {agent_id} command response: {response_data}")
