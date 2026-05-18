"""CRUD контента: список карточек по разделам, форма редактирования, загрузка картинок, reorder."""
import json
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy import delete, select, update

from shared.db import async_session
from shared.html_sanitize import sanitize
from shared.models import Category, ContentItem, Section, User

from ..auth import current_user
from ..common import get_sections, save_uploaded_image, section_exists, template_ctx, templates

router = APIRouter()


@router.get("/section/{section}", response_class=HTMLResponse)
async def section_page(section: str, request: Request, user: User = Depends(current_user)):
    if not await section_exists(section):
        raise HTTPException(status_code=404)
    async with async_session() as s:
        items = (
            await s.execute(
                select(ContentItem)
                .where(ContentItem.section == section)
                .order_by(ContentItem.position, ContentItem.id)
            )
        ).scalars().all()
        section_obj = (
            await s.execute(select(Section).where(Section.name == section))
        ).scalar_one_or_none()
        cat_rows = (
            await s.execute(select(Category).where(Category.section == section))
        ).scalars().all()

    # Собираем уникальные (category, subcategory) из item-ов + информацию из Category-таблицы
    cat_info: dict[tuple[str, str], dict] = {}
    for r in cat_rows:
        cat_info[(r.category, r.subcategory or "")] = {
            "description": r.description or "",
            "image": r.image or "",
        }

    seen: set[tuple[str, str]] = set()
    categories_list: list[dict] = []
    for it in items:
        cat = (it.category or "").strip()
        sub = (it.subcategory or "").strip()
        if not cat:
            continue
        for key in [(cat, ""), (cat, sub)] if sub else [(cat, "")]:
            if key in seen:
                continue
            seen.add(key)
            info = cat_info.get(key, {})
            categories_list.append({
                "category": key[0],
                "subcategory": key[1],
                "description": info.get("description", ""),
                "image": info.get("image", ""),
            })

    return templates.TemplateResponse(
        "section.html",
        await template_ctx(
            request, user,
            current_section=section,
            section_obj=section_obj,
            items=items,
            categories=categories_list,
        ),
    )


@router.get("/item/new", response_class=HTMLResponse)
async def item_new(section: str, request: Request, user: User = Depends(current_user)):
    if not await section_exists(section):
        raise HTTPException(status_code=404)
    item = ContentItem(section=section, title="", url="", description="")
    return templates.TemplateResponse(
        "item_form.html",
        await template_ctx(request, user, current_section=section, item=item, is_new=True),
    )


@router.get("/item/{item_id}/edit", response_class=HTMLResponse)
async def item_edit(item_id: int, request: Request, user: User = Depends(current_user)):
    async with async_session() as s:
        item = (
            await s.execute(select(ContentItem).where(ContentItem.id == item_id))
        ).scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse(
        "item_form.html",
        await template_ctx(request, user, current_section=item.section, item=item, is_new=False),
    )


@router.post("/item")
async def item_create(
    section: str = Form(...),
    title: str = Form(...),
    url: str = Form(""),
    category: str = Form(""),
    subcategory: str = Form(""),
    description: str = Form(""),
    keywords: str = Form(""),
    image: str = Form(""),
    button_text: str = Form(""),
    hidden: str = Form(""),
    user: User = Depends(current_user),
):
    if not await section_exists(section):
        raise HTTPException(status_code=400)
    description = sanitize(description)
    async with async_session() as s:
        max_pos = (
            await s.execute(
                select(ContentItem.position)
                .where(ContentItem.section == section)
                .order_by(ContentItem.position.desc())
                .limit(1)
            )
        ).scalar()
        new_item = ContentItem(
            section=section,
            category=category.strip(),
            subcategory=subcategory.strip(),
            title=title.strip(),
            url=url.strip(),
            description=description,
            keywords=keywords.strip().lower(),
            image=image.strip(),
            button_text=button_text.strip(),
            position=(max_pos or 0) + 1,
            hidden=bool(hidden),
        )
        s.add(new_item)
        await s.commit()
    return RedirectResponse(url=f"/section/{section}", status_code=303)


@router.post("/item/{item_id}")
async def item_update(
    item_id: int,
    section: str = Form(...),
    title: str = Form(...),
    url: str = Form(""),
    category: str = Form(""),
    subcategory: str = Form(""),
    description: str = Form(""),
    keywords: str = Form(""),
    image: str = Form(""),
    button_text: str = Form(""),
    hidden: str = Form(""),
    user: User = Depends(current_user),
):
    if not await section_exists(section):
        raise HTTPException(status_code=400)
    description = sanitize(description)
    async with async_session() as s:
        await s.execute(
            update(ContentItem)
            .where(ContentItem.id == item_id)
            .values(
                section=section,
                category=category.strip(),
                subcategory=subcategory.strip(),
                title=title.strip(),
                url=url.strip(),
                description=description,
                keywords=keywords.strip().lower(),
                image=image.strip(),
                button_text=button_text.strip(),
                hidden=bool(hidden),
            )
        )
        await s.commit()
    return RedirectResponse(url=f"/section/{section}", status_code=303)


@router.post("/item/{item_id}/delete")
async def item_delete(item_id: int, user: User = Depends(current_user)):
    async with async_session() as s:
        item = (
            await s.execute(select(ContentItem).where(ContentItem.id == item_id))
        ).scalar_one_or_none()
        if item is None:
            raise HTTPException(status_code=404)
        section = item.section
        await s.execute(delete(ContentItem).where(ContentItem.id == item_id))
        await s.commit()
    return RedirectResponse(url=f"/section/{section}", status_code=303)


@router.post("/section/{section}/reorder")
async def section_reorder(
    section: str,
    request: Request,
    user: User = Depends(current_user),
):
    """Принимает JSON {"order": [id1, id2, ...]} - присваивает позиции по порядку."""
    if not await section_exists(section):
        raise HTTPException(status_code=400)
    body = await request.json()
    order = body.get("order", [])
    async with async_session() as s:
        for pos, item_id in enumerate(order):
            await s.execute(
                update(ContentItem)
                .where(ContentItem.id == int(item_id), ContentItem.section == section)
                .values(position=pos)
            )
        await s.commit()
    return JSONResponse({"ok": True})


@router.post("/upload")
async def upload(file: UploadFile = File(...), user: User = Depends(current_user)):
    if file.content_type not in {"image/jpeg", "image/png", "image/webp", "image/gif"}:
        raise HTTPException(status_code=400, detail="Только JPEG/PNG/WEBP/GIF")
    data = await file.read()
    if len(data) > 5 * 1024 * 1024:  # 5 МБ
        raise HTTPException(status_code=400, detail="Файл больше 5 МБ")
    name = save_uploaded_image(data, file.filename or "image.jpg")
    return {"filename": name, "url": f"/uploads/{name}"}
