"""Алерти ризику відтоку (M13→M12). Раз на кілька годин: для кожного тенанта
знаходить учнів, які не заходили ≥ churn_alert_days (дефолт 5), і шле викладачу
одне попередження з бота тенанта. Анти-спам: не частіше 1 разу на 7 днів на учня
(users.last_churn_alert_at). «В ризику» також підсвічено бейджем у дашборді M6."""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

from aiogram import Bot
from sqlalchemy import func, select, update as sa_update

from core.db import SessionLocal
from core.models import Review, Tenant, User
from core.bot_registry import get_bot

logger = logging.getLogger(__name__)

CHECK_INTERVAL_S = 6 * 3600
ALERT_COOLDOWN_DAYS = 7


async def _teacher_of(session, tenant_id: int) -> User | None:
    return (await session.execute(
        select(User).where(
            User.tenant_id == tenant_id, User.role.in_(("teacher", "owner")),
        ).order_by(User.id).limit(1)
    )).scalar_one_or_none()


async def check_churn(bot: Bot) -> None:
    now = datetime.now(timezone.utc)
    cooldown_before = now - timedelta(days=ALERT_COOLDOWN_DAYS)
    try:
        async with SessionLocal() as s:
            tenants = (await s.execute(
                select(Tenant).where(Tenant.id != 1, Tenant.plan != "paused")
            )).scalars().all()

        total = 0
        for tenant in tenants:
            inactive_before = now - timedelta(days=tenant.churn_alert_days or 5)
            async with SessionLocal() as s:
                teacher = await _teacher_of(s, tenant.id)
                if teacher is None:
                    continue
                # останній review на учня (bulk)
                last_sq = (
                    select(Review.user_id, func.max(Review.reviewed_at).label("last"))
                    .where(Review.tenant_id == tenant.id)
                    .group_by(Review.user_id)
                    .subquery()
                )
                # учні тенанта, що не заходили давно (або взагалі — але тоді
                # total_reviews=0 і, ймовірно, ще онбордяться; вимагаємо, щоб
                # колись була активність, як у reengage) і поза cooldown алерту.
                rows = (await s.execute(
                    select(User, last_sq.c.last)
                    .join(last_sq, last_sq.c.user_id == User.id)
                    .where(
                        User.tenant_id == tenant.id,
                        User.role == "student",
                        last_sq.c.last < inactive_before,
                        (User.last_churn_alert_at.is_(None))
                        | (User.last_churn_alert_at < cooldown_before),
                    )
                )).all()

            if not rows:
                continue
            tenant_bot = get_bot(tenant.id) or bot
            alerted_ids = []
            for user, last in rows:
                days = (now - last).days if last else tenant.churn_alert_days
                name = user.first_name or (f"@{user.username}" if user.username else "учень")
                try:
                    await tenant_bot.send_message(
                        chat_id=teacher.telegram_id,
                        text=(f"⚠️ <b>{name}</b> не заходив(ла) {days} дн. — "
                              f"можливо, варто написати особисто."),
                    )
                    alerted_ids.append(user.id)
                    total += 1
                    await asyncio.sleep(0.05)
                except Exception as e:
                    logger.warning(f"churn alert send failed for teacher {teacher.telegram_id}: {e}")

            if alerted_ids:
                async with SessionLocal() as s:
                    await s.execute(
                        sa_update(User).where(User.id.in_(alerted_ids)).values(
                            last_churn_alert_at=now
                        )
                    )
                    await s.commit()

        if total:
            logger.info(f"⚠️ Sent {total} churn-risk alerts")
    except Exception as e:
        logger.error(f"churn alert job error: {e}", exc_info=True)


async def churn_alert_loop(bot: Bot) -> None:
    logger.info("⚠️ Churn-alert scheduler started (every 6h)")
    while True:
        try:
            await check_churn(bot)
        except Exception as e:
            logger.error(f"churn alert loop error: {e}")
        await asyncio.sleep(CHECK_INTERVAL_S)
