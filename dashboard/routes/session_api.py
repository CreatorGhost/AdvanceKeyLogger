"""
REST API endpoints for Session Recording & Replay.

Provides endpoints for listing sessions, fetching timeline data,
serving frame images, and controlling recording.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse

from dashboard.auth import get_current_user

logger = logging.getLogger(__name__)

session_api_router = APIRouter(prefix="/api/sessions", tags=["sessions"])


def _require_auth(request: Request) -> None:
    if get_current_user(request) is None:
        raise HTTPException(status_code=401, detail="Not authenticated")


def _get_store(request: Request):
    """Retrieve the SessionStore from app state (set during lifespan)."""
    store = getattr(request.app.state, "session_store", None)
    if store is None:
        raise HTTPException(status_code=503, detail="Session recording not available")
    return store


# ------------------------------------------------------------------
# Session listing
# ------------------------------------------------------------------

@session_api_router.get("")
async def list_sessions(
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    status: str | None = Query(default=None),
) -> dict[str, Any]:
    """List recorded sessions, newest first."""
    _require_auth(request)
    store = _get_store(request)
    sessions = store.list_sessions(limit=limit, status=status)

    # Enrich with thumbnail URL
    for s in sessions:
        if s.get("thumbnail"):
            s["thumbnail_url"] = f"/api/sessions/{s['id']}/frames/0"
        else:
            s["thumbnail_url"] = None

    return {"sessions": sessions, "total": len(sessions)}


@session_api_router.get("/stats")
async def session_stats(request: Request) -> dict[str, Any]:
    """Return aggregate recording statistics."""
    _require_auth(request)
    store = _get_store(request)
    return store.get_stats()


# ------------------------------------------------------------------
# Single session detail
# ------------------------------------------------------------------

@session_api_router.get("/{session_id}")
async def get_session(request: Request, session_id: str) -> dict[str, Any]:
    """Return session metadata."""
    _require_auth(request)
    store = _get_store(request)
    session = store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@session_api_router.get("/{session_id}/timeline")
async def get_timeline(request: Request, session_id: str) -> dict[str, Any]:
    """Return the full timeline: session metadata + all frames + all events.

    This is the primary endpoint the replay player uses.
    """
    _require_auth(request)
    store = _get_store(request)
    timeline = store.get_timeline(session_id)
    if not timeline:
        raise HTTPException(status_code=404, detail="Session not found")

    # Add frame URLs for the player
    for frame in timeline.get("frames", []):
        frame["url"] = f"/api/sessions/{session_id}/frames/{frame['id']}"

    return timeline


# ------------------------------------------------------------------
# Frame serving
# ------------------------------------------------------------------

@session_api_router.get("/{session_id}/frames/{frame_id}")
async def get_frame(request: Request, session_id: str, frame_id: int) -> FileResponse:
    """Serve a session frame image by ID."""
    _require_auth(request)
    store = _get_store(request)

    frames = store.get_frames(session_id)
    if not frames:
        raise HTTPException(status_code=404, detail="Session not found")

    # frame_id=0 means "first frame" (thumbnail)
    if frame_id == 0:
        frame = frames[0]
    else:
        frame = None
        for f in frames:
            if f["id"] == frame_id:
                frame = f
                break
        if frame is None:
            raise HTTPException(status_code=404, detail="Frame not found")

    file_path = Path(frame["file_path"])
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Frame file not found on disk")

    # Path traversal protection — validate against configured frames directory
    recorder = getattr(request.app.state, "session_recorder", None)
    if recorder is not None:
        frames_dir = recorder.frames_dir
    else:
        # Fallback: read frames_dir from app config (same default as SessionRecorder)
        cfg = getattr(request.app.state, "config", {})
        frames_dir = Path(cfg.get("recording", {}).get("frames_dir", "./data/sessions/frames"))
    try:
        file_path.resolve().relative_to(frames_dir.resolve())
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="Access denied") from exc

    media_type = "image/jpeg"
    if file_path.suffix.lower() == ".png":
        media_type = "image/png"

    return FileResponse(
        path=str(file_path),
        media_type=media_type,
        headers={"Cache-Control": "public, max-age=3600"},
    )


# ------------------------------------------------------------------
# Events
# ------------------------------------------------------------------

@session_api_router.get("/{session_id}/events")
async def get_events(
    request: Request,
    session_id: str,
    event_type: str | None = Query(default=None),
) -> dict[str, Any]:
    """Return events for a session, optionally filtered by type."""
    _require_auth(request)
    store = _get_store(request)
    events = store.get_events(session_id, event_type=event_type)
    return {"events": events, "total": len(events)}


# ------------------------------------------------------------------
# Recording control
# ------------------------------------------------------------------

@session_api_router.post("/start")
async def start_recording(request: Request) -> dict[str, Any]:
    """Start a new recording session (if a recorder is attached)."""
    _require_auth(request)
    recorder = getattr(request.app.state, "session_recorder", None)
    if recorder is None:
        raise HTTPException(status_code=503, detail="Session recorder not available")
    if recorder.is_recording:
        return {"status": "already_recording", "session_id": recorder.session_id}
    session_id = recorder.start_session()
    return {"status": "started", "session_id": session_id}


@session_api_router.post("/stop")
async def stop_recording(request: Request) -> dict[str, Any]:
    """Stop the current recording session."""
    _require_auth(request)
    recorder = getattr(request.app.state, "session_recorder", None)
    if recorder is None:
        raise HTTPException(status_code=503, detail="Session recorder not available")
    if not recorder.is_recording:
        return {"status": "not_recording"}
    session_id = recorder.session_id
    recorder.stop_session()
    return {"status": "stopped", "session_id": session_id}


@session_api_router.get("/recorder/status")
async def recorder_status(request: Request) -> dict[str, Any]:
    """Return current recorder status."""
    _require_auth(request)
    recorder = getattr(request.app.state, "session_recorder", None)
    if recorder is None:
        return {"enabled": False, "recording": False}
    return recorder.get_status()


# ------------------------------------------------------------------
# Deletion
# ------------------------------------------------------------------

@session_api_router.delete("/{session_id}")
async def delete_session(request: Request, session_id: str) -> dict[str, Any]:
    """Delete a session and all its data."""
    _require_auth(request)
    store = _get_store(request)
    session = store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    store.delete_session(session_id)
    return {"status": "deleted", "session_id": session_id}
