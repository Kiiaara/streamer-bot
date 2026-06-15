"""Авто-комменты в группах обсуждения каналов.

Когда в канале выходит пост, Telegram автоматически пересылает его в привязанную
группу обсуждения как сообщение с is_automatic_forward=True. Бот ловит такие
сообщения и отвечает первым комментарием с тематическим текстом и кнопками.

Защита от дублей: если пост был медиа-группой (несколько фото), Telegram
шлёт несколько событий с одним media_group_id. Запоминаем уже обработанные
посты (по chat_id + ключу) и игнорируем повторы.
"""
import logging
import os
import time
from collections import OrderedDict

from aiogram import F, Router
from aiogram.types import FSInputFile, Message

from .analytics import log_event
from .keyboards import auto_comment_keyboard
from .sheets import sheets

log = logging.getLogger(__name__)
router = Router()

IMAGES_DIR = "/app/static/images"

# Антидубль: ключ = (chat_id, media_group_id или forward_from_message_id или date),
# значение = unix time. Чистим записи старше 1 часа. Лимит на размер - 500 записей.
_recent_posts: "OrderedDict[tuple, float]" = OrderedDict()
_DEDUP_TTL = 3600
_DEDUP_MAX = 500


def _is_duplicate(msg: Message) -> bool:
    """Возвращает True если на этот пост уже отвечали."""
    now = time.time()
    # Чистим старые записи
    while _recent_posts:
        oldest_key = next(iter(_recent_posts))
        if now - _recent_posts[oldest_key] > _DEDUP_TTL:
            _recent_posts.pop(oldest_key)
        else:
            break

    # Ключ: лучше всего media_group_id (одинаков для всех частей медиа-группы),
    # иначе forward_from_message_id (id поста в канале), иначе date+chat
    key_part = (
        msg.media_group_id
        or (msg.forward_from_message_id if msg.forward_from_message_id else None)
        or msg.date.timestamp()
    )
    key = (msg.chat.id, key_part)

    if key in _recent_posts:
        return True
    _recent_posts[key] = now
    # Ограничиваем размер
    while len(_recent_posts) > _DEDUP_MAX:
        _recent_posts.popitem(last=False)
    return False


@router.message(F.is_automatic_forward.is_(True))
async def auto_forward_comment(msg: Message):
    """Пост из канала автоматически переслан в группу обсуждения - пишем первый коммент."""
    if _is_duplicate(msg):
        log.info(f"Дубль авто-коммента для чата {msg.chat.id} (media_group={msg.media_group_id}, fwd_id={msg.forward_from_message_id}) - пропускаем")
        return

    data = await sheets.get()
    cfg = data.auto_comments.get(msg.chat.id)

    if not cfg:
        log.debug(f"Нет настройки авто-коммента для чата {msg.chat.id} ({msg.chat.title})")
        return

    if not cfg.text and not cfg.image:
        log.warning(f"Пустой авто-коммент для чата {msg.chat.id}")
        return

    image_path = None
    if cfg.image:
        candidate = os.path.join(IMAGES_DIR, cfg.image)
        if os.path.isfile(candidate):
            image_path = candidate
        else:
            log.warning(f"Картинка авто-коммента не найдена: {candidate}")

    kb = auto_comment_keyboard(cfg.buttons)

    try:
        # Отвечаем reply на пересланный пост, чтобы коммент привязался к нему
        if image_path:
            from .photo_cache import send_photo_cached
            await send_photo_cached(msg, image_path, caption=cfg.text or None, reply_markup=kb, method="reply_photo")
        else:
            await msg.reply(cfg.text, reply_markup=kb, disable_web_page_preview=True)
        log.info(f"Авто-коммент в '{cfg.name}' ({msg.chat.id})")
        log_event(msg.chat.id, "auto_comment", cfg.name or str(msg.chat.id))
    except Exception as e:
        log.exception(f"Не удалось отправить авто-коммент в {msg.chat.id}: {e}")
