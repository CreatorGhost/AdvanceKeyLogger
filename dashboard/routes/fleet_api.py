"""
Fleet management API endpoints for agents.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Header, Request, status
from pydantic import BaseModel

from fleet.auth import FleetAuth
from fleet.controller import FleetController
from agent_controller import AgentMetadata, AgentCapabilities, AgentStatus, CommandStatus
from utils.crypto import verify_with_public_key

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


async def verify_signature(
    request: Request,
    x_signature: Optional[str] = Header(None, alias="X-Signature"),
    agent_id: str = Depends(verify_agent_token),
    controller: FleetController = Depends(get_controller),
) -> str:
    """Verify message signature if required by config.

    Returns the agent_id if verification passes.
    """
    # Check if signature verification is required
    config = getattr(request.app.state, "config", {})
    require_sig = (
        config.get("fleet", {}).get("security", {}).get("require_signature_verification", False)
    )

    if not require_sig:
        return agent_id

    if not x_signature:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing X-Signature header (signature verification enabled)",
        )

    # Get agent's public key from storage
    agent_data = controller.storage.get_agent(agent_id)
    if not agent_data or not agent_data.get("public_key"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Agent public key not found",
        )

    public_key_pem = agent_data["public_key"].encode("utf-8")

    # Get request body (already consumed, need to cache it)
    body = await request.body()

    # Decode signature (base64)
    try:
        signature = base64.b64decode(x_signature)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid signature encoding (expected base64)",
        )

    # Verify signature
    if not verify_with_public_key(public_key_pem, body, signature):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Signature verification failed",
        )

    logger.debug(f"Signature verified for agent {agent_id}")
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
    enrollment_key: Optional[str] = None  # Optional pre-shared key for enrollment validation


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

        # Build tags set, including enrollment key if provided
        # TODO: Validate enrollment key against a configured allow-list before
        # accepting the registration. Currently the key is stored but not verified.
        tags: set[str] = set()
        if req.enrollment_key:
            tags.add(f"enrollment_key:{req.enrollment_key}")

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
            tags=tags,
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
        raise HTTPException(status_code=500, detail="Registration failed") from e


@router.post("/heartbeat")
async def heartbeat(
    req: HeartbeatRequest,
    request: Request,
    agent_id: str = Depends(verify_agent_token),
    controller: FleetController = Depends(get_controller),
    x_signature: Optional[str] = Header(None, alias="X-Signature"),
):
    """Receive heartbeat from agent (optionally with signature verification)."""
    # Verify signature if required
    config = getattr(request.app.state, "config", {})
    require_sig = (
        config.get("fleet", {}).get("security", {}).get("require_signature_verification", False)
    )

    if require_sig:
        if not x_signature:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing X-Signature header (signature verification enabled)",
            )
        agent_data = controller.storage.get_agent(agent_id)
        if not agent_data or not agent_data.get("public_key"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Agent public key not found",
            )
        body = await request.body()
        try:
            signature = base64.b64decode(x_signature)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid signature encoding (expected base64)",
            )
        public_key_pem = agent_data["public_key"].encode("utf-8")
        if not verify_with_public_key(public_key_pem, body, signature):
            raise HTTPException(status_code=401, detail="Invalid signature")

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

    if queue:
        # Drain all available commands from the queue
        while True:
            try:
                priority, seq, cmd = queue.get_nowait()
            except asyncio.QueueEmpty:
                break

            commands.append(cmd.to_dict())

            # Update status to SENT (use .get() to guard against concurrent cleanup)
            tracked_cmd = controller.commands.get(cmd.command_id)
            if tracked_cmd is not None:
                tracked_cmd.status = CommandStatus.SENT
            controller.storage.update_command_status(cmd.command_id, "sent")

    # Also check DB for any pending commands that might have been loaded but not in queue?
    # (Memory queue should be source of truth for active controller)

    return {"commands": commands}


@router.post("/commands/{cmd_id}/response")
async def command_response(
    cmd_id: str,
    req: CommandResponseRequest,
    request: Request,
    agent_id: str = Depends(verify_agent_token),
    controller: FleetController = Depends(get_controller),
    x_signature: Optional[str] = Header(None, alias="X-Signature"),
):
    """Submit command execution result (optionally with signature verification)."""
    # Verify signature if required
    config = getattr(request.app.state, "config", {})
    require_sig = (
        config.get("fleet", {}).get("security", {}).get("require_signature_verification", False)
    )

    if require_sig:
        if not x_signature:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing X-Signature header (signature verification enabled)",
            )
        agent_data = controller.storage.get_agent(agent_id)
        if not agent_data or not agent_data.get("public_key"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Agent public key not found",
            )
        body = await request.body()
        try:
            signature = base64.b64decode(x_signature)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid signature encoding (expected base64)",
            )
        public_key_pem = agent_data["public_key"].encode("utf-8")
        if not verify_with_public_key(public_key_pem, body, signature):
            raise HTTPException(status_code=401, detail="Invalid signature")

    await controller.handle_command_response(agent_id, cmd_id, req.model_dump())
    return {"status": "received"}
