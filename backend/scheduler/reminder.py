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
import random
from datetime import datetime, timezone, timedelta
from html import escape

from aiogram import Bot
from sqlalchemy import func, select, update as sa_update
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from core import analytics
from core.bot_i18n import t as bt
from core.db import SessionLocal
from core.models import User, Word
from core.word_service import mark_word_reminded
from bot.keyboards.review_keyboards import show_translation_keyboard

logger = logging.getLogger(__name__)


async def _count_due_words(user_id: int) -> int:
    """Скільки слів готові до повторення прямо зараз (next_review ≤ now)."""
    async with SessionLocal() as session:
        now = datetime.now(timezone.utc)
        n = (await session.execute(
            select(func.count(Word.id)).where(
                Word.user_id == user_id,
                Word.status == "learning",
                Word.next_review <= now,
            )
        )).scalar()
        return int(n or 0)


def _user_tz(user: User) -> ZoneInfo:
    try:
        return ZoneInfo(user.timezone or "Europe/Kiev")
    except ZoneInfoNotFoundError:
        return ZoneInfo("Europe/Kiev")


ACTIVE_WINDOW_HOURS = 12  # Тривалість активного push-вікна після reminder_time
PUSH_COOLDOWN_HOURS = 5   # Мінімальний інтервал між пушами одному юзеру
CATCHUP_THRESHOLD = 3     # Скільки due-слів треба для повторного (не першого) пушу

# Шанс підмінити денне push-слово на випадкове mastered (SRS-перевірка
# «не забув на довгій дистанції»). Без цього mastered-слова лежать мертвим
# вантажем; з ~8% юзер раз на ~2 тижні дістає старе слово на check-up.
# Якщо «forgot» — SM-2 повертає його у learning з reset interval, природньо.
MASTERED_RESAMPLE_PROBABILITY = 0.08


async def _pick_mastered_for_resample(user_id: int) -> Word | None:
    """Випадкове mastered-слово, не нагадане за останні 20 годин."""
    async with SessionLocal() as session:
        cooldown = datetime.now(timezone.utc) - timedelta(hours=20)
        result = await session.execute(
            select(Word)
            .where(
                Word.user_id == user_id,
                Word.status == "mastered",
                (Word.last_reminder_at.is_(None)) | (Word.last_reminder_at < cooldown),
            )
            .order_by(func.random())
            .limit(1)
        )
        return result.scalar_one_or_none()


async def _pick_daily_word(user_id: int) -> tuple[Word | None, bool]:
    """Обирає слово для денного push'у.

    Returns (word, is_mastered_resample). З ймовірністю
    MASTERED_RESAMPLE_PROBABILITY дістаємо random mastered-слово замість
    most-overdue learning. Якщо mastered-слов немає або всі recent — fallback
    на стандартну learning-логіку. `is_mastered_resample` шле analytics.
    """
    if random.random() < MASTERED_RESAMPLE_PROBABILITY:
        mastered = await _pick_mastered_for_resample(user_id)
        if mastered:
            return mastered, True

    async with SessionLocal() as session:
        now = datetime.now(timezone.utc)
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
        return result.scalar_one_or_none(), False


async def send_daily_push_for_user(bot: Bot, user: User, *, force: bool = False) -> str:
    """Шле reminder-push одному юзеру.

    Multi-push policy (force=False):
      • Активне вікно: reminder_time.hour ... +12h локального часу
      • Cooldown 5h між пушами одному юзеру
      • Перший пуш дня — за наявності хоч одного due-слова
      • Наступні (catch-up) пуші — за наявності ≥3 due-слів
      • Природньо обмежено ~3 пушами/день (12h / 5h ≈ 3 слоти)

    force=True — ігноруємо вікно, cooldown і пороги. Для /test_remind.

    Повертає статус: "sent" | "outside_window" | "cooldown" |
    "below_threshold" | "no_due_word" | "send_failed".
    """
    tz = _user_tz(user)
    local_now = datetime.now(tz)
    now_utc = datetime.now(timezone.utc)
    today_local = local_now.date()

    is_first_push_today = (
        user.last_push_at is None or
        user.last_push_at.astimezone(tz).date() != today_local
    )

    if not force:
        primary_hour = (user.reminder_time.hour if user.reminder_time else 9)
        active_end = primary_hour + ACTIVE_WINDOW_HOURS
        # Активне вікно реалізуємо просто на годинах, без перетину опівночі —
        # бо primary_hour 9..12 + 12 = 21..24, не перевалить за 24.
        if local_now.hour < primary_hour or local_now.hour >= active_end:
            return "outside_window"

        # Cooldown: минуло ≥5h з останнього пушу (для catch-up пушів)
        if user.last_push_at and not is_first_push_today:
            since = now_utc - user.last_push_at
            if since < timedelta(hours=PUSH_COOLDOWN_HOURS):
                return "cooldown"

    word, is_mastered_resample = await _pick_daily_word(user.id)
    if not word:
        return "no_due_word"

    lang = user.native_lang or "uk"
    due_total = await _count_due_words(user.id)

    if not force:
        # Catch-up пуш потребує більшого порогу — щоб не дзвонити на 1 слово
        threshold = 1 if is_first_push_today else CATCHUP_THRESHOLD
        if due_total < threshold:
            return "below_threshold"

    more_line = ""
    if due_total > 1:
        more_line = "\n\n" + bt("remind.more_waiting", lang, n=due_total - 1)

    text = (
        f"{bt('remind.title', lang)}\n\n"
        f"📚 <b>{escape(word.word)}</b>\n\n"
        f"{bt('remind.hint', lang)}"
        f"{more_line}"
    )
    keyboard = show_translation_keyboard(
        word.id, source="rem", lang=lang, due_total=due_total,
    )

    try:
        await bot.send_message(
            chat_id=user.telegram_id,
            text=text,
            reply_markup=keyboard,
        )
    except Exception as e:
        logger.warning(f"daily_push bot.send_message failed for {user.telegram_id}: {e}")
        from core.user_service import disable_reminders_if_blocked
        await disable_reminders_if_blocked(user.telegram_id, e, tenant_id=user.tenant_id)
        return "send_failed"

    analytics.capture(user.telegram_id, "daily_push_sent", {
        "target_lang": user.target_lang,
        "native_lang": user.native_lang,
        "hour_local": local_now.hour,
        "timezone": user.timezone or "Europe/Kiev",
        "word_id": word.id,
        "word_status": word.status,
        "due_total": due_total,
        "forced": force,
        "is_first_push_today": is_first_push_today,
        "is_mastered_resample": is_mastered_resample,
    })
    await mark_word_reminded(word.id)
    if not force:
        async with SessionLocal() as session:
            await session.execute(
                sa_update(User).where(User.id == user.id).values(
                    last_push_at=now_utc,
                    last_daily_push_date=today_local,  # legacy stamp — лишаємо
                )
            )
            await session.commit()
    return "sent"


async def check_and_send_daily_pushes(bot: Bot) -> None:
    try:
        async with SessionLocal() as session:
            users = list((await session.execute(
                select(User).where(User.reminders_enabled == True)  # noqa: E712
            )).scalars().all())

        from core.bot_registry import get_bot
        sent = 0
        for user in users:
            try:
                # Нагадування має йти з бота ВЛАСНОГО тенанта юзера (бренд
                # викладача), не з головного. Фолбек на переданий bot (тенант 1).
                user_bot = get_bot(user.tenant_id) or bot
                status = await send_daily_push_for_user(user_bot, user)
                if status == "sent":
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
