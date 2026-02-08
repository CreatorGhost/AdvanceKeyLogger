"""
Resilience patterns: retry decorator, transport queue, and circuit breaker.

These patterns prevent data loss on transient failures and protect
against hammering broken services.

Usage:
    from utils.resilience import retry, TransportQueue, CircuitBreaker

    @retry(max_attempts=3, backoff_base=2.0)
    def send_data(payload):
        ...

    queue = TransportQueue(max_size=1000)
    queue.enqueue({"type": "screenshot", "data": ...})
    batch = queue.drain(batch_size=50)

    breaker = CircuitBreaker(failure_threshold=5, cooldown=60)
    if breaker.can_proceed():
        try:
            send_data(payload)
            breaker.record_success()
        except Exception:
            breaker.record_failure()
"""
from __future__ import annotations

import functools
import logging
import time
from collections import deque
from typing import Any

logger = logging.getLogger(__name__)


def retry(
    max_attempts: int = 3,
    backoff_base: float = 2.0,
    exceptions: tuple[type[Exception], ...] = (Exception,),
):
    """
    Decorator that retries a function with exponential backoff.

    Args:
        max_attempts: Maximum number of attempts before giving up.
        backoff_base: Base for exponential wait (wait = base ** attempt).
        exceptions: Tuple of exception types to catch and retry on.

    Example:
        @retry(max_attempts=3, backoff_base=2.0)
        def send_email(msg):
            smtp.send(msg)

        # Will try up to 3 times: immediately, then after 1s, then after 2s.
    """

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    if attempt == max_attempts - 1:
                        logger.error(
                            "%s failed after %d attempts: %s",
                            func.__name__,
                            max_attempts,
                            e,
                        )
                        raise
                    wait_time = backoff_base**attempt
                    logger.warning(
                        "%s attempt %d/%d failed, retrying in %.1fs: %s",
                        func.__name__,
                        attempt + 1,
                        max_attempts,
                        wait_time,
                        e,
                    )
                    time.sleep(wait_time)

        return wrapper

    return decorator


class TransportQueue:
    """
    Queue captured data for transport with automatic retry on failure.

    If transport fails, data stays in the queue for the next cycle,
    preventing data loss on transient failures.
    """

    def __init__(self, max_size: int = 1000) -> None:
        self._queue: deque[dict[str, Any]] = deque(maxlen=max_size)

    def enqueue(self, item: dict[str, Any]) -> None:
        """Add an item to the transport queue."""
        self._queue.append(item)

    def enqueue_many(self, items: list[dict[str, Any]]) -> None:
        """Add multiple items to the transport queue."""
        self._queue.extend(items)

    def drain(self, batch_size: int = 50) -> list[dict[str, Any]]:
        """
        Remove and return up to batch_size items from the queue.

        Items are removed from the front (oldest first).
        """
        batch = []
        for _ in range(min(batch_size, len(self._queue))):
            batch.append(self._queue.popleft())
        return batch

    def requeue(self, items: list[dict[str, Any]]) -> None:
        """
        Put items back at the front of the queue (after a failed transport).

        Items are re-inserted in their original order.
        """
        self._queue.extendleft(reversed(items))
        logger.warning("Re-queued %d items for retry", len(items))

    @property
    def size(self) -> int:
        """Number of items currently in the queue."""
        return len(self._queue)

    @property
    def is_empty(self) -> bool:
        return len(self._queue) == 0


class CircuitBreaker:
    """
    Prevent hammering a broken service.

    After N consecutive failures, "opens" the circuit (blocks requests)
    for a cooldown period. Then allows one test request through.

    States:
        CLOSED    -> Normal operation, requests go through.
        OPEN      -> Failures exceeded threshold, requests blocked.
        HALF_OPEN -> Cooldown expired, one test request allowed.
    """

    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"

    def __init__(self, failure_threshold: int = 5, cooldown: float = 60.0) -> None:
        self.failure_threshold = failure_threshold
        self.cooldown = cooldown
        self._failures = 0
        self._last_failure_time = 0.0
        self._state = self.CLOSED

    @property
    def state(self) -> str:
        """Current circuit state."""
        return self._state

    def can_proceed(self) -> bool:
        """
        Check if a request should be allowed through.

        Returns:
            True if the request can proceed, False if circuit is open.
        """
        if self._state == self.CLOSED:
            return True
        if self._state == self.OPEN:
            if time.time() - self._last_failure_time > self.cooldown:
                self._state = self.HALF_OPEN
                logger.info("Circuit half-open, allowing test request")
                return True
            return False
        # HALF_OPEN — allow one test request
        return True

    def record_success(self) -> None:
        """Record a successful request. Resets failure count and closes circuit."""
        self._failures = 0
        if self._state == self.HALF_OPEN:
            self._state = self.CLOSED
            logger.info("Circuit closed (service recovered)")

    def record_failure(self) -> None:
        """Record a failed request. Opens circuit if threshold exceeded."""
        self._failures += 1
        self._last_failure_time = time.time()
        if self._failures >= self.failure_threshold:
            self._state = self.OPEN
            logger.warning(
                "Circuit opened after %d consecutive failures (cooldown: %.0fs)",
                self._failures,
                self.cooldown,
            )
