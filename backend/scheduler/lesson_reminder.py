"""Нагадування про урок (M9): обом сторонам за 24 год і за 1 год до початку,
з бота відповідного тенанта, у локальному часі кожного. Раз на хвилину."""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

from aiogram import Bot
from sqlalchemy import select, update as sa_update
from zoneinfo import ZoneInfo

from core.db import SessionLocal
from core.models import Lesson, User
from core.bot_registry import get_bot

logger = logging.getLogger(__name__)


def _fmt(dt_utc: datetime, tz_name: str) -> str:
    dt = dt_utc.astimezone(ZoneInfo(tz_name if tz_name else "Europe/Kiev"))
    wd = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Нд"][dt.weekday()]
    return f"{wd} {dt.strftime('%d.%m %H:%M')}"


async def _send(bot: Bot | None, fallback: Bot, chat_id: int, text: str) -> None:
    b = bot or fallback
    try:
        await b.send_message(chat_id=chat_id, text=text)
    except Exception as e:
        logger.warning(f"lesson reminder send failed to {chat_id}: {e}")


async def _process(bot: Bot, field: str, within: timedelta, label: str) -> int:
    """Шле нагадування для уроків, що входять у вікно `within`, з невиставленим
    прапором `field`. Ставить прапор. Повертає скільки уроків опрацьовано."""
    now = datetime.now(timezone.utc)
    horizon = now + within
    async with SessionLocal() as s:
        lessons = (await s.execute(
            select(Lesson).where(
                Lesson.status == "booked",
                getattr(Lesson, field).is_(False),
                Lesson.starts_at_utc > now,
                Lesson.starts_at_utc <= horizon,
            )
        )).scalars().all()
        if not lessons:
            return 0
        # резолвимо користувачів
        uids = set()
        for ls in lessons:
            uids.add(ls.student_user_id)
            if ls.teacher_user_id:
                uids.add(ls.teacher_user_id)
        users = {u.id: u for u in (await s.execute(
            select(User).where(User.id.in_(uids))
        )).scalars().all()}

    sent = 0
    for ls in lessons:
        tenant_bot = get_bot(ls.tenant_id)
        student = users.get(ls.student_user_id)
        teacher = users.get(ls.teacher_user_id) if ls.teacher_user_id else None
        if student:
            when = _fmt(ls.starts_at_utc, student.timezone)
            await _send(tenant_bot, bot, student.telegram_id,
                        f"⏰ Нагадування: урок {label} — <b>{when}</b>")
        if teacher:
            when = _fmt(ls.starts_at_utc, teacher.timezone)
            sname = student.first_name if student else "учень"
            await _send(tenant_bot, bot, teacher.telegram_id,
                        f"⏰ Нагадування: урок {label} з {sname} — <b>{when}</b>")
        sent += 1
        await asyncio.sleep(0.03)

    # ставимо прапори однією апдейт-операцією
    async with SessionLocal() as s:
        await s.execute(
            sa_update(Lesson).where(Lesson.id.in_([ls.id for ls in lessons])).values(
                **{field: True}
            )
        )
        await s.commit()
    return sent


async def check_lesson_reminders(bot: Bot) -> None:
    try:
        n24 = await _process(bot, "reminder_24_sent", timedelta(hours=24), "завтра")
        n1 = await _process(bot, "reminder_1_sent", timedelta(hours=1), "за годину")
        if n24 or n1:
            logger.info(f"📅 Lesson reminders: {n24}×24h, {n1}×1h")
    except Exception as e:
        logger.error(f"lesson reminder job error: {e}", exc_info=True)


async def lesson_reminder_loop(bot: Bot) -> None:
    logger.info("📅 Lesson-reminder scheduler started")
    while True:
        try:
            await check_lesson_reminders(bot)
        except Exception as e:
            logger.error(f"lesson reminder loop error: {e}")
        await asyncio.sleep(60)
