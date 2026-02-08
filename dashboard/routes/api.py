"""REST API routes for dashboard data."""
from __future__ import annotations

import asyncio
import os
import platform
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from dashboard.auth import get_current_user

try:
    import psutil

    _proc = psutil.Process(os.getpid())
except ImportError:
    psutil = None  # type: ignore[assignment]
    _proc = None

api_router = APIRouter(tags=["api"])

_start_time = time.time()


def _require_api_auth(request: Request) -> None:
    """Raise 401 if not authenticated."""
    if get_current_user(request) is None:
        raise HTTPException(status_code=401, detail="Not authenticated")


@api_router.get("/health")
async def health() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok", "timestamp": datetime.now().isoformat()}


@api_router.get("/status")
async def system_status(request: Request) -> dict[str, Any]:
    """System status overview."""
    _require_api_auth(request)

    uptime = time.time() - _start_time
    hours, remainder = divmod(int(uptime), 3600)
    minutes, seconds = divmod(remainder, 60)

    # CPU / memory (safely degraded when psutil unavailable)
    cpu_pct = 0.0
    mem_mb = 0.0
    if _proc is not None:
        cpu_pct = await asyncio.to_thread(_proc.cpu_percent, 0.1)
        mem_mb = round(_proc.memory_info().rss / 1024 / 1024, 1)

    # Check storage
    data_dir = Path("data")
    storage_used = (
        sum(f.stat().st_size for f in data_dir.rglob("*") if f.is_file())
        if data_dir.exists()
        else 0
    )

    # Check SQLite
    db_path = Path("data/captures.db")
    db_size = db_path.stat().st_size if db_path.exists() else 0
    pending_count = 0
    total_count = 0
    if db_path.exists():
        try:
            from storage.sqlite_storage import SQLiteStorage

            with SQLiteStorage(str(db_path)) as db:
                pending_count = db.count_pending()
                total_count = db.count_total()
        except Exception:
            pass

    return {
        "uptime": f"{hours}h {minutes}m {seconds}s",
        "uptime_seconds": int(uptime),
        "system": {
            "hostname": platform.node(),
            "os": f"{platform.system()} {platform.release()}",
            "python": platform.python_version(),
            "cpu_percent": cpu_pct,
            "memory_mb": mem_mb,
        },
        "storage": {
            "data_dir_bytes": storage_used,
            "data_dir_mb": round(storage_used / 1024 / 1024, 2),
            "db_size_bytes": db_size,
            "db_size_mb": round(db_size / 1024 / 1024, 2),
        },
        "captures": {
            "total": total_count,
            "pending": pending_count,
            "sent": total_count - pending_count,
        },
    }


@api_router.get("/captures")
async def list_captures(
    request: Request,
    capture_type: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    """List captured data from SQLite."""
    _require_api_auth(request)

    db_path = Path("data/captures.db")
    if not db_path.exists():
        return {"items": [], "total": 0, "limit": limit, "offset": offset}

    try:
        from storage.sqlite_storage import SQLiteStorage

        with SQLiteStorage(str(db_path)) as db:
            total = db.count_total()
            rows = db.get_pending(limit=limit)
            items = []
            for row in rows:
                data_val = row["data"]
                item = {
                    "id": row["id"],
                    "capture_type": row["type"],
                    "data": (
                        data_val[:500]
                        if isinstance(data_val, str)
                        else str(data_val)[:500]
                    ),
                    "timestamp": (
                        datetime.fromtimestamp(row["timestamp"]).isoformat()
                        if row.get("timestamp")
                        else None
                    ),
                    "status": row.get("status", "pending"),
                }
                if capture_type and item["capture_type"] != capture_type:
                    continue
                items.append(item)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {"items": items, "total": total, "limit": limit, "offset": offset}


@api_router.get("/screenshots")
async def list_screenshots(
    request: Request,
    limit: int = Query(20, ge=1, le=100),
) -> dict[str, Any]:
    """List available screenshots."""
    _require_api_auth(request)

    screenshot_dir = Path("data/screenshots")
    if not screenshot_dir.exists():
        return {"screenshots": [], "total": 0}

    files = sorted(
        screenshot_dir.glob("*.png"),
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )
    total = len(files)
    files = files[:limit]

    screenshots = []
    for f in files:
        stat = f.stat()
        screenshots.append({
            "filename": f.name,
            "path": f"/api/screenshots/{f.name}",
            "size_bytes": stat.st_size,
            "size_kb": round(stat.st_size / 1024, 1),
            "timestamp": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        })

    return {"screenshots": screenshots, "total": total}


@api_router.get("/screenshots/{filename}")
async def get_screenshot(request: Request, filename: str) -> Any:
    """Serve a screenshot file."""
    _require_api_auth(request)

    # Prevent path traversal
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    filepath = Path("data/screenshots") / filename
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="Screenshot not found")

    from fastapi.responses import FileResponse

    return FileResponse(str(filepath), media_type="image/png")


