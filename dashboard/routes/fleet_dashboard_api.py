"""
Dashboard API for fleet management (used by UI).
"""

from __future__ import annotations

import logging
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Request, Body
from pydantic import BaseModel

from dashboard.auth import get_current_user
from fleet.controller import FleetController, CommandPriority

logger = logging.getLogger(__name__)

router = APIRouter(tags=["fleet_dashboard"])


# Dependency
def get_controller(request: Request) -> FleetController:
    if not getattr(request.app.state, "fleet_controller", None):
        raise HTTPException(503, "Fleet services unavailable")
    return request.app.state.fleet_controller


def get_current_user_api(request: Request) -> str:
    """Dependency to check auth for API routes."""
    user = get_current_user(request)
    if not user:
        raise HTTPException(401, "Not authenticated")
    return user


# Models
class AgentResponse(BaseModel):
    agent_id: str
    hostname: str
    platform: str
    version: str
    ip_address: str
    status: str
    last_seen: float
    capabilities: Dict[str, bool]


class CommandRequest(BaseModel):
    action: str
    parameters: Dict[str, Any] = {}
    priority: str = "NORMAL"


# Endpoints


@router.get("/agents")
async def list_agents(
    request: Request,
    user: str = Depends(get_current_user_api),
    controller: FleetController = Depends(get_controller),
):
    """List all registered agents."""
    agents = controller.get_all_agents()
    return {"agents": [a.to_dict() for a in agents]}


@router.get("/agents/{agent_id}")
async def get_agent(
    agent_id: str,
    user: str = Depends(get_current_user_api),
    controller: FleetController = Depends(get_controller),
):
    """Get agent details."""
    agent = controller.get_agent(agent_id)
    if not agent:
        raise HTTPException(404, "Agent not found")
    return agent.to_dict()


@router.post("/agents/{agent_id}/command")
async def send_command(
    agent_id: str,
    cmd: CommandRequest,
    user: str = Depends(get_current_user_api),
    controller: FleetController = Depends(get_controller),
):
    """Send command to agent."""
    try:
        priority = CommandPriority[cmd.priority.upper()]
    except KeyError:
        priority = CommandPriority.NORMAL

    cmd_id = await controller.send_command_async(agent_id, cmd.action, cmd.parameters, priority)

    if not cmd_id:
        raise HTTPException(400, "Failed to send command (agent offline or invalid)")

    return {"command_id": cmd_id, "status": "queued"}


@router.get("/agents/{agent_id}/commands")
async def get_agent_commands(
    agent_id: str,
    user: str = Depends(get_current_user_api),
    controller: FleetController = Depends(get_controller),
):
    """Get command history for agent."""
    commands = controller.get_agent_commands(agent_id)
    # Sort by timestamp desc
    commands.sort(key=lambda c: c.timestamp, reverse=True)
    return {"commands": [c.to_dict() for c in commands]}
