"""
Word-of-the-Day push (раз на локальний день у `user.reminder_time`).

Раз на хвилину перевіряємо кожного юзера з reminders_enabled=True. Шлемо
ОДНЕ слово якщо:
  - локальна година зараз == user.reminder_time.hour (вікно 1 година)
  - last_daily_push_date != сьогодні (локальне) — не задвоює
  - є хоча б одне слово зі статусом "learning" та next_review <= now

Анти-спам:
  - per-user: last_daily_push_date (одне на локальний день)
  - per-word: last_reminder_at (на випадок ручних /remind у боті — щоб не
    повторити те саме слово протягом доби)
"""
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from html import escape

from aiogram import Bot
from sqlalchemy import select, update as sa_update
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from core import analytics
from core.bot_i18n import t as bt
from core.db import SessionLocal
from core.models import User, Word
from core.word_service import mark_word_reminded
from bot.keyboards.review_keyboards import show_translation_keyboard

logger = logging.getLogger(__name__)


def _user_tz(user: User) -> ZoneInfo:
    try:
        return ZoneInfo(user.timezone or "Europe/Kiev")
    except ZoneInfoNotFoundError:
        return ZoneInfo("Europe/Kiev")


async def _pick_daily_word(user_id: int) -> Word | None:
    """Найкраще слово для денного пушу: найбільш-overdue серед learning."""
    async with SessionLocal() as session:
        now = datetime.now(timezone.utc)
        # Fallback: якщо overdue нема — будь-яке learning, не нагадане сьогодні
        cooldown = now - timedelta(hours=20)
        result = await session.execute(
            select(Word)
            .where(
                Word.user_id == user_id,
                Word.status == "learning",
                Word.next_review <= now,
                (Word.last_reminder_at.is_(None)) | (Word.last_reminder_at < cooldown),
            )
            .order_by(Word.next_review.asc())
            .limit(1)
        )
        return result.scalar_one_or_none()


async def check_and_send_daily_pushes(bot: Bot) -> None:
    try:
        async with SessionLocal() as session:
            users = list((await session.execute(
                select(User).where(User.reminders_enabled == True)  # noqa: E712
            )).scalars().all())

        sent = 0
        for user in users:
            try:
                tz = _user_tz(user)
                local_now = datetime.now(tz)
                target_hour = (user.reminder_time.hour if user.reminder_time else 9)
                if local_now.hour != target_hour:
                    continue

                today_local = local_now.date()
                if user.last_daily_push_date == today_local:
                    continue

                word = await _pick_daily_word(user.id)
                if not word:
                    # Все одно ставимо stamp — щоб не перевіряти повторно цю годину
                    async with SessionLocal() as session:
                        await session.execute(
                            sa_update(User).where(User.id == user.id).values(
                                last_daily_push_date=today_local
                            )
                        )
                        await session.commit()
                    analytics.capture(user.telegram_id, "daily_push_skipped", {
                        "reason": "no_due_word",
                        "hour_local": local_now.hour,
                        "timezone": user.timezone or "Europe/Kiev",
                    })
                    continue

                lang = user.native_lang or "uk"
                text = (
                    f"{bt('remind.title', lang)}\n\n"
                    f"📚 <b>{escape(word.word)}</b>\n\n"
                    f"{bt('remind.hint', lang)}"
                )
                keyboard = show_translation_keyboard(word.id, source="rem", lang=lang)

                await bot.send_message(
                    chat_id=user.telegram_id,
                    text=text,
                    reply_markup=keyboard,
                )
                analytics.capture(user.telegram_id, "daily_push_sent", {
                    "target_lang": user.target_lang,
                    "native_lang": user.native_lang,
                    "hour_local": local_now.hour,
                    "timezone": user.timezone or "Europe/Kiev",
                    "word_id": word.id,
                })
                await mark_word_reminded(word.id)
                async with SessionLocal() as session:
                    await session.execute(
                        sa_update(User).where(User.id == user.id).values(
                            last_daily_push_date=today_local
                        )
                    )
                    await session.commit()
                sent += 1
                await asyncio.sleep(0.05)
            except Exception as e:
                logger.warning(
                    f"daily_push send failed for user {user.telegram_id}: {e}"
                )

        if sent:
            logger.info(f"📬 Sent {sent} daily word pushes")

    except Exception as e:
        logger.error(f"daily_push job error: {e}", exc_info=True)


async def reminder_loop(bot: Bot) -> None:
    logger.info("⏰ Daily-push scheduler started")
    while True:
        try:
            await check_and_send_daily_pushes(bot)
        except Exception as e:
            logger.error(f"daily_push loop error: {e}")
        await asyncio.sleep(60)
