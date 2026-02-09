"""Page routes — serve HTML templates."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from dashboard.auth import get_current_user, require_auth

pages_router = APIRouter(tags=["pages"])


@pages_router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request) -> HTMLResponse:
    """Render login page."""
    if get_current_user(request):
        return RedirectResponse(url="/dashboard", status_code=302)
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "login.html", {"error": None})


@pages_router.get("/", response_class=HTMLResponse)
async def landing_page(request: Request) -> HTMLResponse:
    """Render public landing page (no auth required)."""
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "landing.html", {})


@pages_router.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request) -> HTMLResponse:
    """Render main dashboard."""
    redirect = require_auth(request)
    if redirect:
        return redirect
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "user": get_current_user(request),
            "page": "dashboard",
        },
    )


@pages_router.get("/live", response_class=HTMLResponse)
async def live_dashboard_page(request: Request) -> HTMLResponse:
    """Render real-time live dashboard."""
    redirect = require_auth(request)
    if redirect:
        return redirect
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "live-dashboard.html",
        {
            "user": get_current_user(request),
            "page": "live",
        },
    )


@pages_router.get("/captures", response_class=HTMLResponse)
async def captures_page(request: Request) -> HTMLResponse:
    """Render captures viewer page."""
    redirect = require_auth(request)
    if redirect:
        return redirect
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "captures.html",
        {
            "user": get_current_user(request),
            "page": "captures",
        },
    )


@pages_router.get("/screenshots", response_class=HTMLResponse)
async def screenshots_page(request: Request) -> HTMLResponse:
    """Render screenshots gallery page."""
    redirect = require_auth(request)
    if redirect:
        return redirect
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "screenshots.html",
        {
            "user": get_current_user(request),
            "page": "screenshots",
        },
    )


@pages_router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request) -> HTMLResponse:
    """Render settings page."""
    redirect = require_auth(request)
    if redirect:
        return redirect
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "settings.html",
        {
            "user": get_current_user(request),
            "page": "settings",
        },
    )
