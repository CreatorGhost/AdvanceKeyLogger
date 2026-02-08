"""FastAPI collector for E2E envelopes."""
from __future__ import annotations

import json
from typing import Any

from fastapi import FastAPI, Request, HTTPException

from crypto.envelope import Envelope, HybridEnvelope
from server.keys import load_server_private_key
from server.storage import store_payload


def create_app(config: dict[str, Any]) -> FastAPI:
    app = FastAPI()
    server_private = load_server_private_key(config)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/ingest")
    async def ingest(request: Request) -> dict[str, Any]:
        body = await request.body()
        if not body:
            raise HTTPException(status_code=400, detail="empty payload")
        try:
            envelope = Envelope.from_bytes(body)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"invalid envelope: {exc}")

        try:
            payload = HybridEnvelope.decrypt(envelope, server_private)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"decrypt failed: {exc}")

        path = store_payload(payload, config)
        return {
            "status": "stored",
            "path": str(path),
            "bytes": len(payload),
        }

    return app
