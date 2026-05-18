"""CRUD разделов: имя, описание, картинка, порядок. Только для админа."""
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy import delete, select, update

from shared.db import async_session
from shared.html_sanitize import sanitize
from shared.models import ContentItem, Section, User

from ..auth import require_admin
from ..common import template_ctx, templates

router = APIRouter()


@router.get("/sections-manage", response_class=HTMLResponse)
async def list_sections(request: Request, user: User = Depends(require_admin)):
    async with async_session() as s:
        rows = (
            await s.execute(select(Section).order_by(Section.position, Section.id))
        ).scalars().all()
    return templates.TemplateResponse(
        "sections_manage.html",
        await template_ctx(request, user, active="sections", items=rows),
    )


@router.get("/sections-manage/{section_id}/edit", response_class=HTMLResponse)
async def edit_section(section_id: int, request: Request, user: User = Depends(require_admin)):
    async with async_session() as s:
        section = (
            await s.execute(select(Section).where(Section.id == section_id))
        ).scalar_one_or_none()
    if section is None:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse(
        "section_form.html",
        await template_ctx(request, user, active="sections", section=section),
    )


@router.post("/sections-manage")
async def create_section(
    name: str = Form(...),
    user: User = Depends(require_admin),
):
    name = name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Имя не может быть пустым")
    async with async_session() as s:
        # Проверка уникальности
        existing = (
            await s.execute(select(Section).where(Section.name == name))
        ).scalar_one_or_none()
        if existing:
            raise HTTPException(status_code=400, detail="Раздел с таким именем уже существует")
        max_pos = (
            await s.execute(select(Section.position).order_by(Section.position.desc()).limit(1))
        ).scalar()
        s.add(Section(name=name, position=(max_pos or 0) + 1))
        await s.commit()
    return RedirectResponse(url="/sections-manage", status_code=303)


@router.post("/sections-manage/reorder")
async def reorder_sections(request: Request, user: User = Depends(require_admin)):
    body = await request.json()
    order = body.get("order", [])
    async with async_session() as s:
        for pos, sid in enumerate(order):
            await s.execute(
                update(Section).where(Section.id == int(sid)).values(position=pos)
            )
        await s.commit()
    return JSONResponse({"ok": True})


@router.post("/sections-manage/{section_id}")
async def update_section(
    section_id: int,
    name: str = Form(...),
    description: str = Form(""),
    image: str = Form(""),
    hidden: str = Form(""),
    user: User = Depends(require_admin),
):
    name = name.strip()
    if not name:
        raise HTTPException(status_code=400)
    description = sanitize(description)
    async with async_session() as s:
        section = (
            await s.execute(select(Section).where(Section.id == section_id))
        ).scalar_one_or_none()
        if section is None:
            raise HTTPException(status_code=404)

        old_name = section.name
        # Если имя меняется - обновим все связанные ContentItem
        if old_name != name:
            # Проверка уникальности нового имени
            conflict = (
                await s.execute(
                    select(Section).where(Section.name == name, Section.id != section_id)
                )
            ).scalar_one_or_none()
            if conflict:
                raise HTTPException(status_code=400, detail="Раздел с таким именем уже существует")
            await s.execute(
                update(ContentItem).where(ContentItem.section == old_name).values(section=name)
            )

        section.name = name
        section.description = description
        section.image = image.strip()
        section.hidden = bool(hidden)  # чекбокс присылает "on" если включён, иначе поле отсутствует
        await s.commit()
    return RedirectResponse(url=f"/section/{name}", status_code=303)


@router.post("/sections-manage/{section_id}/delete")
async def delete_section_route(section_id: int, user: User = Depends(require_admin)):
    async with async_session() as s:
        section = (
            await s.execute(select(Section).where(Section.id == section_id))
        ).scalar_one_or_none()
        if section is None:
            raise HTTPException(status_code=404)
        # Проверим что в разделе нет записей
        count = (
            await s.execute(
                select(ContentItem).where(ContentItem.section == section.name).limit(1)
            )
        ).first()
        if count is not None:
            raise HTTPException(
                status_code=400,
                detail="В разделе есть записи. Удали их или перенеси прежде чем удалять раздел.",
            )
        await s.execute(delete(Section).where(Section.id == section_id))
        await s.commit()
    return RedirectResponse(url="/sections-manage", status_code=303)
