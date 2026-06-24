"""Streak-save reminder.

Раз на хвилину перевіряє кожного юзера: якщо у нього локальний час 22:00,
streak >= 3 і за сьогодні (UTC) ще нуль reviews — шлемо нагадування у бот.
Антиспам: last_streak_save_date — одне push на день локального часу.
"""
import asyncio
import logging
from datetime import datetime, timezone
from html import escape

from aiogram import Bot
from sqlalchemy import select, update
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from core.bot_i18n import t as bt
from core.db import SessionLocal
from core.models import User
from core.streaks import calculate_streak, reviewed_today

logger = logging.getLogger(__name__)

# Локальна година коли пушимо. Перед північчю, коли streak ще можна врятувати.
SEND_HOUR_LOCAL = 22


def _user_local_hour(user: User) -> int | None:
    """Поточна година у таймзоні юзера, або None якщо TZ некоректна."""
    try:
        tz = ZoneInfo(user.timezone or "Europe/Kiev")
    except ZoneInfoNotFoundError:
        tz = ZoneInfo("Europe/Kiev")
    return datetime.now(tz).hour


def _user_local_date(user: User):
    try:
        tz = ZoneInfo(user.timezone or "Europe/Kiev")
    except ZoneInfoNotFoundError:
        tz = ZoneInfo("Europe/Kiev")
    return datetime.now(tz).date()


async def check_and_send_streak_saves(bot: Bot) -> None:
    try:
        async with SessionLocal() as session:
            users = list((await session.execute(
                select(User).where(User.reminders_enabled == True)
            )).scalars().all())

            sent = 0
            for user in users:
                try:
                    if _user_local_hour(user) != SEND_HOUR_LOCAL:
                        continue
                    today_local = _user_local_date(user)
                    if user.last_streak_save_date == today_local:
                        continue  # вже відправляли сьогодні

                    streak = await calculate_streak(session, user.id)
                    if streak < 3:
                        continue
                    done = await reviewed_today(session, user.id)
                    if done > 0:
                        continue

                    lang = user.native_lang or "uk"
                    text = (
                        f"{bt('streak_save.title', lang)}\n\n"
                        f"{bt('streak_save.body', lang).format(streak=streak)}"
                    )
                    await bot.send_message(chat_id=user.telegram_id, text=text)
                    await session.execute(
                        update(User).where(User.id == user.id).values(
                            last_streak_save_date=today_local
                        )
                    )
                    await session.commit()
                    sent += 1
                    await asyncio.sleep(0.05)
                except Exception as e:
                    logger.warning(
                        f"streak_save send failed for user {user.telegram_id}: {e}"
                    )
                    from core.user_service import disable_reminders_if_blocked
                    await disable_reminders_if_blocked(user.telegram_id, e)

            if sent:
                logger.info(f"🔥 Sent {sent} streak-save pushes")

    except Exception as e:
        logger.error(f"streak_save job error: {e}", exc_info=True)


async def streak_save_loop(bot: Bot) -> None:
    logger.info("🔥 Streak-save scheduler started")
    while True:
        try:
            await check_and_send_streak_saves(bot)
        except Exception as e:
            logger.error(f"streak_save loop error: {e}")
        await asyncio.sleep(60)
