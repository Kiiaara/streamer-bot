"""Кеш file_id для картинок. Первая отправка - загружаем файл, последующие - используем file_id (мгновенно).

Хранится в Redis (тот же что для FSM). Ключи: tg_file_id:<basename>.
"""
import logging
import os
from typing import Optional

from aiogram import Bot
from aiogram.types import FSInputFile, Message
from redis.asyncio import Redis

from .config import config

log = logging.getLogger("photo_cache")

_redis: Optional[Redis] = None


def _get_redis() -> Redis:
    global _redis
    if _redis is None:
        _redis = Redis.from_url(config.redis_url, decode_responses=True)
    return _redis


def _key(image_path: str) -> str:
    # ключ по имени файла - если файл переименовали/перезалили, file_id сбросится автоматически
    return f"tg_file_id:{os.path.basename(image_path)}"


async def get_cached_file_id(image_path: str) -> Optional[str]:
    try:
        return await _get_redis().get(_key(image_path))
    except Exception as e:
        log.warning(f"redis get failed: {e}")
        return None


async def set_cached_file_id(image_path: str, file_id: str) -> None:
    try:
        # TTL 30 дней - на всякий, обычно file_id не протухают, но мало ли
        await _get_redis().set(_key(image_path), file_id, ex=30 * 24 * 3600)
    except Exception as e:
        log.warning(f"redis set failed: {e}")


def _extract_photo_file_id(msg: Message) -> Optional[str]:
    """Берёт file_id самой большой версии фото из отправленного сообщения."""
    if not msg or not msg.photo:
        return None
    # photo - список PhotoSize от мелкой к крупной. Берём самую крупную.
    return msg.photo[-1].file_id


async def send_photo_cached(
    target,  # объект с методом answer_photo/reply_photo
    image_path: str,
    *,
    caption: Optional[str] = None,
    reply_markup=None,
    method: str = "answer_photo",  # "answer_photo" или "reply_photo"
) -> Message:
    """Шлёт фото. Если file_id есть в кеше - использует его (быстро).
    Если нет - грузит файл и кеширует file_id из ответа TG.
    """
    send_fn = getattr(target, method)
    cached = await get_cached_file_id(image_path)

    if cached:
        try:
            msg = await send_fn(cached, caption=caption, reply_markup=reply_markup)
            return msg
        except Exception as e:
            # file_id протух / недействителен - перезальём файл
            log.info(f"cached file_id failed for {image_path}: {e}, re-uploading")

    msg = await send_fn(FSInputFile(image_path), caption=caption, reply_markup=reply_markup)
    new_file_id = _extract_photo_file_id(msg)
    if new_file_id:
        await set_cached_file_id(image_path, new_file_id)
    return msg


async def warmup_cache(bot: Bot, chat_id: int, images_dir: str) -> tuple[int, int]:
    """Прогревает кеш: отправляет все картинки из images_dir в указанный chat_id,
    сохраняет file_id. Возвращает (успешно, всего)."""
    if not os.path.isdir(images_dir):
        return 0, 0
    files = [f for f in os.listdir(images_dir) if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp"))]
    ok = 0
    for fname in files:
        path = os.path.join(images_dir, fname)
        try:
            msg = await bot.send_photo(chat_id, FSInputFile(path), caption=f"warmup: {fname}")
            file_id = _extract_photo_file_id(msg)
            if file_id:
                await set_cached_file_id(path, file_id)
                ok += 1
            # сразу удаляем сообщение чтоб не засорять чат
            try:
                await bot.delete_message(chat_id, msg.message_id)
            except Exception:
                pass
        except Exception as e:
            log.warning(f"warmup failed for {fname}: {e}")
    return ok, len(files)
