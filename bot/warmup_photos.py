"""Прогрев кеша file_id: отправляет все картинки из IMAGES_DIR в указанный чат,
сохраняет file_id в Redis. После этого все юзеры получают картинки мгновенно.

Запуск:
    docker exec travobot python -m bot.warmup_photos <chat_id>

chat_id - твой личный TG (узнать через @userinfobot).
"""
import asyncio
import logging
import os
import sys

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from .config import config
from .photo_cache import warmup_cache


async def main(chat_id: int):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    log = logging.getLogger("warmup")
    images_dir = os.environ.get("IMAGES_DIR", "/app/static/images")
    log.info(f"Прогрев из {images_dir} в chat_id={chat_id}")

    bot = Bot(token=config.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    try:
        ok, total = await warmup_cache(bot, chat_id, images_dir)
        log.info(f"Готово: {ok}/{total} картинок закешировано")
    finally:
        await bot.session.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m bot.warmup_photos <chat_id>")
        sys.exit(1)
    asyncio.run(main(int(sys.argv[1])))
