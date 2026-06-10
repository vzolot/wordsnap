"""Збираємо щоденний / місячний звіт по продукту для адміна.

Вся статистика — з нашої БД (User, Word, Review, PaymentHistory). PostHog
не зачіпаємо: тут детальніша картина, плюс це швидше і не залежить від
зовнішнього API.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from html import escape
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func, or_, select

from .db import SessionLocal
from .models import PaymentHistory, Review, User, Word
from .streaks import calculate_streak

PeriodKind = Literal["today_live", "yesterday_full", "month_30d"]


def _kyiv_today() -> date:
    try:
        return datetime.now(ZoneInfo("Europe/Kiev")).date()
    except ZoneInfoNotFoundError:
        return datetime.now(timezone.utc).date()


def _kyiv_tz() -> ZoneInfo | timezone:
    try:
        return ZoneInfo("Europe/Kiev")
    except ZoneInfoNotFoundError:
        return timezone.utc


def _utc_window(start_local: date, days: int) -> tuple[datetime, datetime]:
    kyiv = _kyiv_tz()
    start_dt = datetime.combine(start_local, datetime.min.time(), tzinfo=kyiv)
    end_dt = start_dt + timedelta(days=days)
    return start_dt.astimezone(timezone.utc), end_dt.astimezone(timezone.utc)


def _resolve_period(period: PeriodKind) -> dict:
    """Повертає bounds + display-label під обраний режим."""
    today_local = _kyiv_today()
    now = datetime.now(timezone.utc)

    if period == "today_live":
        start_local = today_local
        days = 1
        is_partial = True
        period_label = f"сьогодні (live, {today_local})"
        active_label = "Активних сьогодні"
        period_word = "за добу"
    elif period == "yesterday_full":
        start_local = today_local - timedelta(days=1)
        days = 1
        is_partial = False
        period_label = f"за {start_local}"
        active_label = "Активних того дня"
        period_word = "за добу"
    else:  # month_30d
        start_local = today_local - timedelta(days=29)
        days = 30
        is_partial = True
        period_label = f"за 30 днів ({start_local} — {today_local})"
        active_label = "Активних за період"
        period_word = "за період"

    day_start_utc, day_end_utc = _utc_window(start_local, days)
    if is_partial and day_end_utc > now:
        day_end_utc = now

    return {
        "start_local": start_local,
        "end_local_exclusive": start_local + timedelta(days=days),
        "day_start_utc": day_start_utc,
        "day_end_utc": day_end_utc,
        "now": now,
        "today_local": today_local,
        "is_partial": is_partial,
        "period_label": period_label,
        "active_label": active_label,
        "period_word": period_word,
    }


async def _gather_metrics(p: dict) -> dict:
    day_start_utc = p["day_start_utc"]
    day_end_utc = p["day_end_utc"]
    today_local = p["today_local"]
    now = p["now"]
    week_start_utc, _ = _utc_window(today_local - timedelta(days=6), 7)

    async with SessionLocal() as s:
        # Real users only — `users.is_test_account=TRUE` is the founder/internal
        # testers. Used as a subquery filter on every Review/Word/PaymentHistory
        # query (via user_id IN real_users) and as a WHERE on User queries.
        real_users = select(User.id).where(User.is_test_account.is_(False))
        real_user_filter = User.is_test_account.is_(False)

        # Users — point-in-time totals + period-bounded counts
        total_users = (await s.execute(
            select(func.count(User.id)).where(real_user_filter)
        )).scalar() or 0
        new_users_in_period = (await s.execute(
            select(func.count(User.id)).where(
                real_user_filter,
                User.created_at >= day_start_utc,
                User.created_at < day_end_utc,
            )
        )).scalar() or 0
        # "Active" = users who actually did a review in the window. (NB:
        # users.last_active_at is a dead column — never updated, always ==
        # created_at — so it measured "recently registered", not activity.
        # Reviews are the real activity signal.)
        active_in_period = (await s.execute(
            select(func.count(func.distinct(Review.user_id))).where(
                Review.user_id.in_(real_users),
                Review.reviewed_at >= day_start_utc,
                Review.reviewed_at < day_end_utc,
            )
        )).scalar() or 0
        wau = (await s.execute(
            select(func.count(func.distinct(Review.user_id))).where(
                Review.user_id.in_(real_users),
                Review.reviewed_at >= week_start_utc,
            )
        )).scalar() or 0

        # Pro & trial — всі point-in-time
        active_pro = (await s.execute(
            select(func.count(User.id)).where(
                real_user_filter,
                User.plan == "pro",
                User.plan_expires_at > now,
            )
        )).scalar() or 0
        trial_users = (await s.execute(
            select(func.count(User.id)).where(
                real_user_filter,
                User.plan != "pro",
                User.created_at > now - timedelta(days=7),
            )
        )).scalar() or 0
        trial_ending_soon = (await s.execute(
            select(func.count(User.id)).where(
                real_user_filter,
                User.plan != "pro",
                User.created_at <= now - timedelta(days=5),
                User.created_at > now - timedelta(days=7),
            )
        )).scalar() or 0

        # Payments. `revenue_*` totals are USD-only — TON / Stars (XTR) live
        # in the same `payment_history` table but their `amount` column
        # stores the native unit (1.0 TON, 129★, etc.) which would mislead
        # if summed alongside dollars. The 2026-06-09 founder TON test
        # showed up as "+$1.00" in the daily report and surfaced this bug.
        # Multi-currency display (separate TON / Stars lines) is a TODO; for
        # now we filter to USD so the headline figure stays accurate.
        revenue_filter = or_(
            PaymentHistory.status == "success",
            PaymentHistory.transaction_status == "Approved",
        )
        usd_only = PaymentHistory.currency == "USD"
        revenue_period = (await s.execute(
            select(func.coalesce(func.sum(PaymentHistory.amount), 0)).where(
                PaymentHistory.user_id.in_(real_users),
                revenue_filter,
                usd_only,
                PaymentHistory.created_at >= day_start_utc,
                PaymentHistory.created_at < day_end_utc,
            )
        )).scalar() or 0
        payments_period_count = (await s.execute(
            select(func.count(PaymentHistory.id)).where(
                PaymentHistory.user_id.in_(real_users),
                revenue_filter,
                usd_only,
                PaymentHistory.created_at >= day_start_utc,
                PaymentHistory.created_at < day_end_utc,
            )
        )).scalar() or 0
        revenue_total = (await s.execute(
            select(func.coalesce(func.sum(PaymentHistory.amount), 0)).where(
                PaymentHistory.user_id.in_(real_users),
                revenue_filter,
                usd_only,
            )
        )).scalar() or 0

        # Words in period + by source
        words_in_period = (await s.execute(
            select(func.count(Word.id)).where(
                Word.user_id.in_(real_users),
                Word.created_at >= day_start_utc,
                Word.created_at < day_end_utc,
            )
        )).scalar() or 0
        unique_word_users = (await s.execute(
            select(func.count(func.distinct(Word.user_id))).where(
                Word.user_id.in_(real_users),
                Word.created_at >= day_start_utc,
                Word.created_at < day_end_utc,
            )
        )).scalar() or 0
        words_by_source = (await s.execute(
            select(Word.source, func.count(Word.id)).where(
                Word.user_id.in_(real_users),
                Word.created_at >= day_start_utc,
                Word.created_at < day_end_utc,
            ).group_by(Word.source)
        )).all()

        # Reviews in period
        reviews_in_period = (await s.execute(
            select(func.count(Review.id)).where(
                Review.user_id.in_(real_users),
                Review.reviewed_at >= day_start_utc,
                Review.reviewed_at < day_end_utc,
            )
        )).scalar() or 0

        # Streaks computed from review history (users.streak_days is a dead
        # column — never written). Only users who reviewed today or yesterday
        # can have a live streak, so we only score those candidates.
        candidate_ids = [
            row[0] for row in (await s.execute(
                select(func.distinct(Review.user_id)).where(
                    Review.user_id.in_(real_users),
                    Review.reviewed_at >= now - timedelta(days=2),
                )
            )).all()
        ]
        streak_by_id: dict[int, int] = {}
        for uid in candidate_ids:
            st = await calculate_streak(s, uid)
            if st > 0:
                streak_by_id[uid] = st
        avg_streak = (
            sum(streak_by_id.values()) / len(streak_by_id) if streak_by_id else 0
        )
        top_ids = sorted(streak_by_id, key=lambda u: streak_by_id[u], reverse=True)[:3]
        top_users_rows = []
        if top_ids:
            name_map = {
                r[0]: (r[1], r[2]) for r in (await s.execute(
                    select(User.id, User.first_name, User.total_xp).where(User.id.in_(top_ids))
                )).all()
            }
            for uid in top_ids:
                first_name, total_xp = name_map.get(uid, (None, 0))
                top_users_rows.append((first_name, streak_by_id[uid], total_xp))

    return {
        "users": {
            "total": int(total_users),
            "new_in_period": int(new_users_in_period),
            "active_in_period": int(active_in_period),
            "wau": int(wau),
        },
        "pro": {
            "active": int(active_pro),
            "trial": int(trial_users),
            "trial_ending_soon": int(trial_ending_soon),
            "payments_count": int(payments_period_count),
            "revenue_period": float(revenue_period),
            "revenue_total": float(revenue_total),
        },
        "activity": {
            "words_added": int(words_in_period),
            "unique_word_users": int(unique_word_users),
            "words_by_source": [(src or "unknown", int(n)) for src, n in words_by_source],
            "reviews": int(reviews_in_period),
        },
        "engagement": {
            "avg_streak": round(float(avg_streak), 1),
            "reviews_per_active": (
                round(reviews_in_period / active_in_period, 1)
                if active_in_period else 0
            ),
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


def _format_html(p: dict, m: dict) -> str:
    u = m["users"]
    pr = m["pro"]
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
        f" (з них {pr['trial_ending_soon']} закінчуються 1-2 дні)"
        if pr["trial_ending_soon"] else ""
    )

    return (
        f"📊 <b>WordSnap — {p['period_label']}</b>\n"
        f"\n"
        f"👥 <b>Юзери</b>\n"
        f"  Всього: {u['total']} (+{u['new_in_period']} нових)\n"
        f"  {p['active_label']}: {u['active_in_period']} · тиждень: {u['wau']}\n"
        f"\n"
        f"💰 <b>Pro</b>\n"
        f"  Активних: {pr['active']} · Trial: {pr['trial']}{trial_note}\n"
        f"  Платежів {p['period_word']}: {pr['payments_count']} · ${pr['revenue_period']:.2f}\n"
        f"  Total revenue: ${pr['revenue_total']:.2f}\n"
        f"\n"
        f"📚 <b>Активність</b>\n"
        f"  Слів додано: {a['words_added']} ({a['unique_word_users']} юзерів)\n"
        f"  Sources: {escape(sources_line)}\n"
        f"  Повторень: {a['reviews']}\n"
        f"\n"
        f"🎯 <b>Engagement</b>\n"
        f"  Avg streak: {e['avg_streak']}d · Reviews/active: {e['reviews_per_active']}\n"
        f"\n"
        f"🔥 <b>Топ streaks</b>\n"
        f"{top_lines}"
    )


async def build_report(period: PeriodKind) -> str:
    """Збирає метрики за вказаний період і повертає HTML-форматований звіт."""
    p = _resolve_period(period)
    metrics = await _gather_metrics(p)
    return _format_html(p, metrics)


# Backwards-compat alias — стара назва функції з попередньої ітерації.
async def build_daily_report(*, for_yesterday: bool) -> str:
    return await build_report("yesterday_full" if for_yesterday else "today_live")
