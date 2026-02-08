"""FastAPI application factory for the AdvanceKeyLogger dashboard."""
from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from dashboard.auth import auth_router
from dashboard.routes.api import api_router
from dashboard.routes.pages import pages_router

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent


_INSECURE_DEFAULT = "change-me-in-production"


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
            "Using insecure default secret_key — "
            "do NOT use in production (APP_ENV=%s)",
            env,
        )

    app = FastAPI(
        title="AdvanceKeyLogger Dashboard",
        version="1.0.0",
        docs_url="/api/docs",
        redoc_url=None,
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

    return app
