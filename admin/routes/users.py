"""Управление юзерами админки (роли admin/editor)."""
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import delete, select

from shared.db import async_session
from shared.models import User

from ..auth import normalize_email, require_admin
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
    telegram_id: str = Form(""),  # str чтоб допустить пустую строку при email-only добавлении
    username: str = Form(""),
    email: str = Form(""),
    role: str = Form("editor"),
    user: User = Depends(require_admin),
):
    if role not in ("admin", "editor"):
        raise HTTPException(status_code=400, detail="Bad role")

    email_norm = normalize_email(email) if email else ""
    if email_norm and ("@" not in email_norm or "." not in email_norm):
        raise HTTPException(status_code=400, detail="Некорректный email")

    tg_id_int = None
    if telegram_id and telegram_id.strip():
        try:
            tg_id_int = int(telegram_id.strip())
        except ValueError:
            raise HTTPException(status_code=400, detail="Telegram ID должен быть числом")

    if tg_id_int is None and not email_norm:
        raise HTTPException(status_code=400, detail="Укажите Telegram ID или email")

    async with async_session() as s:
        # Если есть tg_id - ищем по нему (обновляем/создаём)
        if tg_id_int is not None:
            existing = (
                await s.execute(select(User).where(User.telegram_id == tg_id_int))
            ).scalar_one_or_none()
            if existing:
                existing.role = role
                if username.strip():
                    existing.username = username.strip().lstrip("@").lower()
                if email_norm:
                    existing.email = email_norm
            else:
                s.add(User(
                    telegram_id=tg_id_int,
                    username=username.strip().lstrip("@").lower(),
                    email=email_norm,
                    role=role,
                ))
        else:
            # email-only - проверяем что email ещё не занят
            existing_email = (
                await s.execute(select(User).where(User.email == email_norm))
            ).scalar_one_or_none()
            if existing_email:
                existing_email.role = role
                if username.strip():
                    existing_email.username = username.strip().lstrip("@").lower()
            else:
                # подбираем свободный отрицательный telegram_id
                min_row = (await s.execute(
                    select(User).where(User.telegram_id < 0).order_by(User.telegram_id.asc())
                )).scalars().first()
                next_id = (min_row.telegram_id - 1) if min_row else -1
                s.add(User(
                    telegram_id=next_id,
                    username=username.strip().lstrip("@").lower(),
                    email=email_norm,
                    role=role,
                    first_name=email_norm,
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
