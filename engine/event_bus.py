"""
Simple pub/sub event bus for capture events.
"""
from __future__ import annotations

import logging
import threading
from collections import defaultdict
from typing import Any, Callable

logger = logging.getLogger(__name__)

Event = dict[str, Any]
Handler = Callable[[Event], None]


class EventBus:
    """In-process event bus with topic routing."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subscribers: dict[str, list[Handler]] = defaultdict(list)

    def subscribe(self, topic: str, handler: Handler) -> None:
        """Subscribe a handler to a topic ("*" for all)."""
        with self._lock:
            self._subscribers[topic].append(handler)

    def publish(self, topic: str, event: Event) -> None:
        """Publish an event to a topic."""
        handlers = []
        with self._lock:
            handlers.extend(self._subscribers.get(topic, []))
            handlers.extend(self._subscribers.get("*", []))
        for handler in handlers:
            try:
                handler(event)
            except Exception as exc:
                logger.error("EventBus handler failed for topic '%s': %s", topic, exc)
