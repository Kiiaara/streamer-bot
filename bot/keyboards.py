"""Генерация inline-клавиатур через дерево контента."""
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from .tree import Node


def nav_keyboard(node: Node, path_indices: list[int]) -> InlineKeyboardMarkup:
    """Кнопки детей текущего узла + кнопка Назад если не на корне.
    Листовые дети с url - кнопки-ссылки. Промежуточные - callback с расширенным путём."""
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for idx, child in enumerate(node.children):
        new_path = path_indices + [idx]
        if child.is_leaf():
            btn = InlineKeyboardButton(text=child.label[:64], url=child.item.url)
        else:
            btn = InlineKeyboardButton(text=child.label[:64], callback_data=_cb(new_path))
        row.append(btn)
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)

    if path_indices:
        # Назад - на уровень выше
        parent_path = path_indices[:-1]
        rows.append([InlineKeyboardButton(text="← Назад", callback_data=_cb(parent_path))])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def leaf_card_keyboard(item, path_indices: list[int]) -> InlineKeyboardMarkup:
    """Карточка листа - кнопка перехода (текст из item.button_text или 'Перейти →') + Назад.
    Если url пустой - кнопки перехода нет, только Назад (например для реквизитов)."""
    parent_path = path_indices[:-1]
    rows: list[list[InlineKeyboardButton]] = []
    url = (getattr(item, "url", "") or "").strip()
    if url:
        button_label = (getattr(item, "button_text", "") or "").strip() or "Перейти →"
        rows.append([InlineKeyboardButton(text=button_label[:64], url=url)])
    rows.append([InlineKeyboardButton(text="← Назад", callback_data=_cb(parent_path))])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def auto_comment_keyboard(buttons: list[tuple[str, str]]) -> InlineKeyboardMarkup | None:
    if not buttons:
        return None
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for title, url in buttons:
        row.append(InlineKeyboardButton(text=title, url=url))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _cb(path: list[int]) -> str:
    """Сериализация пути в callback_data. Формат: n:0:1:2 (или n: для корня)."""
    return "n:" + ":".join(str(i) for i in path)


def parse_cb(data: str) -> list[int] | None:
    """Парсит callback_data вида n:0:1:2 в список индексов."""
    if not data.startswith("n:"):
        return None
    rest = data[2:]
    if not rest:
        return []
    try:
        return [int(x) for x in rest.split(":")]
    except ValueError:
        return None
