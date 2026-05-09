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


def _is_admin(message: Message) -> bool:
    aid = admin_telegram_id()
    return aid is not None and message.from_user.id == aid


@router.message(Command("stats"))
async def cmd_stats(message: Message) -> None:
    """Live-зріз поточного дня (з 00:00 Kyiv до зараз)."""
    if not _is_admin(message):
        return  # тиха відмова
    try:
        text = await build_daily_report(for_yesterday=False)
        await message.answer(text, parse_mode="HTML")
    except Exception as e:
        logger.error(f"/stats failed: {e}", exc_info=True)
        await message.answer("⚠️ Звіт не вдалось зібрати — глянь логи.")


@router.message(Command("stats_yesterday"))
async def cmd_stats_yesterday(message: Message) -> None:
    """Повна вчорашня доба — той самий зріз що приходить о 09:00."""
    if not _is_admin(message):
        return
    try:
        text = await build_daily_report(for_yesterday=True)
        await message.answer(text, parse_mode="HTML")
    except Exception as e:
        logger.error(f"/stats_yesterday failed: {e}", exc_info=True)
        await message.answer("⚠️ Звіт не вдалось зібрати — глянь логи.")
