"""FastAPI application factory for the AdvanceKeyLogger dashboard."""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from dashboard.auth import auth_router
from dashboard.routes.pages import pages_router
from dashboard.routes.api import api_router

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent


def create_app(secret_key: str = "change-me-in-production") -> FastAPI:
    """Create and configure the FastAPI application."""
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
