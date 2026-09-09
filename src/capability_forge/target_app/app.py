from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from capability_forge.target_app.data import lookup

TEMPLATES = Path(__file__).parent / "templates"
STATIC = Path(__file__).parent / "static"
templates = Jinja2Templates(directory=str(TEMPLATES))

router = APIRouter(prefix="/corebank", tags=["corebank"])


@router.get("/", response_class=HTMLResponse)
async def search(request: Request, notice: int = 0) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "search.html",
        {"title": "Member search", "crumb": "Search", "notice": bool(notice)},
    )


@router.get("/search-form", response_class=HTMLResponse)
async def search_form(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "search_form.html", {})


@router.get("/results", response_class=HTMLResponse)
async def results(request: Request, memno: str = "") -> HTMLResponse:
    member = lookup(memno)
    return templates.TemplateResponse(
        request,
        "results.html",
        {"title": "Search results", "crumb": "Results", "member": member, "memno": memno},
    )


@router.get("/member/{member_id}", response_class=HTMLResponse)
async def detail(request: Request, member_id: str) -> HTMLResponse:
    member = lookup(member_id)
    if not member:
        return RedirectResponse(f"/corebank/results?memno={member_id}", status_code=302)
    return templates.TemplateResponse(
        request,
        "detail.html",
        {"title": "Member file", "crumb": "File", "member": member},
    )


@router.get("/member/{member_id}/inquiry", response_class=HTMLResponse)
async def inquiry(request: Request, member_id: str) -> HTMLResponse:
    member = lookup(member_id)
    if not member:
        return RedirectResponse(f"/corebank/results?memno={member_id}", status_code=302)
    confirmation = f"INQ-{member_id}-8841"
    return templates.TemplateResponse(
        request,
        "confirm.html",
        {
            "title": "Inquiry confirmation",
            "crumb": "Confirmation",
            "member": member,
            "confirmation": confirmation,
        },
    )


@router.get("/member/{member_id}/close-account", response_class=HTMLResponse)
async def close_account(request: Request, member_id: str) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "denied.html",
        {"title": "Denied", "crumb": "Denied", "member_id": member_id},
    )
