"""
Планувальник автоматичних нагадувань.
Кожну хвилину перевіряє кому слати нагадування.
Після відправки відкладає next_review слова на 6 годин,
щоб не спамити одне і те ж слово щохвилини.
"""
import logging
import asyncio
from datetime import datetime, timezone, timedelta
from sqlalchemy import select
from aiogram import Bot

from core.db import SessionLocal
from core.models import User, Word
from core.word_service import get_words_due_review
from bot.keyboards.review_keyboards import show_translation_keyboard
from html import escape

logger = logging.getLogger(__name__)

# На скільки годин відкласти next_review після відправки нагадування,
# якщо користувач не натиснув жодну кнопку
REMINDER_SNOOZE_HOURS = 6


async def check_and_send_reminders(bot: Bot):
    """Перевіряє кому слати нагадування і відправляє їх."""
    try:
        async with SessionLocal() as session:
            # Беремо всіх юзерів з увімкненими нагадуваннями
            result = await session.execute(
                select(User).where(User.reminders_enabled == True)
            )
            users = list(result.scalars().all())

        sent = 0
        for user in users:
            try:
                # Беремо ОДНЕ найперше слово для повторення
                words = await get_words_due_review(user.id, limit=1)

                if not words:
                    continue

                word = words[0]

                # Відправляємо нагадування
                text = (
                    f"🔔 <b>Час повторити слово!</b>\n\n"
                    f"📚 <b>{escape(word.word)}</b>\n\n"
                    f"<i>Згадав переклад? Натисни щоб перевірити 👇</i>"
                )
                keyboard = show_translation_keyboard(word.id)

                await bot.send_message(
                    chat_id=user.telegram_id,
                    text=text,
                    reply_markup=keyboard,
                )
                sent += 1

                # КЛЮЧОВА ЗМІНА: відкладаємо next_review цього слова на N годин,
                # щоб через хвилину не повторити те саме нагадування.
                # Якщо користувач натисне кнопку — process_review перепише next_review правильно.
                await _snooze_word(word.id, hours=REMINDER_SNOOZE_HOURS)

                # Невелика пауза щоб не задовбати Telegram API
                await asyncio.sleep(0.05)

            except Exception as e:
                logger.warning(f"Failed to send reminder to user {user.telegram_id}: {e}")

        if sent > 0:
            logger.info(f"📬 Sent {sent} reminders")

    except Exception as e:
        logger.error(f"Error in reminder job: {e}", exc_info=True)


async def _snooze_word(word_id: int, hours: int) -> None:
    """Відкласти наступне нагадування цього слова на N годин."""
    try:
        async with SessionLocal() as session:
            result = await session.execute(
                select(Word).where(Word.id == word_id)
            )
            word = result.scalar_one_or_none()
            if word:
                word.next_review = datetime.now(timezone.utc) + timedelta(hours=hours)
                await session.commit()
    except Exception as e:
        logger.warning(f"Failed to snooze word {word_id}: {e}")


async def reminder_loop(bot: Bot):
    """Головний цикл планувальника. Запускається кожну хвилину."""
    logger.info("⏰ Reminder scheduler started")

    while True:
        try:
            await check_and_send_reminders(bot)
        except Exception as e:
            logger.error(f"Reminder loop error: {e}")

        # Чекаємо 60 секунд
        await asyncio.sleep(60)