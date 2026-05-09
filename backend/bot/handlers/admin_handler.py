"""Admin-only команди для @WordSnapBot.

/stats_admin       — live-зріз поточного дня (з 00:00 Kyiv до зараз)
/stats_admin_day   — повна вчорашня доба (той самий зріз що в 09:00 push)
/stats_admin_month — за останні 30 днів (включно з сьогодні-live)

Доступні лише користувачу із telegram_id == ADMIN_TELEGRAM_ID. Для всіх
інших — тиха відмова, щоб не палити існування команди.
"""
import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from core.admin_report import PeriodKind, build_report
from core.constants import admin_telegram_id

logger = logging.getLogger(__name__)
router = Router()


def _is_admin(message: Message) -> bool:
    aid = admin_telegram_id()
    return aid is not None and message.from_user.id == aid


async def _send_report(message: Message, period: PeriodKind, command_name: str) -> None:
    if not _is_admin(message):
        return  # тиха відмова
    try:
        text = await build_report(period)
        await message.answer(text, parse_mode="HTML")
    except Exception as e:
        logger.error(f"/{command_name} failed: {e}", exc_info=True)
        await message.answer("⚠️ Звіт не вдалось зібрати — глянь логи.")


@router.message(Command("stats_admin"))
async def cmd_stats_admin(message: Message) -> None:
    await _send_report(message, "today_live", "stats_admin")


@router.message(Command("stats_admin_day"))
async def cmd_stats_admin_day(message: Message) -> None:
    await _send_report(message, "yesterday_full", "stats_admin_day")


@router.message(Command("stats_admin_month"))
async def cmd_stats_admin_month(message: Message) -> None:
    await _send_report(message, "month_30d", "stats_admin_month")


@router.message(Command("test_remind"))
async def cmd_test_remind(message: Message) -> None:
    """Force-надсилає денний пуш зараз, ігноруючи час/дату/cooldown.
    Корисно для дебагу: чи працює сама send-логіка, чи проблема у scheduler-таймері."""
    if not _is_admin(message):
        return

    from sqlalchemy import select
    from core.db import SessionLocal
    from core.models import User
    from scheduler.reminder import send_daily_push_for_user

    async with SessionLocal() as s:
        user = (await s.execute(
            select(User).where(User.telegram_id == message.from_user.id)
        )).scalar_one_or_none()

    if not user:
        await message.answer("⚠️ Не знайшов твій user-row у БД.")
        return

    status = await send_daily_push_for_user(message.bot, user, force=True)
    if status == "sent":
        # Окреме повідомлення не шлемо — пуш сам прийшов як окрема нотифікація.
        return

    explanations = {
        "no_due_word": (
            "🤷 Нема learning-слів зі статусом due (next_review ≤ now).\n"
            "→ Перевір у мініапі вкладку \"Повторення\" — якщо там empty, "
            "то й бот не має що нагадати."
        ),
        "send_failed": "⚠️ bot.send_message впав — глянь логи Railway.",
    }
    await message.answer(explanations.get(status, f"⚠️ status={status}"))
