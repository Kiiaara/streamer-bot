"""Одноразовая миграция данных из Google Sheets в SQLite.

Запуск: docker compose run --rm bot python -m scripts.migrate_from_sheets
Использует те же credentials и SHEETS_ID что и бот раньше.
Идемпотентно: сначала чистит таблицы, потом наполняет заново.
"""
import asyncio
import json
import logging
import os
import sys

import gspread
from google.oauth2.service_account import Credentials
from sqlalchemy import delete

from shared.db import async_session, init_db
from shared.models import AutoComment, Channel, ContentItem, Setting

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]


def _parse_buttons_legacy(raw: str) -> list[dict]:
    """Старый формат кнопок 'Т1|url1;;Т2|url2' -> JSON-список."""
    result = []
    for part in (raw or "").split(";;"):
        part = part.strip()
        if not part or "|" not in part:
            continue
        title, url = part.split("|", 1)
        title, url = title.strip(), url.strip()
        if title and url:
            result.append({"title": title, "url": url})
    return result


def fetch_sheets_data():
    sheets_id = os.environ["SHEETS_ID"]
    creds_path = os.environ.get("GOOGLE_CREDENTIALS", "/app/credentials.json")
    creds = Credentials.from_service_account_file(creds_path, scopes=SCOPES)
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(sheets_id)

    data = {"content": [], "auto_comments": [], "channels": [], "settings": []}

    try:
        ws = sh.worksheet("Контент")
        for pos, r in enumerate(ws.get_all_records()):
            title = str(r.get("title", "")).strip()
            url = str(r.get("url", "")).strip()
            if not title or not url:
                continue
            data["content"].append({
                "section": str(r.get("section", "")).strip(),
                "category": str(r.get("category", "")).strip(),
                "subcategory": str(r.get("subcategory", "")).strip(),
                "title": title,
                "url": url,
                "description": str(r.get("description", "")).strip(),
                "keywords": str(r.get("keywords", "")).strip().lower(),
                "image": str(r.get("image", "")).strip(),
                "position": pos,
            })
    except gspread.WorksheetNotFound:
        log.warning("Лист 'Контент' не найден")

    try:
        ws = sh.worksheet("АвтоКомменты")
        for r in ws.get_all_records():
            cid = str(r.get("chat_id", "")).strip()
            if not cid:
                continue
            try:
                cid_int = int(cid)
            except ValueError:
                continue
            data["auto_comments"].append({
                "chat_id": cid_int,
                "name": str(r.get("название", "")).strip(),
                "topic": str(r.get("тематика", "")).strip(),
                "text": str(r.get("текст", "")).strip(),
                "buttons_json": json.dumps(
                    _parse_buttons_legacy(str(r.get("кнопки", ""))),
                    ensure_ascii=False,
                ),
                "enabled": True,
            })
    except gspread.WorksheetNotFound:
        log.warning("Лист 'АвтоКомменты' не найден")

    try:
        ws = sh.worksheet("Каналы")
        for r in ws.get_all_records():
            cid = str(r.get("chat_id", "")).strip()
            if not cid:
                continue
            try:
                cid_int = int(cid)
            except ValueError:
                continue
            data["channels"].append({
                "chat_id": cid_int,
                "name": str(r.get("название", "")).strip(),
                "category": str(r.get("привязка_к_категории", "все")).strip() or "все",
            })
    except gspread.WorksheetNotFound:
        log.warning("Лист 'Каналы' не найден")

    try:
        ws = sh.worksheet("Настройки")
        for r in ws.get_all_records():
            k = str(r.get("ключ", "")).strip()
            v = str(r.get("значение", "")).strip()
            if k:
                data["settings"].append({"key": k, "value": v})
    except gspread.WorksheetNotFound:
        log.warning("Лист 'Настройки' не найден")

    return data


async def migrate(data):
    async with async_session() as s:
        # Чистим таблицы перед заполнением (идемпотентность)
        await s.execute(delete(ContentItem))
        await s.execute(delete(AutoComment))
        await s.execute(delete(Channel))
        await s.execute(delete(Setting))
        await s.commit()

        for row in data["content"]:
            s.add(ContentItem(**row))
        for row in data["auto_comments"]:
            s.add(AutoComment(**row))
        for row in data["channels"]:
            s.add(Channel(**row))
        for row in data["settings"]:
            s.add(Setting(**row))
        await s.commit()


async def main():
    await init_db()
    log.info("Читаю Google Sheets...")
    data = fetch_sheets_data()
    log.info(
        "Прочитано: контент=%d, авто-комменты=%d, каналы=%d, настройки=%d",
        len(data["content"]),
        len(data["auto_comments"]),
        len(data["channels"]),
        len(data["settings"]),
    )
    log.info("Записываю в SQLite...")
    await migrate(data)
    log.info("Миграция завершена.")


if __name__ == "__main__":
    sys.exit(asyncio.run(main()) or 0)
