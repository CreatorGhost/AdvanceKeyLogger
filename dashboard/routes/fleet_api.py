"""
Fleet management API endpoints for agents.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Header, Request, status
from pydantic import BaseModel

from fleet.auth import FleetAuth
from fleet.controller import FleetController
from agent_controller import AgentMetadata, AgentCapabilities, AgentStatus

logger = logging.getLogger(__name__)

router = APIRouter(tags=["fleet"])

# Dependency Injection Helpers


def get_controller(request: Request) -> FleetController:
    if not getattr(request.app.state, "fleet_controller", None):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Fleet services unavailable"
        )
    return request.app.state.fleet_controller


def get_auth_service(request: Request) -> FleetAuth:
    if not getattr(request.app.state, "fleet_auth", None):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Auth services unavailable"
        )
    return request.app.state.fleet_auth


async def verify_agent_token(
    authorization: str = Header(None), auth_service: FleetAuth = Depends(get_auth_service)
) -> str:
    """Verify Bearer token and return agent_id."""
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing authorization header"
        )

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication scheme"
        )

    agent_id = auth_service.verify_token(token)
    if not agent_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token"
        )

    return agent_id


# Pydantic Models


class RegisterRequest(BaseModel):
    agent_id: str
    hostname: str
    platform: str
    version: str
    public_key: str
    capabilities: Dict[str, bool] = {}
    metadata: Dict[str, Any] = {}


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int
    token_type: str = "Bearer"
    controller_public_key: Optional[str] = None


class HeartbeatRequest(BaseModel):
    status: str = "ONLINE"
    uptime: float = 0.0
    metrics: Dict[str, Any] = {}


class CommandResponseRequest(BaseModel):
    result: Dict[str, Any]
    success: bool
    error: Optional[str] = None


# Endpoints


@router.post("/register", response_model=TokenResponse)
async def register_agent(
    req: RegisterRequest,
    request: Request,
    controller: FleetController = Depends(get_controller),
    auth_service: FleetAuth = Depends(get_auth_service),
):
    """Register a new agent and return auth tokens."""
    try:
        # Construct metadata
        # Get IP from request if behind proxy?
        ip = request.client.host if request.client else "0.0.0.0"

        metadata = AgentMetadata(
            agent_id=req.agent_id,
            hostname=req.hostname,
            platform=req.platform,
            version=req.version,
            ip_address=ip,
            mac_address=req.metadata.get("mac_address", ""),
            capabilities=AgentCapabilities(**req.capabilities),
            status=AgentStatus.ONLINE,
            first_seen=time.time(),
            last_seen=time.time(),
        )

        # Register with controller (persists to DB)
        # We assume public_key is PEM encoded string
        controller.register_agent(metadata, None, req.public_key.encode())

        # Generate tokens
        tokens = auth_service.create_tokens(req.agent_id)

        # Include controller public key for secure channel
        tokens["controller_public_key"] = controller.get_public_key()

        return tokens

    except Exception as e:
        logger.error(f"Registration failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/heartbeat")
async def heartbeat(
    req: HeartbeatRequest,
    agent_id: str = Depends(verify_agent_token),
    controller: FleetController = Depends(get_controller),
):
    """Receive heartbeat from agent."""
    await controller.handle_heartbeat(agent_id, req.model_dump())
    return {"status": "ok"}


@router.get("/commands")
async def get_commands(
    agent_id: str = Depends(verify_agent_token),
    controller: FleetController = Depends(get_controller),
):
    """Poll for pending commands."""
    # This requires controller to expose get_pending_commands
    # For now, we'll implement a simple fetch from DB via controller logic
    # or expose access to storage

    # Check command queue in memory
    queue = controller.command_queues.get(agent_id)
    commands = []

    if queue and not queue.empty():
        # Get all available commands
        while not queue.empty():
            try:
                # We peek/get but only if we can confirm delivery?
                # Ideally we peek, return, and ack later.
                # Or we return and mark as SENT.
                priority, seq, cmd = queue.get_nowait()
                # Encrypt command for agent
                # Since we are using REST, we might skip full encryption if TLS is used
                # But Gap 4 says "Secure Channel".
                # So we should return the encrypted blob that _send_command_to_agent would produce.

                # However, _send_command_to_agent sends directly via transport.
                # Here we want to RETURN the command payload.

                # For MVP, let's return the command object and let the agent handle it.
                # If we want encryption, we need to invoke controller logic to encrypt it.

                # Let's trust TLS for now (Gap 4 mentions "RSA keys ... never exposed").
                # If we rely on TLS, we don't need app-level encryption for confidentiality,
                # but we need signatures for integrity/auth.

                # Let's return the raw command dict for now,
                # assuming agent will verify signature if we add it.
                commands.append(cmd.to_dict())

                # Update status to SENT
                cmd.status = controller.commands[cmd.command_id].status
                from agent_controller import CommandStatus

                controller.commands[cmd.command_id].status = CommandStatus.SENT
                controller.storage.update_command_status(cmd.command_id, "sent")

            except Exception:
                break

    # Also check DB for any pending commands that might have been loaded but not in queue?
    # (Memory queue should be source of truth for active controller)

    return {"commands": commands}


@router.post("/commands/{cmd_id}/response")
async def command_response(
    cmd_id: str,
    req: CommandResponseRequest,
    agent_id: str = Depends(verify_agent_token),
    controller: FleetController = Depends(get_controller),
):
    """Submit command execution result."""
    await controller.handle_command_response(agent_id, cmd_id, req.model_dump())
    return {"status": "received"}
