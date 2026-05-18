"""Авто-комменты в группах обсуждения каналов.

Когда в канале выходит пост, Telegram автоматически пересылает его в привязанную
группу обсуждения как сообщение с is_automatic_forward=True. Бот ловит такие
сообщения и отвечает первым комментарием с тематическим текстом и кнопками.
"""
import logging

from aiogram import F, Router
from aiogram.types import Message

from .analytics import log_event
from .keyboards import auto_comment_keyboard
from .sheets import sheets

log = logging.getLogger(__name__)
router = Router()


@router.message(F.is_automatic_forward.is_(True))
async def auto_forward_comment(msg: Message):
    """Пост из канала автоматически переслан в группу обсуждения - пишем первый коммент."""
    data = await sheets.get()
    cfg = data.auto_comments.get(msg.chat.id)

    if not cfg:
        log.debug(f"Нет настройки авто-коммента для чата {msg.chat.id} ({msg.chat.title})")
        return

    if not cfg.text:
        log.warning(f"Пустой текст авто-коммента для чата {msg.chat.id}")
        return

    try:
        # Отвечаем именно reply на пересланный пост, чтобы коммент привязался к нему
        await msg.reply(
            cfg.text,
            reply_markup=auto_comment_keyboard(cfg.buttons),
            disable_web_page_preview=True,
        )
        log.info(f"Авто-коммент в '{cfg.name}' ({msg.chat.id})")
        log_event(msg.chat.id, "auto_comment", cfg.name or str(msg.chat.id))
    except Exception as e:
        log.exception(f"Не удалось отправить авто-коммент в {msg.chat.id}: {e}")
