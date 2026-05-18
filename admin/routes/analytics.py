"""Страница Статистика - показывает свёртки за дни + сегодня из сырых events."""
import json
from collections import Counter
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Request

MSK = timezone(timedelta(hours=3))
from fastapi.responses import HTMLResponse
from sqlalchemy import select

from shared.db import async_session
from shared.models import DailyStat, Event, User

from ..auth import require_admin
from ..common import template_ctx, templates

router = APIRouter()


def _today_str() -> str:
    """Сегодняшняя дата по Москве."""
    return datetime.now(MSK).strftime("%Y-%m-%d")


def _to_msk_hour(dt: datetime) -> int:
    """Час в Москве из любого datetime."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(MSK).hour


def _to_msk_str(dt: datetime) -> str:
    """Форматирует datetime в МСК для шаблона."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(MSK).strftime("%d.%m %H:%M")


async def _today_stats() -> dict:
    """Считает статистику текущего дня (по Москве) по сырым events."""
    msk_today = datetime.now(MSK).replace(hour=0, minute=0, second=0, microsecond=0)
    start_utc = msk_today.astimezone(timezone.utc)
    async with async_session() as s:
        events = (
            await s.execute(select(Event).where(Event.created_at >= start_utc))
        ).scalars().all()

    unique_users = len({e.user_id for e in events})
    clicks = sum(1 for e in events if e.event_type.startswith("click_"))
    searches = sum(1 for e in events if e.event_type == "search")
    auto_comments = sum(1 for e in events if e.event_type == "auto_comment")

    by_section: Counter = Counter()
    by_category: Counter = Counter()
    by_link: Counter = Counter()
    by_hour: Counter = Counter()
    for e in events:
        by_hour[_to_msk_hour(e.created_at)] += 1
        if e.event_type == "click_section":
            by_section[e.target] += 1
        elif e.event_type in ("click_category", "click_subcategory"):
            by_category[e.target] += 1
        elif e.event_type == "click_leaf":
            by_link[e.target] += 1

    return dict(
        unique_users=unique_users,
        total_clicks=clicks,
        searches=searches,
        auto_comments=auto_comments,
        by_section=dict(by_section.most_common()),
        by_category=dict(by_category.most_common()),
        by_link=by_link.most_common(20),
        by_hour={h: by_hour.get(h, 0) for h in range(24)},
    )


@router.get("/stats", response_class=HTMLResponse)
async def stats_page(request: Request, user: User = Depends(require_admin)):
    today = await _today_stats()
    today_str = _today_str()

    # История из daily_stats: последние 30 дней
    cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d")
    async with async_session() as s:
        rows = (
            await s.execute(
                select(DailyStat)
                .where(DailyStat.date >= cutoff)
                .order_by(DailyStat.date)
            )
        ).scalars().all()
        # Последние свободные вопросы (последние 50 за всё время сырых events)
        recent_searches = (
            await s.execute(
                select(Event)
                .where(Event.event_type == "search")
                .order_by(Event.created_at.desc())
                .limit(50)
            )
        ).scalars().all()

    history = []
    sum_unique_7 = 0
    sum_unique_30 = 0
    sum_clicks_30 = 0
    section_total: Counter = Counter()
    category_total: Counter = Counter()
    link_total: Counter = Counter()
    hour_total: Counter = Counter()
    searches_total: Counter = Counter()
    auto_comment_total = 0
    search_count_30 = 0

    week_start = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")

    for r in rows:
        history.append({"date": r.date, "clicks": r.total_clicks, "users": r.unique_users})
        sum_unique_30 += r.unique_users
        sum_clicks_30 += r.total_clicks
        search_count_30 += r.searches
        auto_comment_total += r.auto_comments
        if r.date >= week_start:
            sum_unique_7 += r.unique_users
        try:
            for k, v in json.loads(r.by_section or "{}").items():
                section_total[k] += v
            for k, v in json.loads(r.by_category or "{}").items():
                category_total[k] += v
            for url, cnt in json.loads(r.by_link or "[]"):
                link_total[url] += cnt
            for h, v in json.loads(r.by_hour or "{}").items():
                hour_total[int(h)] += v
            for term, cnt in json.loads(r.top_searches or "[]"):
                searches_total[term] += cnt
        except Exception:
            pass

    # Складываем сегодня в общие
    for k, v in today["by_section"].items():
        section_total[k] += v
    for k, v in today["by_category"].items():
        category_total[k] += v
    for url, cnt in today["by_link"]:
        link_total[url] += cnt
    for h, v in today["by_hour"].items():
        hour_total[h] += v
    auto_comment_total += today["auto_comments"]
    search_count_30 += today["searches"]

    # Дополняем history сегодняшним днём
    history.append({"date": today_str + " (сегодня)", "clicks": today["total_clicks"], "users": today["unique_users"]})
    sum_unique_7 += today["unique_users"]
    sum_unique_30 += today["unique_users"]
    sum_clicks_30 += today["total_clicks"]

    return templates.TemplateResponse(
        "stats.html",
        await template_ctx(
            request, user,
            active="stats",
            today=today,
            history=history,
            week_users=sum_unique_7,
            month_users=sum_unique_30,
            month_clicks=sum_clicks_30,
            month_searches=search_count_30,
            month_autocomments=auto_comment_total,
            top_sections=section_total.most_common(10),
            top_categories=category_total.most_common(10),
            top_links=link_total.most_common(10),
            top_searches=searches_total.most_common(20),
            by_hour={h: hour_total.get(h, 0) for h in range(24)},
            recent_searches=recent_searches,
            to_msk=_to_msk_str,
        ),
    )
