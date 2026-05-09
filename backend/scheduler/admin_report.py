"""Щоденний адмін-звіт у Telegram о 09:00 за Europe/Kiev.

Раз на хвилину перевіряємо чи зараз 09:xx у Києві і чи ми ще не слали
звіт сьогодні. Якщо так — будуємо звіт через core/admin_report.py і шлемо
у чат адміна (ADMIN_TELEGRAM_ID).
"""
import asyncio
import logging
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from aiogram import Bot

from core.admin_report import build_daily_report
from core.constants import admin_telegram_id

logger = logging.getLogger(__name__)

REPORT_HOUR_LOCAL = 9  # 09:xx Europe/Kiev

# Тримаємо у in-memory state — перезапуск процесу скидає, тоді є шанс
# отримати один зайвий звіт того самого дня. Прийнятна ціна простоти.
_last_sent_date: date | None = None


def _kyiv_now() -> datetime:
    try:
        return datetime.now(ZoneInfo("Europe/Kiev"))
    except ZoneInfoNotFoundError:
        return datetime.now(timezone.utc)


async def _maybe_send(bot: Bot) -> None:
    global _last_sent_date

    admin_id = admin_telegram_id()
    if admin_id is None:
        return  # не сконфігуровано — мовчки пропускаємо

    now = _kyiv_now()
    if now.hour != REPORT_HOUR_LOCAL:
        return
    today = now.date()
    if _last_sent_date == today:
        return

    try:
        text = await build_daily_report()
        await bot.send_message(chat_id=admin_id, text=text, parse_mode="HTML")
        _last_sent_date = today
        logger.info(f"📊 Admin report sent to {admin_id}")
    except Exception as e:
        logger.error(f"Admin report send failed: {e}", exc_info=True)


async def admin_report_loop(bot: Bot) -> None:
    logger.info("📊 Admin-report scheduler started")
    while True:
        try:
            await _maybe_send(bot)
        except Exception as e:
            logger.error(f"admin_report loop error: {e}")
        await asyncio.sleep(60)