@api_router.get("/analytics/activity")
async def activity_data(request: Request) -> dict[str, Any]:
    """Activity heatmap data (hour x day-of-week)."""
    _require_api_auth(request)

    db_path = Path("data/captures.db")
    if not db_path.exists():
        return {"heatmap": [[0] * 24 for _ in range(7)], "total_events": 0}

    heatmap = [[0] * 24 for _ in range(7)]
    total = 0

    try:
        from storage.sqlite_storage import SQLiteStorage

        with SQLiteStorage(str(db_path)) as db:
            rows = db.get_pending(limit=10000)
            for row in rows:
                total += 1
                ts_val = row.get("timestamp")
                if ts_val:
                    try:
                        ts = datetime.fromtimestamp(float(ts_val))
                        heatmap[ts.weekday()][ts.hour] += 1
                    except (ValueError, TypeError, OSError):
                        pass
    except Exception:
        pass

    return {"heatmap": heatmap, "total_events": total}


@api_router.get("/analytics/summary")
async def analytics_summary(request: Request) -> dict[str, Any]:
    """Summary analytics."""
    _require_api_auth(request)

    db_path = Path("data/captures.db")
    stats: dict[str, Any] = {
        "total_captures": 0,
        "pending": 0,
        "sent": 0,
        "capture_types": {},
        "screenshots_count": 0,
        "db_size_mb": 0,
    }

    if db_path.exists():
        try:
            from storage.sqlite_storage import SQLiteStorage

            with SQLiteStorage(str(db_path)) as db:
                stats["total_captures"] = db.count_total()
                stats["pending"] = db.count_pending()
                stats["sent"] = stats["total_captures"] - stats["pending"]
            stats["db_size_mb"] = round(
                db_path.stat().st_size / 1024 / 1024, 2
            )
        except Exception:
            pass

    screenshot_dir = Path("data/screenshots")
    if screenshot_dir.exists():
        stats["screenshots_count"] = len(list(screenshot_dir.glob("*.png")))

    return stats


@api_router.get("/config")
async def get_config(request: Request) -> dict[str, Any]:
    """Get current configuration."""
    _require_api_auth(request)
    try:
        from config.settings import Settings

        settings = Settings()
        return {"config": settings.as_dict()}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@api_router.get("/modules")
async def list_modules(request: Request) -> dict[str, Any]:
    """List registered capture and transport modules."""
    _require_api_auth(request)

    capture_modules = []
    transport_modules = []

    try:
        from capture import _CAPTURE_REGISTRY

        for name, cls in _CAPTURE_REGISTRY.items():
            capture_modules.append({
                "name": name,
                "class": cls.__name__,
                "module": cls.__module__,
            })
    except Exception:
        pass

    try:
        from transport import _TRANSPORT_REGISTRY

        for name, cls in _TRANSPORT_REGISTRY.items():
            transport_modules.append({
                "name": name,
                "class": cls.__name__,
                "module": cls.__module__,
            })
    except Exception:
        pass

    return {
        "capture_modules": capture_modules,
        "transport_modules": transport_modules,
    }
