"""Управление юзерами админки (роли admin/editor)."""
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import delete, select

from shared.db import async_session
from shared.models import User

from ..auth import require_admin
from ..common import template_ctx, templates

router = APIRouter()


@router.get("/users", response_class=HTMLResponse)
async def list_users(request: Request, user: User = Depends(require_admin)):
    async with async_session() as s:
        rows = (await s.execute(select(User).order_by(User.created_at))).scalars().all()
    return templates.TemplateResponse(
        "users.html",
        await template_ctx(request, user, active="users", items=rows),
    )


@router.post("/users")
async def add_user(
    telegram_id: int = Form(...),
    username: str = Form(""),
    role: str = Form("editor"),
    user: User = Depends(require_admin),
):
    if role not in ("admin", "editor"):
        raise HTTPException(status_code=400)
    async with async_session() as s:
        existing = (
            await s.execute(select(User).where(User.telegram_id == telegram_id))
        ).scalar_one_or_none()
        if existing:
            existing.role = role
            existing.username = username.strip().lstrip("@").lower() or existing.username
        else:
            s.add(User(
                telegram_id=telegram_id,
                username=username.strip().lstrip("@").lower(),
                role=role,
            ))
        await s.commit()
    return RedirectResponse(url="/users", status_code=303)


@router.post("/users/{telegram_id}/delete")
async def delete_user(telegram_id: int, user: User = Depends(require_admin)):
    if telegram_id == user.telegram_id:
        raise HTTPException(status_code=400, detail="Нельзя удалить себя")
    async with async_session() as s:
        await s.execute(delete(User).where(User.telegram_id == telegram_id))
        await s.commit()
    return RedirectResponse(url="/users", status_code=303)
