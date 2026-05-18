"""Поиск по контенту: сначала простой по ключевым словам, потом AI через Groq."""
import json
import logging
import re

from groq import AsyncGroq

from .config import config
from .sheets import ContentItem, SheetsData

log = logging.getLogger(__name__)

_groq_client: AsyncGroq | None = None


def _groq() -> AsyncGroq:
    global _groq_client
    if _groq_client is None:
        _groq_client = AsyncGroq(api_key=config.groq_api_key)
    return _groq_client


def keyword_search(query: str, data: SheetsData, filter_section: str | None = None) -> list[ContentItem]:
    """Простой поиск по ключевым словам и заголовку. Возвращает релевантные item-ы."""
    q = query.lower().strip()
    if not q:
        return []
    # Разбиваем запрос на токены длиннее 2 символов
    tokens = [t for t in re.findall(r"\w+", q) if len(t) > 2]
    if not tokens:
        return []

    scored: list[tuple[int, ContentItem]] = []
    for item in data.content:
        if filter_section and item.section != filter_section:
            continue
        haystack = f"{item.title} {item.category} {item.section} {item.keywords} {item.description}".lower()
        score = sum(1 for t in tokens if t in haystack)
        if score > 0:
            scored.append((score, item))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [item for _, item in scored[:5]]


async def ai_search(query: str, data: SheetsData, filter_section: str | None = None) -> list[ContentItem]:
    """AI-поиск через Groq. Возвращает список релевантных item-ов."""
    items = data.content
    if filter_section:
        items = [c for c in items if c.section == filter_section]
    if not items:
        return []

    # Готовим компактный каталог для LLM
    catalog = []
    for i, item in enumerate(items):
        catalog.append({
            "id": i,
            "section": item.section,
            "category": item.category,
            "title": item.title,
            "description": item.description,
        })

    system_prompt = (
        "Ты помощник который находит подходящие ресурсы стримера по запросу пользователя. "
        "На вход дан каталог ресурсов и вопрос пользователя на русском. "
        "Верни JSON-массив id (числа) релевантных ресурсов в порядке убывания релевантности. "
        "Максимум 5 id. Если ничего подходящего нет - верни пустой массив []. "
        "Отвечай ТОЛЬКО валидным JSON-массивом, без пояснений."
    )

    user_prompt = (
        f"Каталог:\n{json.dumps(catalog, ensure_ascii=False)}\n\n"
        f"Вопрос пользователя: {query}\n\n"
        f"Верни JSON-массив id релевантных ресурсов."
    )

    try:
        resp = await _groq().chat.completions.create(
            model=config.groq_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.1,
            max_tokens=200,
            response_format={"type": "json_object"},
        )
        raw = resp.choices[0].message.content or "[]"
        # Groq иногда возвращает {"ids": [...]} вместо чистого массива - обрабатываем оба
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            ids = next((v for v in parsed.values() if isinstance(v, list)), [])
        else:
            ids = parsed
        return [items[i] for i in ids if isinstance(i, int) and 0 <= i < len(items)]
    except Exception as e:
        log.warning(f"Groq поиск не удался: {e}")
        return []


async def hybrid_search(query: str, data: SheetsData, filter_section: str | None = None) -> list[ContentItem]:
    """Гибрид: сначала ключевые слова, если ничего - AI."""
    results = keyword_search(query, data, filter_section)
    if results:
        return results
    return await ai_search(query, data, filter_section)
