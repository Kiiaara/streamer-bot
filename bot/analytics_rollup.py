"""Демон ежедневной свёртки сырых events в daily_stats и удаления старых событий.
Запускается фоновой задачей при старте бота."""
import asyncio
import json
import logging
from collections import Counter
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select

from shared.db import async_session
from shared.models import DailyStat, Event

log = logging.getLogger(__name__)

EVENTS_TTL_DAYS = 30      # сколько хранить сырые события
ROLLUP_INTERVAL = 3600    # как часто проверять что нужно свернуть (1 час)


async def rollup_day(date_str: str):
    """Свёртывает все события указанной даты (YYYY-MM-DD) в daily_stats. Идемпотентно."""
    start = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    end = start + timedelta(days=1)

    async with async_session() as s:
        events = (
            await s.execute(
                select(Event).where(Event.created_at >= start, Event.created_at < end)
            )
        ).scalars().all()

        if not events:
            return  # ничего сворачивать

        unique_users = len({e.user_id for e in events})
        clicks = 0
        searches = 0
        auto_comments = 0
        by_section: Counter[str] = Counter()
        by_category: Counter[str] = Counter()
        by_link: Counter[str] = Counter()
        by_hour: Counter[int] = Counter()
        search_words: Counter[str] = Counter()

        for e in events:
            by_hour[e.created_at.hour] += 1
            if e.event_type == "click_section":
                clicks += 1
                by_section[e.target] += 1
            elif e.event_type == "click_category":
                clicks += 1
                by_category[e.target] += 1
            elif e.event_type == "click_subcategory":
                clicks += 1
                by_category[e.target] += 1
            elif e.event_type == "click_leaf":
                clicks += 1
                by_link[e.target] += 1
            elif e.event_type == "search":
                searches += 1
                # Раскладываем поисковый запрос на слова длиннее 3 символов
                for w in e.target.lower().split():
                    w = "".join(c for c in w if c.isalnum())
                    if len(w) > 3:
                        search_words[w] += 1
            elif e.event_type == "auto_comment":
                auto_comments += 1

        # Upsert в daily_stats
        existing = (
            await s.execute(select(DailyStat).where(DailyStat.date == date_str))
        ).scalar_one_or_none()
        payload = dict(
            unique_users=unique_users,
            total_clicks=clicks,
            searches=searches,
            auto_comments=auto_comments,
            by_section=json.dumps(dict(by_section.most_common()), ensure_ascii=False),
            by_category=json.dumps(dict(by_category.most_common()), ensure_ascii=False),
            by_link=json.dumps(by_link.most_common(20), ensure_ascii=False),
            by_hour=json.dumps({str(h): by_hour.get(h, 0) for h in range(24)}, ensure_ascii=False),
            top_searches=json.dumps(search_words.most_common(20), ensure_ascii=False),
        )
        if existing:
            for k, v in payload.items():
                setattr(existing, k, v)
        else:
            s.add(DailyStat(date=date_str, **payload))
        await s.commit()
        log.info(f"daily_stats: {date_str} - users={unique_users}, clicks={clicks}")


async def cleanup_old_events():
    """Удаляет сырые события старше EVENTS_TTL_DAYS дней."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=EVENTS_TTL_DAYS)
    async with async_session() as s:
        result = await s.execute(delete(Event).where(Event.created_at < cutoff))
        await s.commit()
        if result.rowcount:
            log.info(f"Удалено старых событий: {result.rowcount}")


async def run_pending_rollups():
    """Сворачивает все дни от последнего свёрнутого до вчерашнего."""
    async with async_session() as s:
        last = (
            await s.execute(select(DailyStat.date).order_by(DailyStat.date.desc()).limit(1))
        ).scalar()

    today = datetime.now(timezone.utc).date()
    if last:
        last_date = datetime.strptime(last, "%Y-%m-%d").date()
        start = last_date + timedelta(days=1)
    else:
        # Если ещё нет свёрток - смотрим самое старое событие
        async with async_session() as s:
            oldest = (
                await s.execute(select(func.min(Event.created_at)))
            ).scalar()
        if oldest is None:
            return
        start = oldest.date()

    d = start
    while d < today:
        await rollup_day(d.strftime("%Y-%m-%d"))
        d += timedelta(days=1)


async def analytics_loop():
    """Бесконечный цикл - свёртка и очистка раз в час."""
    while True:
        try:
            await run_pending_rollups()
            await cleanup_old_events()
        except Exception as e:
            log.exception(f"analytics_loop error: {e}")
        await asyncio.sleep(ROLLUP_INTERVAL)
