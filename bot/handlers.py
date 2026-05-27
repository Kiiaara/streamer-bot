"""Хендлеры: личка с юзером, навигация по дереву, свободные вопросы."""
import logging
import os

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from .analytics import log_event
from .keyboards import leaf_card_keyboard, nav_keyboard, parse_cb
from .search import hybrid_search
from .sheets import ContentItem, SheetsData, sheets
from .tree import Node, build_tree, resolve_path

IMAGES_DIR = "/app/static/images"
log = logging.getLogger(__name__)
router = Router()


def _greeting(settings: dict[str, str]) -> str:
    return settings.get(
        "greeting",
        "Привет! Я Травобот. Выбери раздел или просто напиши вопрос - я найду ответ."
    )


async def _resolve_filter(chat_id: int) -> str | None:
    data = await sheets.get()
    binding = data.channels.get(chat_id)
    if not binding or binding.category in ("все", "all", ""):
        return None
    return binding.category


def _image_path(item: ContentItem) -> str | None:
    if not item.image:
        return None
    path = os.path.join(IMAGES_DIR, item.image)
    return path if os.path.isfile(path) else None


def _node_description(data: SheetsData, path_labels: list[str]) -> str:
    """Ищет описание узла:
    - 1 уровень (раздел): таблица Section, потом legacy section_desc.X в Settings
    - 2 уровень (категория): Category(section, category, ""), потом legacy
    - 3 уровень (подкатегория): Category(section, category, subcategory), потом legacy
    """
    if not path_labels:
        return ""
    if len(path_labels) == 1:
        section = data.sections.get(path_labels[0])
        if section and section.description:
            return section.description.strip()
    elif len(path_labels) == 2:
        cat = data.categories.get((path_labels[0], path_labels[1], ""))
        if cat and cat.description:
            return cat.description.strip()
    elif len(path_labels) >= 3:
        cat = data.categories.get((path_labels[0], path_labels[1], path_labels[2]))
        if cat and cat.description:
            return cat.description.strip()
    # Legacy fallback
    key = "section_desc." + ".".join(path_labels)
    return data.settings.get(key, "").strip()


def _node_image(data: SheetsData, path_labels: list[str]) -> str | None:
    """Картинка узла - для разделов и категорий/подкатегорий."""
    image = ""
    if len(path_labels) == 1:
        section = data.sections.get(path_labels[0])
        if section:
            image = section.image
    elif len(path_labels) == 2:
        cat = data.categories.get((path_labels[0], path_labels[1], ""))
        if cat:
            image = cat.image
    elif len(path_labels) >= 3:
        cat = data.categories.get((path_labels[0], path_labels[1], path_labels[2]))
        if cat:
            image = cat.image
    if image:
        path = os.path.join(IMAGES_DIR, image)
        if os.path.isfile(path):
            return path
    return None


def _build_header(node: Node, path_labels: list[str], data: SheetsData, leaf: ContentItem | None = None) -> str:
    """Текст-заголовок для текущего экрана.
    Для листа: title (если не дублирует родителя) + description.
    Для узла: <b>label</b> + описание из Настроек/Section если есть."""
    if leaf is not None:
        parts = []
        if leaf.title:
            parts.append(f"<b>{leaf.title}</b>")
        if leaf.description:
            parts.append(leaf.description)
        return "\n\n".join(parts) if parts else ""

    label = node.label if path_labels else "Главное меню"
    desc = _node_description(data, path_labels)
    if desc:
        return f"<b>{label}</b>\n\n{desc}"
    return f"<b>{label}</b>"


async def _send_screen(cb: CallbackQuery, text: str, kb: InlineKeyboardMarkup, image_path: str | None):
    """Отправляет экран. Если картинка - удаляем старое сообщение и шлём новое с фото.
    Если предыдущее было фото, а новое текст - тоже удаляем (Telegram не даёт edit между типами)."""
    msg = cb.message
    if image_path:
        try:
            await msg.delete()
        except Exception:
            pass
        from .photo_cache import send_photo_cached
        await send_photo_cached(msg, image_path, caption=text[:1024], reply_markup=kb)
    else:
        if msg.photo:
            try:
                await msg.delete()
            except Exception:
                pass
            await msg.answer(text, reply_markup=kb)
        else:
            try:
                await msg.edit_text(text, reply_markup=kb)
            except Exception:
                # Если редактирование не удалось (например сообщение слишком старое) - шлём новое
                await msg.answer(text, reply_markup=kb)


