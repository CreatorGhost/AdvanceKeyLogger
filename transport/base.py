"""
Abstract base class for all transport (data delivery) modules.

Every transport module (email, HTTP, FTP, Telegram) must inherit
from BaseTransport and implement connect(), send(), and disconnect().

Usage:
    class MyTransport(BaseTransport):
        def connect(self) -> None: ...
        def send(self, data: bytes, metadata: dict) -> bool: ...
        def disconnect(self) -> None: ...
"""
from __future__ import annotations

from abc import ABC, abstractmethod
import logging
from typing import Any


class BaseTransport(ABC):
    """Abstract base class that all transport modules must implement."""

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.logger = logging.getLogger(self.__class__.__name__)
        self._connected = False

    @abstractmethod
    def connect(self) -> None:
        """
        Establish connection to the transport endpoint.

        Called before send(). May be a no-op for stateless transports.
        Set self._connected = True on success.
        """

    @abstractmethod
    def send(self, data: bytes, metadata: dict[str, Any] | None = None) -> bool:
        """
        Send data through this transport.

        Args:
            data: The bytes to send (may be compressed/encrypted).
            metadata: Optional dict with context like filenames, types, etc.

        Returns:
            True if send succeeded, False otherwise.
        """

    @abstractmethod
    def disconnect(self) -> None:
        """
        Close connection and clean up resources.

        Called on shutdown. Set self._connected = False.
        """

    @property
    def is_connected(self) -> bool:
        """Whether the transport has an active connection."""
        return self._connected

    def __enter__(self) -> BaseTransport:
        self.connect()
        return self

    def __exit__(self, *args: Any) -> None:
        self.disconnect()

    def __repr__(self) -> str:
        status = "connected" if self._connected else "disconnected"
        return f"<{self.__class__.__name__} ({status})>"
