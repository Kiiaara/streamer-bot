"""Одноразовая миграция: переносит ключи section_desc.* из Settings в таблицы Section/Category.
Запуск: docker compose exec admin python -m scripts.migrate_section_desc
"""
import asyncio
import logging

from sqlalchemy import delete, select

from shared.db import async_session, init_db
from shared.models import Category, Section, Setting

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("migrate")


async def main():
    await init_db()  # на случай если таблиц нет

    async with async_session() as s:
        # Все ключи section_desc.*
        settings = (
            await s.execute(select(Setting).where(Setting.key.like("section_desc.%")))
        ).scalars().all()

        moved_sections = 0
        moved_categories = 0
        for st in settings:
            # section_desc.Сайт                     -> Section.Сайт
            # section_desc.Игры.Dota 2              -> Category(section=Игры, category=Dota 2)
            # section_desc.Соцсети.Telegram.Dota 2  -> Category(section=Соцсети, category=Telegram, subcategory=Dota 2)
            parts = st.key.split(".", 3)  # ["section_desc", раздел, [категория], [подкатегория]]
            if len(parts) < 2:
                continue
            value = (st.value or "").strip()
            if not value:
                continue

            if len(parts) == 2:
                # Описание раздела
                _, section_name = parts
                section = (
                    await s.execute(select(Section).where(Section.name == section_name))
                ).scalar_one_or_none()
                if section and not section.description:
                    section.description = value
                    moved_sections += 1
                    log.info(f"Section: {section_name}")
            elif len(parts) == 3:
                _, section_name, cat_name = parts
                existing = (
                    await s.execute(
                        select(Category).where(
                            Category.section == section_name,
                            Category.category == cat_name,
                            Category.subcategory == "",
                        )
                    )
                ).scalar_one_or_none()
                if existing:
                    if not existing.description:
                        existing.description = value
                        moved_categories += 1
                else:
                    s.add(Category(
                        section=section_name,
                        category=cat_name,
                        subcategory="",
                        description=value,
                    ))
                    moved_categories += 1
                log.info(f"Category: {section_name}/{cat_name}")
            elif len(parts) == 4:
                _, section_name, cat_name, sub_name = parts
                existing = (
                    await s.execute(
                        select(Category).where(
                            Category.section == section_name,
                            Category.category == cat_name,
                            Category.subcategory == sub_name,
                        )
                    )
                ).scalar_one_or_none()
                if existing:
                    if not existing.description:
                        existing.description = value
                        moved_categories += 1
                else:
                    s.add(Category(
                        section=section_name,
                        category=cat_name,
                        subcategory=sub_name,
                        description=value,
                    ))
                    moved_categories += 1
                log.info(f"Subcategory: {section_name}/{cat_name}/{sub_name}")

        await s.commit()

        # Удаляем перенесённые ключи
        deleted = await s.execute(
            delete(Setting).where(Setting.key.like("section_desc.%"))
        )
        await s.commit()

        log.info(f"Перенесено разделов: {moved_sections}, категорий: {moved_categories}")
        log.info(f"Удалено ключей section_desc.*: {deleted.rowcount}")


if __name__ == "__main__":
    asyncio.run(main())
