"""CRUD каналов (привязка чат → категория для тематического меню)."""
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import delete, select

from shared.db import async_session
from shared.models import Channel, User

from ..auth import require_admin
from ..common import template_ctx, templates

router = APIRouter()


@router.get("/channels", response_class=HTMLResponse)
async def list_channels(request: Request, user: User = Depends(require_admin)):
    async with async_session() as s:
        rows = (await s.execute(select(Channel))).scalars().all()
    return templates.TemplateResponse(
        "channels.html",
        await template_ctx(request, user, active="channels", items=rows),
    )


@router.post("/channels")
async def upsert_channel(
    chat_id: int = Form(...),
    name: str = Form(""),
    category: str = Form("все"),
    user: User = Depends(require_admin),
):
    async with async_session() as s:
        existing = (
            await s.execute(select(Channel).where(Channel.chat_id == chat_id))
        ).scalar_one_or_none()
        if existing:
            existing.name = name.strip()
            existing.category = category.strip() or "все"
        else:
            s.add(Channel(chat_id=chat_id, name=name.strip(), category=category.strip() or "все"))
        await s.commit()
    return RedirectResponse(url="/channels", status_code=303)


@router.post("/channels/{chat_id}/delete")
async def delete_channel(chat_id: int, user: User = Depends(require_admin)):
    async with async_session() as s:
        await s.execute(delete(Channel).where(Channel.chat_id == chat_id))
        await s.commit()
    return RedirectResponse(url="/channels", status_code=303)
