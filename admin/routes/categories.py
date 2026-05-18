"""CRUD категорий и подкатегорий. Категории не создаются отдельно - они возникают
из записей контента. Через этот роутер можно только редактировать описание и картинку
существующих категорий/подкатегорий."""
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select

from shared.db import async_session
from shared.html_sanitize import sanitize
from shared.models import Category, ContentItem, User

from ..auth import current_user
from ..common import section_exists, template_ctx, templates

router = APIRouter()


def _get_existing_categories(items: list[ContentItem]) -> list[tuple[str, str]]:
    """Возвращает список (category, subcategory) уникальных категорий и подкатегорий
    которые встречаются в записях. Subcategory может быть пустым - это сама category верхнего уровня."""
    seen: set[tuple[str, str]] = set()
    result: list[tuple[str, str]] = []
    for it in items:
        cat = (it.category or "").strip()
        sub = (it.subcategory or "").strip()
        if not cat:
            continue
        # Сама category (как заголовок-узел) - если есть запись с category но без subcategory
        # ИЛИ у category есть записи с subcategory - значит category тоже отображается как узел
        key1 = (cat, "")
        if key1 not in seen:
            seen.add(key1)
            result.append(key1)
        if sub:
            key2 = (cat, sub)
            if key2 not in seen:
                seen.add(key2)
                result.append(key2)
    return result


@router.get("/section/{section}/category/{category}/edit", response_class=HTMLResponse)
async def edit_category(
    section: str,
    category: str,
    subcategory: str = "",
    request: Request = None,
    user: User = Depends(current_user),
):
    if not await section_exists(section):
        raise HTTPException(status_code=404)
    async with async_session() as s:
        cat = (
            await s.execute(
                select(Category).where(
                    Category.section == section,
                    Category.category == category,
                    Category.subcategory == subcategory,
                )
            )
        ).scalar_one_or_none()
        if cat is None:
            # Виртуальная запись - не создаём пока не сохранят
            cat = Category(section=section, category=category, subcategory=subcategory)
    return templates.TemplateResponse(
        "category_form.html",
        await template_ctx(
            request, user,
            current_section=section,
            category=cat,
            is_subcategory=bool(subcategory),
        ),
    )


@router.post("/section/{section}/category/{category}")
async def save_category(
    section: str,
    category: str,
    subcategory: str = Form(""),
    description: str = Form(""),
    image: str = Form(""),
    user: User = Depends(current_user),
):
    if not await section_exists(section):
        raise HTTPException(status_code=400)
    description = sanitize(description)
    async with async_session() as s:
        existing = (
            await s.execute(
                select(Category).where(
                    Category.section == section,
                    Category.category == category,
                    Category.subcategory == subcategory,
                )
            )
        ).scalar_one_or_none()
        if existing:
            existing.description = description
            existing.image = image.strip()
        else:
            s.add(Category(
                section=section,
                category=category,
                subcategory=subcategory,
                description=description,
                image=image.strip(),
            ))
        await s.commit()
    return RedirectResponse(url=f"/section/{section}", status_code=303)
