"""Місячний PDF-звіт (M15). 1-го числа генерує PDF по кожному учню тенантів з
monthly_report_enabled і надсилає викладачу файлом у Telegram (він пересилає
батькам/учню). Анти-дубль: app_state ключ per-tenant з міткою місяця."""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

from aiogram import Bot
from sqlalchemy import func, select

from core.db import SessionLocal
from core.models import Review, Tenant, User, Word
from core.app_state import get_state, set_state
from core.telegram_send import send_document
from core.pdf_report import build_student_report

logger = logging.getLogger(__name__)

CHECK_INTERVAL_S = 3600  # раз на годину; діємо лише 1-го числа й один раз/тенант/міс


async def _prev_month_bounds(now: datetime) -> tuple[datetime, datetime, int, int]:
    first_this = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    last_prev_end = first_this
    prev_last_day = first_this - timedelta(days=1)
    first_prev = prev_last_day.replace(day=1)
    return first_prev, last_prev_end, prev_last_day.month, prev_last_day.year


async def _student_stats(s, tenant_id: int, uid: int, since, until) -> dict:
    reviews = (await s.execute(
        select(func.count(Review.id)).where(
            Review.user_id == uid, Review.reviewed_at >= since, Review.reviewed_at < until,
        )
    )).scalar() or 0
    new_words = (await s.execute(
        select(func.count(Word.id)).where(
            Word.user_id == uid, Word.created_at >= since, Word.created_at < until,
        )
    )).scalar() or 0
    learned = (await s.execute(
        select(func.count(Word.id)).where(Word.user_id == uid, Word.status == "mastered")
    )).scalar() or 0
    rows = (await s.execute(
        select(func.date(Review.reviewed_at), func.count(Review.id)).where(
            Review.user_id == uid, Review.reviewed_at >= since, Review.reviewed_at < until,
        ).group_by(func.date(Review.reviewed_at))
    )).all()
    activity = {str(d): int(n) for d, n in rows}
    return {"reviews": int(reviews), "new_words": int(new_words),
            "learned": int(learned), "activity": activity}


async def _run_for_tenant(bot: Bot, tenant: Tenant, since, until, month, year) -> int:
    async with SessionLocal() as s:
        teacher = (await s.execute(
            select(User).where(
                User.tenant_id == tenant.id, User.role.in_(("teacher", "owner")),
            ).order_by(User.id).limit(1)
        )).scalar_one_or_none()
        students = (await s.execute(
            select(User).where(User.tenant_id == tenant.id, User.role == "student")
        )).scalars().all()
    if teacher is None or not students:
        return 0
    sent = 0
    for student in students:
        async with SessionLocal() as s:
            st = await _student_stats(s, tenant.id, student.id, since, until)
        if st["reviews"] == 0 and st["new_words"] == 0:
            continue  # неактивних цього місяця пропускаємо
        name = student.first_name or (f"@{student.username}" if student.username else f"id{student.telegram_id}")
        try:
            pdf = build_student_report(
                brand=tenant.display_name, color_primary=tenant.color_primary,
                student_name=name, month=month, year=year,
                reviews=st["reviews"], learned=st["learned"],
                new_words=st["new_words"], streak=student.streak_days or 0,
                activity=st["activity"], target_lang=student.target_lang,
            )
            await send_document(
                chat_id=teacher.telegram_id, file_bytes=pdf,
                filename=f"report-{name}-{year}-{month:02d}.pdf",
                caption=f"📄 Звіт про прогрес: {name} · {month:02d}.{year}",
                mime_type="application/pdf", tenant_id=tenant.id,
            )
            sent += 1
            await asyncio.sleep(0.1)
        except Exception as e:
            logger.warning(f"monthly report failed for student {student.id}: {e}")
    return sent


async def check_monthly_reports(bot: Bot) -> None:
    now = datetime.now(timezone.utc)
    if now.day != 1:
        return
    tag = f"{now.year}-{now.month:02d}"
    try:
        since, until, pmonth, pyear = await _prev_month_bounds(now)
        async with SessionLocal() as s:
            tenants = (await s.execute(
                select(Tenant).where(Tenant.monthly_report_enabled.is_(True))
            )).scalars().all()
        for tenant in tenants:
            key = f"monthly_report_sent:{tenant.id}"
            if (await get_state(key)) == tag:
                continue  # вже слали цього місяця
            n = await _run_for_tenant(bot, tenant, since, until, pmonth, pyear)
            await set_state(key, tag)
            if n:
                logger.info(f"📄 Monthly reports: {n} for tenant {tenant.slug}")
    except Exception as e:
        logger.error(f"monthly report job error: {e}", exc_info=True)


async def monthly_report_loop(bot: Bot) -> None:
    logger.info("📄 Monthly-report scheduler started")
    while True:
        try:
            await check_monthly_reports(bot)
        except Exception as e:
            logger.error(f"monthly report loop error: {e}")
        await asyncio.sleep(CHECK_INTERVAL_S)
