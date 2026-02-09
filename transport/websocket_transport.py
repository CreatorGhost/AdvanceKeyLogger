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


from typing import Callable

# Type alias for message handlers
MessageHandler = Callable[[Dict[str, Any]], None]


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

        # Message handlers for received messages
        self._message_handlers: Dict[str, MessageHandler] = {}
        self._default_handler: Optional[MessageHandler] = None

        # Message queue for receive() method (created lazily when event loop exists)
        self._receive_queue: Optional[asyncio.Queue[bytes]] = None

        # SSL configuration
        if config.get("ssl", False):
            self._ssl_context = ssl.create_default_context()
            if config.get("verify_ssl", True):
                self._ssl_context.check_hostname = True
                self._ssl_context.verify_mode = ssl.CERT_REQUIRED
            else:
                self._ssl_context.check_hostname = False
                self._ssl_context.verify_mode = ssl.CERT_NONE

    def register_handler(self, message_type: str, handler: MessageHandler) -> None:
        """Register a handler for a specific message type."""
        self._message_handlers[message_type] = handler
        logger.debug(f"Registered handler for message type: {message_type}")

    def set_default_handler(self, handler: MessageHandler) -> None:
        """Set a default handler for unhandled message types."""
        self._default_handler = handler

    def receive(self, timeout: float = 5.0) -> Optional[bytes]:
        """Receive a message from the queue (blocking, for sync callers)."""
        if not self._loop or not self._receive_queue:
            return None
        try:
            future = asyncio.run_coroutine_threadsafe(
                asyncio.wait_for(self._receive_queue.get(), timeout=timeout),
                self._loop,
            )
            return future.result(timeout=timeout + 1)
        except (asyncio.TimeoutError, TimeoutError):
            return None
        except Exception as e:
            logger.debug(f"Receive failed: {e}")
            return None

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
        loop = self._loop
        if loop is None:
            logger.error("Event loop not initialized")
            return
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._async_connect())
            loop.run_forever()
        except Exception as e:
            logger.error(f"Async loop failed: {e}")
            self._connected = False
        finally:
            try:
                loop.stop()
                loop.close()
            except Exception:
                pass

    async def _async_connect(self) -> None:
        """Async connection handler."""
        try:
            url = self._url
            if not url:
                raise ValueError("WebSocket URL not configured")
            logger.info(f"Connecting to WebSocket: {url}")

            # Create message queue now that event loop is running
            if self._receive_queue is None:
                self._receive_queue = asyncio.Queue()

            # Create connection
            self._websocket = await websockets.connect(
                url,
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
            loop = self._loop
            ws = self._websocket
            if loop is None or ws is None:
                raise ConnectionError("WebSocket not connected")
            future = asyncio.run_coroutine_threadsafe(ws.send(serialized), loop)
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
        """Receive messages from WebSocket and dispatch to handlers."""
        while self._connected and self._websocket:
            try:
                # Receive message
                raw_message = await self._websocket.recv()

                # Decompress (manual gzip matching send path)
                decompressed = gzip.decompress(raw_message)

                # Parse JSON
                data = json.loads(decompressed)

                logger.debug(f"Received message: {data}")

                # Put raw bytes in queue for receive() method
                if self._receive_queue:
                    await self._receive_queue.put(decompressed)

                # Dispatch to registered handlers
                msg_type = data.get("type") if isinstance(data, dict) else None

                if msg_type and msg_type in self._message_handlers:
                    try:
                        self._message_handlers[msg_type](data)
                    except Exception as e:
                        logger.error(f"Handler error for {msg_type}: {e}")
                elif self._default_handler:
                    try:
                        self._default_handler(data)
                    except Exception as e:
                        logger.error(f"Default handler error: {e}")
                else:
                    logger.debug(f"No handler for message type: {msg_type}")

            except websockets.ConnectionClosed:
                logger.warning("WebSocket connection closed during receive")
                self._connected = False
                break
            except gzip.BadGzipFile:
                # Message wasn't compressed, try parsing directly
                # raw_message is guaranteed to be bound here since BadGzipFile
                # can only be raised after gzip.decompress(raw_message) was called
                try:
                    uncompressed_data = json.loads(raw_message)  # type: ignore[possibly-undefined]
                    raw_bytes = (
                        raw_message  # type: ignore[possibly-undefined]
                        if isinstance(raw_message, bytes)  # type: ignore[possibly-undefined]
                        else raw_message.encode()  # type: ignore[possibly-undefined]
                    )
                    if self._receive_queue:
                        await self._receive_queue.put(raw_bytes)
                    uc_msg_type = (
                        uncompressed_data.get("type")
                        if isinstance(uncompressed_data, dict)
                        else None
                    )
                    if uc_msg_type and uc_msg_type in self._message_handlers:
                        self._message_handlers[uc_msg_type](uncompressed_data)
                    elif self._default_handler:
                        self._default_handler(uncompressed_data)
                except Exception as e:
                    logger.error(f"Failed to parse uncompressed message: {e}")
            except Exception as e:
                logger.error(f"Receive error: {e}")
                await asyncio.sleep(1)

    @property
    def is_connected(self) -> bool:
        """Check if WebSocket is connected."""
        return self._connected and self._websocket is not None
