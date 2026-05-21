"""CRUD авто-комментов в группах обсуждения."""
import json

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import delete, select, update

from shared.db import async_session
from shared.html_sanitize import sanitize
from shared.models import AutoComment, User

from ..auth import require_admin
from ..common import template_ctx, templates

router = APIRouter()


def _parse_buttons_input(text: str) -> list[dict]:
    """Парсит мультистрочный ввод 'Заголовок | https://url' (по строке - кнопка)."""
    out = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line or "|" not in line:
            continue
        title, url = line.split("|", 1)
        title, url = title.strip(), url.strip()
        if title and url:
            out.append({"title": title, "url": url})
    return out


def _format_buttons(buttons_json: str) -> str:
    """Распаковывает JSON в формат 'Заголовок | url' по строкам - для редактирования."""
    try:
        data = json.loads(buttons_json or "[]")
    except json.JSONDecodeError:
        return ""
    return "\n".join(f"{b['title']} | {b['url']}" for b in data if b.get("title") and b.get("url"))


@router.get("/auto-comments", response_class=HTMLResponse)
async def list_auto_comments(request: Request, user: User = Depends(require_admin)):
    async with async_session() as s:
        rows = (await s.execute(select(AutoComment))).scalars().all()
    items = [
        {
            "chat_id": r.chat_id,
            "name": r.name,
            "topic": r.topic,
            "text": r.text,
            "buttons": _format_buttons(r.buttons_json),
            "image": r.image or "",
            "enabled": r.enabled,
        }
        for r in rows
    ]
    return templates.TemplateResponse(
        "auto_comments.html",
        await template_ctx(request, user, active="auto-comments", items=items),
    )


@router.post("/auto-comments")
async def upsert_auto_comment(
    chat_id: int = Form(...),
    new_chat_id: str = Form(""),
    name: str = Form(""),
    topic: str = Form(""),
    text: str = Form(""),
    buttons: str = Form(""),
    image: str = Form(""),
    enabled: bool = Form(False),
    user: User = Depends(require_admin),
):
    text = sanitize(text)
    buttons_json = json.dumps(_parse_buttons_input(buttons), ensure_ascii=False)
    parsed_new = int(new_chat_id.strip()) if new_chat_id.strip() else None
    target_id = parsed_new if parsed_new and parsed_new != chat_id else chat_id

    async with async_session() as s:
        existing = (
            await s.execute(select(AutoComment).where(AutoComment.chat_id == chat_id))
        ).scalar_one_or_none()
        if existing:
            if target_id != chat_id:
                # Меняем PK - удаляем старую запись, создаём новую
                await s.execute(delete(AutoComment).where(AutoComment.chat_id == chat_id))
                s.add(AutoComment(
                    chat_id=target_id,
                    name=name.strip(),
                    topic=topic.strip(),
                    text=text,
                    buttons_json=buttons_json,
                    image=image.strip(),
                    enabled=enabled,
                ))
            else:
                existing.name = name.strip()
                existing.topic = topic.strip()
                existing.text = text
                existing.buttons_json = buttons_json
                existing.image = image.strip()
                existing.enabled = enabled
        else:
            s.add(AutoComment(
                chat_id=target_id,
                name=name.strip(),
                topic=topic.strip(),
                text=text,
                buttons_json=buttons_json,
                image=image.strip(),
                enabled=enabled,
            ))
        await s.commit()
    return RedirectResponse(url=f"/auto-comments?saved={target_id}#ac-{target_id}", status_code=303)


@router.post("/auto-comments/{chat_id}/delete")
async def delete_auto_comment(chat_id: int, user: User = Depends(require_admin)):
    async with async_session() as s:
        await s.execute(delete(AutoComment).where(AutoComment.chat_id == chat_id))
        await s.commit()
    return RedirectResponse(url="/auto-comments", status_code=303)
