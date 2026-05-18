"""Логирование событий бота. Fire-and-forget - не блокирует обработчик."""
import asyncio
import logging

from shared.db import async_session
from shared.models import Event

log = logging.getLogger(__name__)


async def _write(user_id: int, event_type: str, target: str):
    try:
        async with async_session() as s:
            s.add(Event(user_id=user_id, event_type=event_type, target=target[:512]))
            await s.commit()
    except Exception as e:
        log.warning(f"analytics write failed: {e}")


def log_event(user_id: int | None, event_type: str, target: str = ""):
    """Не блокирует хендлер - запись идёт в фоне."""
    if not user_id:
        return
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_write(user_id, event_type, target))
    except Exception:
        pass
