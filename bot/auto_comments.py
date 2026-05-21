"""Авто-комменты в группах обсуждения каналов.

Когда в канале выходит пост, Telegram автоматически пересылает его в привязанную
группу обсуждения как сообщение с is_automatic_forward=True. Бот ловит такие
сообщения и отвечает первым комментарием с тематическим текстом и кнопками.
"""
import logging
import os

from aiogram import F, Router
from aiogram.types import FSInputFile, Message

from .analytics import log_event
from .keyboards import auto_comment_keyboard
from .sheets import sheets

log = logging.getLogger(__name__)
router = Router()

IMAGES_DIR = "/app/static/images"


@router.message(F.is_automatic_forward.is_(True))
async def auto_forward_comment(msg: Message):
    """Пост из канала автоматически переслан в группу обсуждения - пишем первый коммент."""
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
            await msg.reply_photo(FSInputFile(image_path), caption=cfg.text or None, reply_markup=kb)
        else:
            await msg.reply(cfg.text, reply_markup=kb, disable_web_page_preview=True)
        log.info(f"Авто-коммент в '{cfg.name}' ({msg.chat.id})")
        log_event(msg.chat.id, "auto_comment", cfg.name or str(msg.chat.id))
    except Exception as e:
        log.exception(f"Не удалось отправить авто-коммент в {msg.chat.id}: {e}")
