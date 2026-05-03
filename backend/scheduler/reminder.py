"""
Планувальник автоматичних нагадувань.
Кожну хвилину перевіряє кому слати нагадування.
Не пушить next_review (щоб слово залишалось видимим у міні-апі),
а трекає last_reminder_at для антиспаму.
"""
import logging
import asyncio
from html import escape

from sqlalchemy import select
from aiogram import Bot

from core.bot_i18n import t as bt
from core.constants import REMINDER_COOLDOWN_HOURS
from core.db import SessionLocal
from core.models import User
from core.word_service import get_word_for_reminder, mark_word_reminded
from bot.keyboards.review_keyboards import show_translation_keyboard

logger = logging.getLogger(__name__)


async def check_and_send_reminders(bot: Bot):
    try:
        async with SessionLocal() as session:
            result = await session.execute(
                select(User).where(User.reminders_enabled == True)
            )
            users = list(result.scalars().all())

        sent = 0
        for user in users:
            try:
                word = await get_word_for_reminder(user.id, REMINDER_COOLDOWN_HOURS)
                if not word:
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
                sent += 1

                await mark_word_reminded(word.id)
                await asyncio.sleep(0.05)

            except Exception as e:
                logger.warning(f"Failed to send reminder to user {user.telegram_id}: {e}")

        if sent > 0:
            logger.info(f"📬 Sent {sent} reminders")

    except Exception as e:
        logger.error(f"Error in reminder job: {e}", exc_info=True)


async def reminder_loop(bot: Bot):
    logger.info("⏰ Reminder scheduler started")
    while True:
        try:
            await check_and_send_reminders(bot)
        except Exception as e:
            logger.error(f"Reminder loop error: {e}")
        await asyncio.sleep(60)
