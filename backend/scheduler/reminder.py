"""
Планувальник автоматичних нагадувань.
Кожну хвилину перевіряє кому слати нагадування.
"""
import logging
import asyncio
from datetime import datetime, timezone
from sqlalchemy import select
from aiogram import Bot

from core.db import SessionLocal
from core.models import User, Word
from core.word_service import get_words_due_review
from bot.handlers.review_handler import send_review_word
from bot.keyboards.review_keyboards import show_translation_keyboard
from html import escape

logger = logging.getLogger(__name__)


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
                # Беремо слова для повторення
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
                
                # Невелика пауза щоб не задовбати Telegram API
                await asyncio.sleep(0.05)
                
            except Exception as e:
                logger.warning(f"Failed to send reminder to user {user.telegram_id}: {e}")
        
        if sent > 0:
            logger.info(f"📬 Sent {sent} reminders")
            
    except Exception as e:
        logger.error(f"Error in reminder job: {e}", exc_info=True)


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