async def _show_root(cb_or_msg, data, filter_section: str | None, edit: bool):
    """Показать главное меню (или вход в фильтрованный раздел)."""
    root = build_tree(data, filter_section=filter_section)
    text = _greeting(data.settings) if not filter_section else _build_header(root, [], data)
    kb = nav_keyboard(root, [])
    if edit and isinstance(cb_or_msg, CallbackQuery):
        await _send_screen(cb_or_msg, text, kb, image_path=None)
    else:
        msg = cb_or_msg if isinstance(cb_or_msg, Message) else cb_or_msg.message
        await msg.answer(text, reply_markup=kb)


@router.message(CommandStart())
async def cmd_start(msg: Message):
    data = await sheets.get()
    filter_section = None if msg.chat.type == "private" else await _resolve_filter(msg.chat.id)
    if msg.from_user:
        log_event(msg.from_user.id, "start", "")
    await _show_root(msg, data, filter_section, edit=False)


@router.message(Command("menu"))
async def cmd_menu(msg: Message):
    data = await sheets.get()
    filter_section = None if msg.chat.type == "private" else await _resolve_filter(msg.chat.id)
    await _show_root(msg, data, filter_section, edit=False)


@router.message(Command("reload"))
async def cmd_reload(msg: Message):
    await sheets.invalidate()
    await sheets.get(force=True)
    await msg.answer("Кеш Sheets обновлён.")


@router.callback_query(F.data.startswith("n:"))
async def cb_nav(cb: CallbackQuery):
    indices = parse_cb(cb.data)
    if indices is None:
        await cb.answer()
        return

    data = await sheets.get()
    filter_section = None if cb.message.chat.type == "private" else await _resolve_filter(cb.message.chat.id)
    root = build_tree(data, filter_section=filter_section)
    node, path = resolve_path(root, indices)

    # Корень
    if not path:
        text = _greeting(data.settings)
        await _send_screen(cb, text, nav_keyboard(root, []), image_path=None)
        await cb.answer()
        return

    path_labels = [n.label for n in path]

    # Аналитика - тип события по глубине пути
    user = cb.from_user
    if user:
        if len(path_labels) == 1:
            log_event(user.id, "click_section", path_labels[0])
        elif len(path_labels) == 2:
            log_event(user.id, "click_category", " / ".join(path_labels))
        else:
            log_event(user.id, "click_subcategory", " / ".join(path_labels))

    # Если узел не лист и у него один лист-ребёнок - сразу карточка.
    # Назад ведём НЕ на этого родителя (он опять проскочит сюда же), а на ДЕДА.
    # Поэтому в leaf_card_keyboard передаём индексы родителя (не +1), а сама кнопка Назад
    # внутри ведёт на indices[:-1] - дедушку.
    if not node.is_leaf() and len(node.children) == 1 and node.children[0].is_leaf():
        leaf = node.children[0]
        path_labels_with_leaf = path_labels + [leaf.label]
        text = _build_header(leaf, path_labels_with_leaf, data, leaf=leaf.item)
        if user:
            log_event(user.id, "click_leaf", leaf.item.url or leaf.label)
        # indices = путь до родителя. leaf_card_keyboard сделает Назад на indices[:-1] = деда.
        kb = leaf_card_keyboard(leaf.item, indices)
        await _send_screen(cb, text, kb, image_path=_image_path(leaf.item))
        await cb.answer()
        return

    if node.is_leaf():
        text = _build_header(node, path_labels, data, leaf=node.item)
        if user:
            log_event(user.id, "click_leaf", node.item.url or node.label)
        kb = leaf_card_keyboard(node.item, indices)
        await _send_screen(cb, text, kb, image_path=_image_path(node.item))
    else:
        text = _build_header(node, path_labels, data)
        kb = nav_keyboard(node, indices)
        # Картинка узла (для разделов и категорий/подкатегорий)
        node_image = _node_image(data, path_labels)
        await _send_screen(cb, text, kb, image_path=node_image)
    await cb.answer()


@router.message(F.chat.type == "private", F.text)
async def free_question(msg: Message):
    """Свободный вопрос в личке - гибридный поиск."""
    query = msg.text.strip()
    if not query or query.startswith("/"):
        return

    data = await sheets.get()
    if msg.from_user:
        log_event(msg.from_user.id, "search", query)
    results = await hybrid_search(query, data)

    if not results:
        root = build_tree(data)
        await msg.answer(
            "Не нашёл точного ответа. Посмотри в меню - может найдёшь нужное.",
            reply_markup=nav_keyboard(root, []),
        )
        return

    rows: list[list[InlineKeyboardButton]] = []
    for item in results:
        label = item.title
        # Если есть родительская категория - добавим для контекста
        if item.category and item.category != item.title:
            label = f"{item.category} - {item.title}"
        rows.append([InlineKeyboardButton(text=label[:64], url=item.url)])
    rows.append([InlineKeyboardButton(text="← В меню", callback_data="n:")])

    text = "Вот что нашёл:" if len(results) > 1 else "Думаю это:"
    await msg.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
