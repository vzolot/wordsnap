"""Передурочний дайджест (M10). За `tenants.digest_lead_hours` (дефолт 3) до
уроку шле:
  • Викладачу — імʼя учня, час (у tz викладача), активність, прогрес по колодах,
    топ-5 слабких слів.
  • Учню — нагадування (у tz учня) + кнопка «Повторити слабкі слова», що відкриває
    Mini App одразу в режимі тренування по слабких словах.

Дані = ті самі агрегати, що в M6 (`teacher_stats.student_detail`) — не дублюємо
логіку. Прапор `lessons.digest_sent` захищає від повторів. Раз на хвилину.
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from sqlalchemy import select, update as sa_update
from zoneinfo import ZoneInfo

from core.db import SessionLocal
from core.models import Lesson, Tenant, User
from core.bot_registry import get_bot
from core.constants import MINI_APP_URL
from core import teacher_stats as tstats

logger = logging.getLogger(__name__)

MAX_LEAD_SCAN_HOURS = 12  # ширина сканування; фактичний lead — per-tenant


def _fmt(dt_utc: datetime, tz_name: str) -> str:
    dt = dt_utc.astimezone(ZoneInfo(tz_name if tz_name else "Europe/Kiev"))
    wd = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Нд"][dt.weekday()]
    return f"{wd} {dt.strftime('%d.%m %H:%M')}"


def _teacher_text(student_name: str, when: str, det: dict, homework: list | None = None) -> str:
    lines = [
        f"📋 <b>Скоро урок</b> — {when}",
        f"Учень: <b>{student_name}</b>",
        "",
        f"🔥 Стрік: {det['streak']} дн · повторень за 7 дн: {det['reviews_7d']}",
    ]
    if homework:
        lines.append("")
        lines.append("<b>Домашнє завдання:</b>")
        _label = {"done": "✅ виконано", "overdue": "⛔ прострочено",
                  "in_progress": "… у процесі", "assigned": "▫️ не почато"}
        for h in homework[:5]:
            lines.append(f"• {h['title']}: {_label.get(h['status'], h['status'])} ({h['passed']}/{h['total']})")
    if det.get("decks"):
        lines.append("")
        lines.append("<b>Прогрес по колодах:</b>")
        for d in det["decks"][:4]:
            total = d["learned"] + d["in_progress"] + d["not_started"]
            lines.append(f"• {d['title']}: {d['learned']}/{total} вивчено")
    weak = det.get("weak_words") or []
    if weak:
        lines.append("")
        lines.append("<b>Топ слабких слів:</b>")
        for w in weak[:5]:
            lines.append(f"• {w['word']} — {w['translation']} ({round(w['error_rate']*100)}% помилок)")
    return "\n".join(lines)


async def _send_teacher(bot: Bot, chat_id: int, text: str) -> None:
    try:
        await bot.send_message(chat_id=chat_id, text=text)
    except Exception as e:
        logger.warning(f"digest teacher send failed to {chat_id}: {e}")


async def _send_student(bot: Bot, chat_id: int, when: str, has_weak: bool) -> None:
    text = (
        f"📅 <b>Скоро урок</b> — {when}\n\n"
        "Гарний момент розім'ятись перед заняттям."
    )
    kb = None
    if has_weak:
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(
                text="🎯 Повторити слабкі слова",
                web_app=WebAppInfo(url=f"{MINI_APP_URL}?src=weak"),
            )
        ]])
    try:
        await bot.send_message(chat_id=chat_id, text=text, reply_markup=kb)
    except Exception as e:
        logger.warning(f"digest student send failed to {chat_id}: {e}")


async def check_digests(bot: Bot) -> None:
    now = datetime.now(timezone.utc)
    horizon = now + timedelta(hours=MAX_LEAD_SCAN_HOURS)
    try:
        async with SessionLocal() as s:
            lessons = (await s.execute(
                select(Lesson).where(
                    Lesson.status == "booked",
                    Lesson.digest_sent.is_(False),
                    Lesson.starts_at_utc > now,
                    Lesson.starts_at_utc <= horizon,
                )
            )).scalars().all()
            if not lessons:
                return
            tenants = {t.id: t for t in (await s.execute(
                select(Tenant).where(Tenant.id.in_({l.tenant_id for l in lessons}))
            )).scalars().all()}
            uids = set()
            for l in lessons:
                uids.add(l.student_user_id)
                if l.teacher_user_id:
                    uids.add(l.teacher_user_id)
            users = {u.id: u for u in (await s.execute(
                select(User).where(User.id.in_(uids))
            )).scalars().all()}

        due_ids = []
        for l in lessons:
            tenant = tenants.get(l.tenant_id)
            lead = (tenant.digest_lead_hours if tenant else 3)
            if l.starts_at_utc - now > timedelta(hours=lead):
                continue  # ще рано
            student = users.get(l.student_user_id)
            teacher = users.get(l.teacher_user_id) if l.teacher_user_id else None
            if not student:
                continue
            tenant_bot = get_bot(l.tenant_id) or bot
            det = await tstats.student_detail(l.tenant_id, student.id)
            has_weak = bool(det and det.get("weak_words"))

            if teacher:
                when_t = _fmt(l.starts_at_utc, teacher.timezone)
                sname = student.first_name or "учень"
                from core.homework_service import student_homework_summary
                hw = await student_homework_summary(l.tenant_id, student.id)
                await _send_teacher(tenant_bot, teacher.telegram_id,
                                    _teacher_text(sname, when_t, det or {}, hw))
            when_s = _fmt(l.starts_at_utc, student.timezone)
            await _send_student(tenant_bot, student.telegram_id, when_s, has_weak)
            due_ids.append(l.id)
            await asyncio.sleep(0.03)

        if due_ids:
            async with SessionLocal() as s:
                await s.execute(
                    sa_update(Lesson).where(Lesson.id.in_(due_ids)).values(digest_sent=True)
                )
                await s.commit()
            logger.info(f"📋 Sent {len(due_ids)} pre-lesson digests")
    except Exception as e:
        logger.error(f"digest job error: {e}", exc_info=True)


async def lesson_digest_loop(bot: Bot) -> None:
    logger.info("📋 Pre-lesson digest scheduler started")
    while True:
        try:
            await check_digests(bot)
        except Exception as e:
            logger.error(f"digest loop error: {e}")
        await asyncio.sleep(60)
