"""Санитайзинг HTML описаний под Telegram parse_mode=HTML.

Telegram поддерживает: b, strong, i, em, u, ins, s, strike, del, code, pre,
a (с href), tg-spoiler. ВАЖНО: <br> не поддерживается - надо переводить в \\n.
Также <p> и <div> от contenteditable - заменяем на переводы строк.
"""
import re

import bleach

ALLOWED_TAGS = [
    "b", "strong",
    "i", "em",
    "u", "ins",
    "s", "strike", "del",
    "code", "pre",
    "a",
    "tg-spoiler",
]

ALLOWED_ATTRS = {
    "a": ["href"],
}


def sanitize(html: str) -> str:
    """Очищает HTML до Telegram-совместимого подмножества тегов.
    Переносы строк (<br>, <p>, <div>) превращаем в \\n - они дают тот же визуальный
    результат в Telegram, но не ломают парсер HTML."""
    if not html:
        return ""

    # Сначала превращаем теги-переносы в \n до удаления через bleach
    # <br>, <br/>, <br /> -> \n
    s = re.sub(r"<br\s*/?>", "\n", html, flags=re.IGNORECASE)
    # </p>, </div> -> \n (открывающие удалятся ниже)
    s = re.sub(r"</(p|div)>", "\n", s, flags=re.IGNORECASE)
    # Открывающие <p>, <div> - просто срезаем
    s = re.sub(r"<(p|div)[^>]*>", "", s, flags=re.IGNORECASE)
    # &nbsp; -> обычный пробел
    s = s.replace("&nbsp;", " ").replace("&#160;", " ")

    cleaned = bleach.clean(
        s,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRS,
        strip=True,
        strip_comments=True,
    )

    # Сжимаем пачку \n в максимум двойной
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()
