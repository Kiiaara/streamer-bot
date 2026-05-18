"""Настройки бота (приветствие, описания разделов и т.д.)."""
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import delete, select

from shared.db import async_session
from shared.models import Setting, User

from ..auth import require_admin
from ..common import template_ctx, templates

router = APIRouter()


@router.get("/settings", response_class=HTMLResponse)
async def list_settings(request: Request, user: User = Depends(require_admin)):
    async with async_session() as s:
        rows = (await s.execute(select(Setting).order_by(Setting.key))).scalars().all()
    return templates.TemplateResponse(
        "settings.html",
        await template_ctx(request, user, active="settings", items=rows),
    )


@router.get("/greeting", response_class=HTMLResponse)
async def edit_greeting(request: Request, user: User = Depends(require_admin)):
    async with async_session() as s:
        row = (
            await s.execute(select(Setting).where(Setting.key == "greeting"))
        ).scalar_one_or_none()
    value = row.value if row else "Привет! Я Травобот. Выбери раздел или просто напиши вопрос - я найду ответ."
    return templates.TemplateResponse(
        "greeting.html",
        await template_ctx(request, user, active="greeting", value=value),
    )


@router.post("/greeting")
async def save_greeting(value: str = Form(""), user: User = Depends(require_admin)):
    async with async_session() as s:
        existing = (
            await s.execute(select(Setting).where(Setting.key == "greeting"))
        ).scalar_one_or_none()
        if existing:
            existing.value = value
        else:
            s.add(Setting(key="greeting", value=value))
        await s.commit()
    return RedirectResponse(url="/greeting", status_code=303)


@router.post("/settings")
async def upsert_setting(
    key: str = Form(...),
    value: str = Form(""),
    user: User = Depends(require_admin),
):
    key = key.strip()
    if not key:
        return RedirectResponse(url="/settings", status_code=303)
    async with async_session() as s:
        existing = (
            await s.execute(select(Setting).where(Setting.key == key))
        ).scalar_one_or_none()
        if existing:
            existing.value = value
        else:
            s.add(Setting(key=key, value=value))
        await s.commit()
    return RedirectResponse(url="/settings", status_code=303)


@router.post("/settings/{key}/delete")
async def delete_setting(key: str, user: User = Depends(require_admin)):
    async with async_session() as s:
        await s.execute(delete(Setting).where(Setting.key == key))
        await s.commit()
    return RedirectResponse(url="/settings", status_code=303)
