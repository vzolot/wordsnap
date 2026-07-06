"""Груповий лідерборд (M16). Тижневий рейтинг за повтореннями + стріком, у
межах групи (school) або всіх учнів тенанта (репетитор).

Минулі тижні «зберігаються» без окремої таблиці — рахуються з історії reviews
за довільне ISO-тижневе вікно (Пн 00:00 UTC → Нд 23:59). Анти-накрутка: рахуємо
лише реальні SM-2 ревʼю (усі рядки reviews створюються через process_review),
дедуплікуючи по (word_id) в межах дня, щоб спам-тапи по одному слову не крутили.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from .db import SessionLocal
from .models import GroupMember, Review, User


def current_week_bounds(now: datetime | None = None) -> tuple[datetime, datetime]:
    """(Пн 00:00 UTC поточного тижня, now). Для минулих тижнів передавай явні."""
    now = now or datetime.now(timezone.utc)
    monday = (now - timedelta(days=now.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return monday, now


async def _member_ids(session, tenant_id: int, group_id: int | None) -> list[int]:
    if group_id is not None:
        rows = (await session.execute(
            select(GroupMember.user_id).where(GroupMember.group_id == group_id)
        )).scalars().all()
        return list(rows)
    rows = (await session.execute(
        select(User.id).where(User.tenant_id == tenant_id, User.role == "student")
    )).scalars().all()
    return list(rows)


async def group_leaderboard(
    tenant_id: int, group_id: int | None = None,
    since: datetime | None = None, until: datetime | None = None, top: int = 20,
) -> dict:
    """Рейтинг за тиждень. Повертає {rows: [{user_id, name, reviews, streak,
    rank}], week_start, week_end}."""
    if since is None or until is None:
        since, until = current_week_bounds()

    async with SessionLocal() as s:
        ids = await _member_ids(s, tenant_id, group_id)
        if not ids:
            return {"rows": [], "week_start": since.isoformat(), "week_end": until.isoformat()}

        # Анти-накрутка: distinct (user_id, word_id, day) → рахуємо унікальні
        # слово-дні, не кожен тап.
        distinct_sq = (
            select(
                Review.user_id.label("uid"),
                Review.word_id.label("wid"),
                func.date(Review.reviewed_at).label("d"),
            )
            .where(
                Review.tenant_id == tenant_id,
                Review.user_id.in_(ids),
                Review.reviewed_at >= since,
                Review.reviewed_at <= until,
            )
            .distinct()
            .subquery()
        )
        counts = dict((uid, int(n)) for uid, n in (await s.execute(
            select(distinct_sq.c.uid, func.count()).group_by(distinct_sq.c.uid)
        )).all())

        users = {u.id: u for u in (await s.execute(
            select(User).where(User.id.in_(ids))
        )).scalars().all()}

    ranked = []
    for uid in ids:
        u = users.get(uid)
        if not u:
            continue
        reviews = counts.get(uid, 0)
        if reviews == 0:
            continue  # у рейтингу лише активні цього тижня
        ranked.append({
            "user_id": uid,
            "name": (u.first_name or (f"@{u.username}" if u.username else f"id{u.telegram_id}"))[:16],
            "reviews": reviews,
            "streak": u.streak_days or 0,
        })
    ranked.sort(key=lambda r: (r["reviews"], r["streak"]), reverse=True)
    for i, r in enumerate(ranked):
        r["rank"] = i + 1
    return {
        "rows": ranked[:top],
        "all_ranks": {r["user_id"]: r["rank"] for r in ranked},
        "total": len(ranked),
        "week_start": since.isoformat(),
        "week_end": until.isoformat(),
    }
