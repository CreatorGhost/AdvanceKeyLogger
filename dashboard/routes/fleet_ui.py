from fastapi import APIRouter, HTTPException, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from dashboard.auth import get_current_user, require_auth

router = APIRouter(tags=["fleet_ui"])


@router.get("/fleet", response_class=HTMLResponse)
async def fleet_page(request: Request) -> HTMLResponse:
    redirect = require_auth(request)
    if redirect:
        return redirect

    templates = getattr(request.app.state, "templates", None)
    if templates is None:
        raise HTTPException(status_code=503, detail="Dashboard templates not initialized")
    return templates.TemplateResponse(
        request,
        "fleet/index.html",
        {
            "user": get_current_user(request),
            "page": "fleet",
        },
    )


@router.get("/fleet/agents/{agent_id}", response_class=HTMLResponse)
async def agent_details_page(request: Request, agent_id: str) -> HTMLResponse:
    redirect = require_auth(request)
    if redirect:
        return redirect

    templates = getattr(request.app.state, "templates", None)
    if templates is None:
        raise HTTPException(status_code=503, detail="Dashboard templates not initialized")
    return templates.TemplateResponse(
        request,
        "fleet/agent_details.html",
        {"user": get_current_user(request), "page": "fleet", "agent_id": agent_id},
    )
