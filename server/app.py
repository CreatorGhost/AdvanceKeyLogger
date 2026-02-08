"""FastAPI collector for E2E envelopes."""
from __future__ import annotations

import base64
import logging
import threading
from typing import Any

from fastapi import FastAPI, Request, HTTPException

from crypto.envelope import Envelope, HybridEnvelope, compute_envelope_id
from server.audit import get_audit_logger
from server.auth import is_authorized
from server.clients import ClientRegistry
from server.keys import load_server_private_keys
from server.rate_limit import RateLimiter
from server.replay import ReplayCache
from server.storage import store_payload

logger = logging.getLogger(__name__)


def create_app(config: dict[str, Any]) -> FastAPI:
    app = FastAPI()
    server_keys = load_server_private_keys(config)
    audit_logger = get_audit_logger(config)

    auth_tokens = list(config.get("auth_tokens", []))
    registration_tokens = list(config.get("registration_tokens", []))
    allowed_client_keys = list(config.get("allowed_client_keys", []))
    clients_file = config.get("clients_file")

    registry = ClientRegistry(allowed_client_keys, clients_file)
    rate_limiter = RateLimiter(int(config.get("rate_limit_per_minute", 60)))
    replay_cache = ReplayCache(
        ttl_seconds=int(config.get("replay_ttl_seconds", 3600)),
        max_entries=int(config.get("replay_cache_max", 10000)),
    )
    max_payload = int(config.get("max_payload_bytes", 10 * 1024 * 1024))
    last_sequences: dict[str, int] = {}
    seq_lock = threading.Lock()

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/register")
    async def register_client(request: Request) -> dict[str, Any]:
        if registration_tokens and not is_authorized(request, registration_tokens):
            raise HTTPException(status_code=401, detail="unauthorized")
        try:
            data = await request.json()
        except (ValueError, KeyError):
            raise HTTPException(status_code=400, detail="invalid or missing JSON body")
        key_b64 = str(data.get("sender_public_key", "")).strip()
        if not key_b64:
            raise HTTPException(status_code=400, detail="missing sender_public_key")
        try:
            raw_key = base64.b64decode(key_b64)
            if len(raw_key) != 32:
                raise ValueError("key must be 32 bytes")
        except Exception:
            raise HTTPException(status_code=400, detail="invalid public key format")
        registry.register(key_b64)
        audit_logger.info("client_registered key=%s", _truncate(key_b64))
        return {"status": "registered"}

    @app.post("/ingest")
    async def ingest(request: Request) -> dict[str, Any]:
        client_ip = request.client.host if request.client else "unknown"

        if not rate_limiter.allow(client_ip):
            raise HTTPException(status_code=429, detail="rate limit exceeded")

        if auth_tokens and not is_authorized(request, auth_tokens):
            raise HTTPException(status_code=401, detail="unauthorized")

        content_length = request.headers.get("Content-Length")
        if content_length:
            try:
                if int(content_length) > max_payload:
                    raise HTTPException(status_code=413, detail="payload too large")
            except ValueError:
                pass

        body = await _read_body_limited(request, max_payload)
        if not body:
            raise HTTPException(status_code=400, detail="empty payload")

        try:
            envelope = Envelope.from_bytes(body)
        except Exception as exc:
            audit_logger.warning("invalid_envelope ip=%s error=%s", client_ip, exc)
            raise HTTPException(status_code=400, detail=f"invalid envelope: {exc}")

        sender_key_b64 = base64.b64encode(envelope.sender_public_key).decode("utf-8")
        truncated_sender = _truncate(sender_key_b64)
        if not registry.is_allowed(sender_key_b64):
            audit_logger.warning(
                "unauthorized_sender ip=%s key=%s",
                client_ip,
                truncated_sender,
            )
            raise HTTPException(status_code=403, detail="sender not allowed")

        envelope_id = envelope.envelope_id or compute_envelope_id(envelope)
        if replay_cache.seen(envelope_id):
            audit_logger.warning("replay_detected ip=%s id=%s", client_ip, envelope_id)
            raise HTTPException(status_code=409, detail="replay detected")

        if envelope.sequence is not None:
            with seq_lock:
                last = last_sequences.get(sender_key_b64)
                if last is not None and envelope.sequence <= last:
                    audit_logger.warning(
                        "sequence_replay ip=%s key=%s seq=%d last=%d",
                        client_ip,
                        _truncate(sender_key_b64),
                        envelope.sequence,
                        last,
                    )
                    raise HTTPException(status_code=409, detail="sequence replay")
                if last is not None and envelope.sequence > last + 1:
                    audit_logger.info(
                        "sequence_gap ip=%s key=%s last=%d current=%d",
                        client_ip,
                        _truncate(sender_key_b64),
                        last,
                        envelope.sequence,
                    )
                last_sequences[sender_key_b64] = envelope.sequence

        payload = None
        decrypt_error = None
        for key in server_keys:
            try:
                payload = HybridEnvelope.decrypt(envelope, key)
                break
            except Exception as exc:
                decrypt_error = exc
                continue
        if payload is None:
            audit_logger.warning("decrypt_failed ip=%s error=%s", client_ip, decrypt_error)
            raise HTTPException(status_code=400, detail=f"decrypt failed: {decrypt_error}")

        path = store_payload(payload, config)
        audit_logger.info(
            "ingest_ok ip=%s key=%s bytes=%d file=%s",
            client_ip,
            _truncate(sender_key_b64),
            len(payload),
            path.name,
        )
        return {
            "status": "stored",
            "bytes": len(payload),
            "envelope_id": envelope_id,
            "filename": path.name,
        }

    return app


async def _read_body_limited(request: Request, max_bytes: int) -> bytes:
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > max_bytes:
            raise HTTPException(status_code=413, detail="payload too large")
    return bytes(body)


def _truncate(value: str, limit: int = 12) -> str:
    if len(value) <= limit:
        return value
    return value[:limit] + "..."
