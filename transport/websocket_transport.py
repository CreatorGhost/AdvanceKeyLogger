"""
WebSocket transport for real-time data streaming.

Provides persistent bidirectional communication between agents and the controller.
Supports automatic reconnection, compression, and heartbeat mechanisms.
"""

from __future__ import annotations

import asyncio
import base64
import gzip
import json
import logging
import ssl
import threading
import time
from typing import Any, Dict, Optional

import websockets
from transport import register_transport
from transport.base import BaseTransport

logger = logging.getLogger(__name__)


@register_transport("websocket")
class WebSocketTransport(BaseTransport):
    """WebSocket transport for real-time data streaming."""

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self._url = config.get("url")
        self._reconnect_interval = float(config.get("reconnect_interval", 5))
        self._heartbeat_interval = float(config.get("heartbeat_interval", 30))
        # Use None for websockets compression param; manual gzip is used in send/receive
        self._compression = None
        self._ssl_context = None
        self._websocket: Optional[Any] = None
        self._connected = False
        self._last_heartbeat = 0.0

        # Event loop for async operations
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None

        # SSL configuration
        if config.get("ssl", False):
            self._ssl_context = ssl.create_default_context()
            if config.get("verify_ssl", True):
                self._ssl_context.check_hostname = True
                self._ssl_context.verify_mode = ssl.CERT_REQUIRED
            else:
                self._ssl_context.check_hostname = False
                self._ssl_context.verify_mode = ssl.CERT_NONE

    def connect(self) -> None:
        """Establish WebSocket connection."""
        if not self._url:
            raise ValueError("WebSocket transport requires a URL")

        if self._connected:
            logger.debug("WebSocket already connected")
            return

        # Start async event loop in separate thread
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_async_loop, daemon=True)
        self._thread.start()

        # Wait for connection
        timeout = 10.0
        start_time = time.time()
        while not self._connected and time.time() - start_time < timeout:
            time.sleep(0.1)

        if not self._connected:
            raise ConnectionError(f"Failed to connect to WebSocket: {self._url}")

        logger.info(f"WebSocket connected: {self._url}")

    def _run_async_loop(self) -> None:
        """Run async event loop in separate thread."""
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._async_connect())
            self._loop.run_forever()
        except Exception as e:
            logger.error(f"Async loop failed: {e}")
            self._connected = False
        finally:
            try:
                self._loop.stop()
                self._loop.close()
            except Exception:
                pass

    async def _async_connect(self) -> None:
        """Async connection handler."""
        try:
            logger.info(f"Connecting to WebSocket: {self._url}")

            # Create connection
            self._websocket = await websockets.connect(
                self._url,
                ssl=self._ssl_context,
                max_queue=2**16,
                compression=self._compression,
                ping_interval=self._heartbeat_interval,
                ping_timeout=10.0,
            )

            self._connected = True
            self._last_heartbeat = time.time()

            # Start receive task
            asyncio.create_task(self._receive_loop())

        except Exception as e:
            logger.error(f"Failed to connect WebSocket: {e}")
            self._connected = False

    def disconnect(self) -> None:
        """Close WebSocket connection."""
        if not self._connected:
            return

        try:
            if self._loop and self._websocket:
                future = asyncio.run_coroutine_threadsafe(self._websocket.close(), self._loop)
                future.result(timeout=5.0)

            self._connected = False
            self._websocket = None

            # Stop event loop
            if self._loop:
                self._loop.call_soon_threadsafe(self._loop.stop)

            # Wait for thread to finish
            if self._thread:
                self._thread.join(timeout=5.0)

            logger.info("WebSocket disconnected")

        except Exception as e:
            logger.error(f"Error disconnecting WebSocket: {e}")

    def send(self, data: bytes, metadata: dict[str, Any] | None = None) -> bool:
        """Send data through WebSocket."""
        if not self._connected or not self._loop:
            self.connect()

        if not self._connected or not self._websocket:
            return False

        try:
            # Prepare message — handle binary data safely
            if metadata is None:
                metadata = {}
            if isinstance(data, bytes):
                try:
                    data_str = data.decode("utf-8")
                except UnicodeDecodeError:
                    data_str = base64.b64encode(data).decode("ascii")
                    metadata["encoding"] = "base64"
            else:
                data_str = data

            message = {
                "timestamp": time.time(),
                "data": data_str,
                "metadata": metadata,
            }

            # Serialize and compress (manual gzip)
            serialized = json.dumps(message).encode()
            serialized = gzip.compress(serialized)

            # Send message using event loop
            future = asyncio.run_coroutine_threadsafe(self._websocket.send(serialized), self._loop)
            future.result(timeout=10.0)

            logger.debug(f"Sent {len(serialized)} bytes via WebSocket")
            return True

        except websockets.ConnectionClosed:
            logger.warning("WebSocket connection closed")
            self._connected = False
            return False
        except Exception as e:
            logger.error(f"Failed to send WebSocket message: {e}")
            self._connected = False
            return False

    async def _receive_loop(self) -> None:
        """Receive messages from WebSocket."""
        while self._connected and self._websocket:
            try:
                # Receive message
                message = await self._websocket.recv()

                # Decompress (manual gzip matching send path)
                message = gzip.decompress(message)

                # Parse JSON
                data = json.loads(message)

                # Handle received message
                self.logger.debug(f"Received message: {data}")

                # TODO: Process received messages (e.g., commands from controller)

            except websockets.ConnectionClosed:
                logger.warning("WebSocket connection closed during receive")
                self._connected = False
                break
            except Exception as e:
                logger.error(f"Receive error: {e}")
                await asyncio.sleep(1)

    @property
    def is_connected(self) -> bool:
        """Check if WebSocket is connected."""
        return self._connected and self._websocket is not None
