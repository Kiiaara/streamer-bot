"""Бывший SheetsClient - теперь читает из SQLite через SQLAlchemy.
Имя файла оставил для обратной совместимости (минимум изменений в импортах).

Кеш на 30 секунд: SQLite дёшев, можно обновлять чаще чем Google Sheets когда-то.
"""
import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy import select

from shared.db import async_session
from shared.models import AutoComment as DbAutoComment
from shared.models import Category as DbCategory
from shared.models import Channel as DbChannel
from shared.models import ContentItem as DbContentItem
from shared.models import Section as DbSection
from shared.models import Setting as DbSetting

from .config import config

log = logging.getLogger(__name__)


@dataclass
class ContentItem:
    section: str
    category: str
    title: str
    url: str
    subcategory: str = ""
    description: str = ""
    keywords: str = ""
    image: str = ""
    button_text: str = ""


@dataclass
class AutoComment:
    chat_id: int
    name: str
    topic: str
    text: str
    buttons: list[tuple[str, str]] = field(default_factory=list)


@dataclass
class ChannelBinding:
    chat_id: int
    name: str
    category: str


@dataclass
class SectionInfo:
    name: str
    description: str = ""
    image: str = ""
    position: int = 0
    hidden: bool = False


@dataclass
class CategoryInfo:
    section: str
    category: str
    subcategory: str = ""
    description: str = ""
    image: str = ""


@dataclass
class SheetsData:
    content: list[ContentItem]
    auto_comments: dict[int, AutoComment]
    channels: dict[int, ChannelBinding]
    settings: dict[str, str]
    sections: dict[str, SectionInfo]  # ключ - название раздела
    categories: dict[tuple[str, str, str], CategoryInfo]  # ключ - (section, category, subcategory)
    fetched_at: float


# Кеш короче чем у Sheets - SQLite дешёвый
_DB_CACHE_TTL = min(config.cache_ttl, 30)


class SheetsClient:
    """Имя класса оставлено для совместимости со старым кодом - читает из SQLite."""

    def __init__(self):
        self._lock = asyncio.Lock()
        self._cache: Optional[SheetsData] = None

    async def _fetch(self) -> SheetsData:
        async with async_session() as s:
            content_rows = (
                await s.execute(
                    select(DbContentItem).order_by(
                        DbContentItem.section, DbContentItem.position, DbContentItem.id
                    )
                )
            ).scalars().all()

            auto_rows = (await s.execute(select(DbAutoComment))).scalars().all()
            channel_rows = (await s.execute(select(DbChannel))).scalars().all()
            setting_rows = (await s.execute(select(DbSetting))).scalars().all()
            section_rows = (await s.execute(select(DbSection))).scalars().all()
            category_rows = (await s.execute(select(DbCategory))).scalars().all()

        content = [
            ContentItem(
                section=r.section,
                category=r.category or "",
                subcategory=r.subcategory or "",
                title=r.title,
                url=r.url,
                description=r.description or "",
                keywords=(r.keywords or "").lower(),
                image=r.image or "",
                button_text=(r.button_text or "").strip(),
            )
            for r in content_rows
            if not getattr(r, "hidden", False)
        ]

        auto_comments: dict[int, AutoComment] = {}
        for r in auto_rows:
            if not r.enabled:
                continue
            try:
                btns_raw = json.loads(r.buttons_json or "[]")
            except json.JSONDecodeError:
                btns_raw = []
            buttons = [
                (str(b.get("title", "")).strip(), str(b.get("url", "")).strip())
                for b in btns_raw
                if b.get("title") and b.get("url")
            ]
            auto_comments[r.chat_id] = AutoComment(
                chat_id=r.chat_id,
                name=r.name or "",
                topic=r.topic or "",
                text=r.text or "",
                buttons=buttons,
            )

        channels = {
            r.chat_id: ChannelBinding(
                chat_id=r.chat_id,
                name=r.name or "",
                category=r.category or "все",
            )
            for r in channel_rows
        }

        settings = {r.key: r.value or "" for r in setting_rows}

        sections = {
            r.name: SectionInfo(
                name=r.name,
                description=r.description or "",
                image=r.image or "",
                position=r.position or 0,
                hidden=bool(getattr(r, "hidden", False)),
            )
            for r in section_rows
        }

        categories = {
            (r.section, r.category, r.subcategory or ""): CategoryInfo(
                section=r.section,
                category=r.category,
                subcategory=r.subcategory or "",
                description=r.description or "",
                image=r.image or "",
            )
            for r in category_rows
        }

        return SheetsData(
            content=content,
            auto_comments=auto_comments,
            channels=channels,
            settings=settings,
            sections=sections,
            categories=categories,
            fetched_at=time.time(),
        )

    async def get(self, force: bool = False) -> SheetsData:
        async with self._lock:
            now = time.time()
            stale = (
                self._cache is None
                or now - self._cache.fetched_at > _DB_CACHE_TTL
            )
            if force or stale:
                try:
                    self._cache = await self._fetch()
                except Exception as e:
                    log.exception(f"Ошибка чтения из SQLite: {e}")
                    if self._cache is None:
                        raise
            return self._cache

    async def invalidate(self):
        async with self._lock:
            self._cache = None


sheets = SheetsClient()
