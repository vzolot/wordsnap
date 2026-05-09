"""Збираємо щоденний звіт по продукту для адміна.

Вся статистика — з нашої БД (User, Word, Review, PaymentHistory). PostHog
не зачіпаємо: тут детальніша картина, плюс це швидше і не залежить від
зовнішнього API.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from html import escape
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func, or_, select

from .db import SessionLocal
from .models import PaymentHistory, Review, User, Word


def _kyiv_today() -> date:
    try:
        return datetime.now(ZoneInfo("Europe/Kiev")).date()
    except ZoneInfoNotFoundError:
        return datetime.now(timezone.utc).date()


def _utc_window(start_local: date, days: int = 1) -> tuple[datetime, datetime]:
    """Повертає UTC-проміжок який покриває [start_local, start_local+days)
    у Києві — для фільтрування по UTC-стампах reviewed_at/created_at."""
    try:
        kyiv = ZoneInfo("Europe/Kiev")
    except ZoneInfoNotFoundError:
        kyiv = timezone.utc
    start_dt = datetime.combine(start_local, datetime.min.time(), tzinfo=kyiv)
    end_dt = start_dt + timedelta(days=days)
    return start_dt.astimezone(timezone.utc), end_dt.astimezone(timezone.utc)


async def _gather_metrics(report_day: date, is_partial_day: bool) -> dict:
    """Збирає метрики за `report_day` (Europe/Kiev day).

    is_partial_day=True означає що день ще йде (use case: /stats live).
    Тоді кінцеве вікно — поточний UTC-момент. Інакше — повних 24 години."""
    day_start_utc, day_end_utc = _utc_window(report_day, 1)
    today_local = _kyiv_today()
    week_start_utc, _ = _utc_window(today_local - timedelta(days=6), 7)
    now = datetime.now(timezone.utc)
    if is_partial_day and day_end_utc > now:
        day_end_utc = now

    async with SessionLocal() as s:
        # Users — single sweep + кілька маленьких scalar-запитів
        total_users = (await s.execute(select(func.count(User.id)))).scalar() or 0
        new_users_today = (await s.execute(
            select(func.count(User.id)).where(
                User.created_at >= day_start_utc,
                User.created_at < day_end_utc,
            )
        )).scalar() or 0
        dau = (await s.execute(
            select(func.count(User.id)).where(
                User.last_active_at >= day_start_utc,
                User.last_active_at < day_end_utc,
            )
        )).scalar() or 0
        wau = (await s.execute(
            select(func.count(User.id)).where(User.last_active_at >= week_start_utc)
        )).scalar() or 0

        # Pro & trial
        active_pro = (await s.execute(
            select(func.count(User.id)).where(
                User.plan == "pro",
                User.plan_expires_at > now,
            )
        )).scalar() or 0
        trial_users = (await s.execute(
            select(func.count(User.id)).where(
                User.plan != "pro",
                User.created_at > now - timedelta(days=7),
            )
        )).scalar() or 0
        trial_ending_soon = (await s.execute(
            select(func.count(User.id)).where(
                User.plan != "pro",
                User.created_at <= now - timedelta(days=5),
                User.created_at > now - timedelta(days=7),
            )
        )).scalar() or 0

        # Payments
        revenue_filter = or_(
            PaymentHistory.status == "success",
            PaymentHistory.transaction_status == "Approved",
        )
        revenue_today = (await s.execute(
            select(func.coalesce(func.sum(PaymentHistory.amount), 0)).where(
                revenue_filter,
                PaymentHistory.created_at >= day_start_utc,
                PaymentHistory.created_at < day_end_utc,
            )
        )).scalar() or 0
        payments_today_count = (await s.execute(
            select(func.count(PaymentHistory.id)).where(
                revenue_filter,
                PaymentHistory.created_at >= day_start_utc,
                PaymentHistory.created_at < day_end_utc,
            )
        )).scalar() or 0
        revenue_total = (await s.execute(
            select(func.coalesce(func.sum(PaymentHistory.amount), 0)).where(revenue_filter)
        )).scalar() or 0

        # Words on report-day + by source
        words_today = (await s.execute(
            select(func.count(Word.id)).where(
                Word.created_at >= day_start_utc,
                Word.created_at < day_end_utc,
            )
        )).scalar() or 0
        unique_word_users_today = (await s.execute(
            select(func.count(func.distinct(Word.user_id))).where(
                Word.created_at >= day_start_utc,
                Word.created_at < day_end_utc,
            )
        )).scalar() or 0
        words_by_source = (await s.execute(
            select(Word.source, func.count(Word.id)).where(
                Word.created_at >= day_start_utc,
                Word.created_at < day_end_utc,
            ).group_by(Word.source)
        )).all()

        # Reviews on report-day
        reviews_today = (await s.execute(
            select(func.count(Review.id)).where(
                Review.reviewed_at >= day_start_utc,
                Review.reviewed_at < day_end_utc,
            )
        )).scalar() or 0

        # Engagement: avg streak among users that have at least 1 review ever
        avg_streak = (await s.execute(
            select(func.avg(User.streak_days)).where(User.streak_days > 0)
        )).scalar() or 0

        # Top streak users (3)
        top_users_rows = (await s.execute(
            select(User.first_name, User.streak_days, User.total_xp)
            .where(User.streak_days > 0)
            .order_by(User.streak_days.desc(), User.total_xp.desc())
            .limit(3)
        )).all()

    return {
        "report_day": report_day,
        "is_partial": is_partial_day,
        "users": {
            "total": int(total_users),
            "new_today": int(new_users_today),
            "dau": int(dau),
            "wau": int(wau),
        },
        "pro": {
            "active": int(active_pro),
            "trial": int(trial_users),
            "trial_ending_soon": int(trial_ending_soon),
            "payments_today_count": int(payments_today_count),
            "revenue_today": float(revenue_today),
            "revenue_total": float(revenue_total),
        },
        "activity": {
            "words_added": int(words_today),
            "unique_word_users": int(unique_word_users_today),
            "words_by_source": [(src or "unknown", int(n)) for src, n in words_by_source],
            "reviews": int(reviews_today),
        },
        "engagement": {
            "avg_streak": round(float(avg_streak), 1),
            "reviews_per_dau": round(reviews_today / dau, 1) if dau else 0,
        },
        "top_users": [
            {
                "name": (name or "—")[:14],
                "streak": int(streak or 0),
                "xp": int(xp or 0),
            }
            for name, streak, xp in top_users_rows
        ],
    }


def _format_html(m: dict) -> str:
    u = m["users"]
    p = m["pro"]
    a = m["activity"]
    e = m["engagement"]

    sources_line = (
        ", ".join(f"{src}: {n}" for src, n in a["words_by_source"])
        if a["words_by_source"] else "—"
    )

    top_lines = "\n".join(
        f"  • <b>{escape(t['name'])}</b> — {t['streak']}d, {t['xp']} XP"
        for t in m["top_users"]
    ) or "  —"

    trial_note = (
        f" (з них {p['trial_ending_soon']} закінчуються 1-2 дні)"
        if p["trial_ending_soon"] else ""
    )

    period_label = (
        f"сьогодні (live, {m['report_day']})"
        if m["is_partial"]
        else f"за {m['report_day']}"
    )
    active_label = "Активних сьогодні" if m["is_partial"] else "Активних того дня"

    return (
        f"📊 <b>WordSnap — {period_label}</b>\n"
        f"\n"
        f"👥 <b>Юзери</b>\n"
        f"  Всього: {u['total']} (+{u['new_today']} нових)\n"
        f"  {active_label}: {u['dau']} · тиждень: {u['wau']}\n"
        f"\n"
        f"💰 <b>Pro</b>\n"
        f"  Активних: {p['active']} · Trial: {p['trial']}{trial_note}\n"
        f"  Платежів за добу: {p['payments_today_count']} · ${p['revenue_today']:.2f}\n"
        f"  Total revenue: ${p['revenue_total']:.2f}\n"
        f"\n"
        f"📚 <b>Активність</b>\n"
        f"  Слів додано: {a['words_added']} ({a['unique_word_users']} юзерів)\n"
        f"  Sources: {escape(sources_line)}\n"
        f"  Повторень: {a['reviews']}\n"
        f"\n"
        f"🎯 <b>Engagement</b>\n"
        f"  Avg streak: {e['avg_streak']}d · Reviews/DAU: {e['reviews_per_dau']}\n"
        f"\n"
        f"🔥 <b>Топ streaks</b>\n"
        f"{top_lines}"
    )


async def build_daily_report(*, for_yesterday: bool) -> str:
    """Збирає метрики і повертає HTML-форматований звіт.

    for_yesterday=True → повних 24 год вчора Kyiv (use case: 09:00 авто-push)
    for_yesterday=False → сьогодні з опівночі до зараз (use case: /stats live)
    """
    today_local = _kyiv_today()
    if for_yesterday:
        report_day = today_local - timedelta(days=1)
        is_partial = False
    else:
        report_day = today_local
        is_partial = True
    metrics = await _gather_metrics(report_day, is_partial)
    return _format_html(metrics)
