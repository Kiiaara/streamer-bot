"""Точка входа Травобота."""
import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage

from shared.db import init_db

from .analytics_rollup import analytics_loop
from .config import config
from . import auto_comments, handlers
from .sheets import sheets


async def main():
    logging.basicConfig(
        level=config.log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    log = logging.getLogger("travobot")

    # Создаём таблицы если их ещё нет (идемпотентно)
    await init_db()

    storage = RedisStorage.from_url(config.redis_url)
    bot = Bot(
        token=config.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=storage)

    # Порядок важен: auto_comments первым, чтобы перехватить is_automatic_forward
    # до того как handlers начнёт обрабатывать как обычное сообщение.
    dp.include_router(auto_comments.router)
    dp.include_router(handlers.router)

    # Прогреваем кеш на старте, чтобы первый юзер не ждал
    try:
        await sheets.get(force=True)
        log.info("Кеш контента прогрет")
    except Exception as e:
        log.exception(f"Не удалось прогреть кеш: {e}")

    me = await bot.get_me()
    log.info(f"Бот запущен: @{me.username} ({me.id})")

    # Фоновая задача аналитики (свёртка + очистка)
    analytics_task = asyncio.create_task(analytics_loop())

    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        analytics_task.cancel()
        await bot.session.close()
        await storage.close()


if __name__ == "__main__":
    asyncio.run(main())
