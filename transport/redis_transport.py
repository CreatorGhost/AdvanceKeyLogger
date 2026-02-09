"""
Redis transport module - re-exports RedisTransport from utils.redis_queue.

This file exists so the transport/__init__.py auto-import mechanism can find
and register the RedisTransport class. The actual implementation lives in
utils/redis_queue.py to keep the Redis queue utilities together.

IMPORT ORDER NOTE:
There is a circular import chain: transport/__init__.py -> transport/redis_transport.py
-> utils/redis_queue.py -> transport/__init__.py (for register_transport decorator).
This works because register_transport() is defined early in transport/__init__.py
(before the auto-import loop). If you refactor, ensure register_transport is available
before this module imports from utils.redis_queue.
"""

from utils.redis_queue import Message, MessagePriority, RedisQueue, RedisTransport

__all__ = ["RedisTransport", "RedisQueue", "Message", "MessagePriority"]
