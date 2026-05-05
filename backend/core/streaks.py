"""Хелпери для streak та лічильників повторень.

Виокремлено з webhook/api_routes.py щоб scheduler/reminder.py і інші місця
могли використовувати ту ж логіку без циклічних залежностей.
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Review


async def calculate_streak(session: AsyncSession, user_id: int) -> int:
    """Підрахунок підряд днів з повтореннями (закінчуючи сьогодні чи вчора)."""
    rows = await session.execute(
        select(func.date(Review.reviewed_at)).where(
            Review.user_id == user_id,
        ).distinct().order_by(func.date(Review.reviewed_at).desc())
    )
    dates = [r[0] for r in rows.all()]
    if not dates:
        return 0

    today = datetime.now(timezone.utc).date()
    yesterday = today - timedelta(days=1)
    if dates[0] != today and dates[0] != yesterday:
        return 0

    streak = 1
    for i in range(1, len(dates)):
        if dates[i] == dates[i - 1] - timedelta(days=1):
            streak += 1
        else:
            break
    return streak


async def reviewed_today(session: AsyncSession, user_id: int) -> int:
    """Скільки повторень зроблено за сьогодні (UTC)."""
    today_start = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    n = (await session.execute(
        select(func.count(Review.id)).where(
            Review.user_id == user_id,
            Review.reviewed_at >= today_start,
        )
    )).scalar() or 0
    return n
