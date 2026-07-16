"""Щоденний адмін-звіт у Telegram о 09:00 за Europe/Kyiv.

Раз на хвилину перевіряємо чи зараз 09:xx у Києві і чи ми ще не слали
звіт сьогодні. Якщо так — будуємо звіт через core/admin_report.py і шлемо
у чат адміна (ADMIN_TELEGRAM_ID).

Дата останньої розсилки персиститься у БД (`app_state`), тому redeploy
під час 09:xx не задвоює звіт.
"""
import asyncio
import logging
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from aiogram import Bot

from core.admin_report import build_report
from core.app_state import get_state, set_state
from core.constants import admin_telegram_id

logger = logging.getLogger(__name__)

REPORT_HOUR_LOCAL = 9  # 09:xx Europe/Kyiv
_STATE_KEY = "admin_report_last_sent"  # значення = ISO-дата (YYYY-MM-DD)

# In-memory кеш — щоб не ходити в БД щохвилини. Джерело істини — БД; кеш
# підвантажується ліниво при першій перевірці після старту.
_last_sent_date: date | None = None
_loaded_from_db = False


def _kyiv_now() -> datetime:
    try:
        return datetime.now(ZoneInfo("Europe/Kyiv"))
    except ZoneInfoNotFoundError:
        return datetime.now(timezone.utc)


async def _ensure_loaded() -> None:
    global _last_sent_date, _loaded_from_db
    if _loaded_from_db:
        return
    raw = await get_state(_STATE_KEY)
    if raw:
        try:
            _last_sent_date = date.fromisoformat(raw)
        except ValueError:
            _last_sent_date = None
    _loaded_from_db = True


async def _maybe_send(bot: Bot) -> None:
    global _last_sent_date

    admin_id = admin_telegram_id()
    if admin_id is None:
        return  # не сконфігуровано — мовчки пропускаємо

    now = _kyiv_now()
    if now.hour != REPORT_HOUR_LOCAL:
        return

    await _ensure_loaded()
    today = now.date()
    if _last_sent_date == today:
        return

    try:
        # Звіт за повну вчорашню добу — щоб ранкова розсилка показувала
        # завершений 24-годинний зріз, а не 9 годин ранку поточного дня.
        text = await build_report("yesterday_full")
        await bot.send_message(chat_id=admin_id, text=text, parse_mode="HTML")
        _last_sent_date = today
        await set_state(_STATE_KEY, today.isoformat())
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
