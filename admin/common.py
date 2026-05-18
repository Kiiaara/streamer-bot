"""Общие хелперы админки: разделы из БД, шаблонный контекст, загрузка картинок."""
import os
import secrets
from pathlib import Path

from fastapi.templating import Jinja2Templates
from sqlalchemy import select

from shared.db import async_session
from shared.models import Section

from .config import config

# Дефолтные разделы создаются при первом запуске если в БД пусто
DEFAULT_SECTIONS = ["Сайт", "Соцсети", "Гайды", "Игры", "Сервисы", "Ставки"]

BASE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=BASE_DIR / "templates")


async def get_sections() -> list[Section]:
    """Возвращает все разделы в порядке отображения."""
    async with async_session() as s:
        rows = (
            await s.execute(select(Section).order_by(Section.position, Section.id))
        ).scalars().all()
    return list(rows)


async def get_section_names() -> list[str]:
    return [s.name for s in await get_sections()]


async def section_exists(name: str) -> bool:
    return name in await get_section_names()


async def ensure_default_sections():
    """Создаёт дефолтные разделы если в таблице sections пусто."""
    async with async_session() as s:
        existing = (await s.execute(select(Section))).scalars().first()
        if existing is not None:
            return
        for pos, name in enumerate(DEFAULT_SECTIONS):
            s.add(Section(name=name, position=pos))
        await s.commit()


async def template_ctx(request, user, **extra) -> dict:
    """Базовый контекст для всех шаблонов - подгружает разделы для верхней навигации."""
    sections = await get_sections()
    return {
        "request": request,
        "user": user,
        "sections": sections,         # список объектов Section
        "section_names": [s.name for s in sections],
        **extra,
    }


def save_uploaded_image(content: bytes, filename: str) -> str:
    """Сохраняет картинку в IMAGES_DIR с уникальным именем. Возвращает имя файла."""
    os.makedirs(config.images_dir, exist_ok=True)
    ext = Path(filename).suffix.lower() or ".jpg"
    if ext not in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
        ext = ".jpg"
    unique = secrets.token_hex(8) + ext
    target = os.path.join(config.images_dir, unique)
    with open(target, "wb") as f:
        f.write(content)
    return unique
