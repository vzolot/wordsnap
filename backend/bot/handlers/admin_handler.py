"""Admin-only команди для @WordSnapBot.

/stats — миттєвий снапшот ключових метрик. Доступна лише користувачу
із telegram_id == ADMIN_TELEGRAM_ID (env var).
"""
import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from core.admin_report import build_daily_report
from core.constants import admin_telegram_id

logger = logging.getLogger(__name__)
router = Router()


@router.message(Command("stats"))
async def cmd_stats(message: Message) -> None:
    admin_id = admin_telegram_id()
    if admin_id is None or message.from_user.id != admin_id:
        # Тиха відмова — не палимо існування команди для не-адмінів
        return
    try:
        text = await build_daily_report()
        await message.answer(text, parse_mode="HTML")
    except Exception as e:
        logger.error(f"/stats failed: {e}", exc_info=True)
        await message.answer("⚠️ Звіт не вдалось зібрати — глянь логи.")
