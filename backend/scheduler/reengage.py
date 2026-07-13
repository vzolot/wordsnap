"""Re-engagement push для юзерів, які 7+ днів не робили жодного перегляду.

Звичайний daily-push (reminder.py) шле кожному з due-словами щодня — навіть
коли юзер мовчить кілька тижнів. Цей лооп окремий: ловить тих хто реально
вибув із циклу (нуль reviews за останні 7+ днів) і шле ОДИН теплий пуш з
останнім словом, яке вони провалили. Тон — нагадування, не маркетинг.

Анти-спам: один такий push на юзера що 30 днів максимум.
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from html import escape

from aiogram import Bot
from sqlalchemy import func, select, update as sa_update

from core import analytics
from core.bot_i18n import t as bt
from core.db import SessionLocal
from core.models import Review, User, Word

logger = logging.getLogger(__name__)

# Юзер вважається «вибулим» якщо MAX(reviews.reviewed_at) < now - INACTIVE_DAYS.
INACTIVE_DAYS = 7
# Мінімальний інтервал між двома re-engage пушами одному юзеру.
COOLDOWN_DAYS = 30
# Скільки юзерів максимум обробляємо за один прохід loop (захист від різких
# хвиль; у нормі їх десятки, не тисячі).
MAX_PER_TICK = 50


async def _pick_reengage_word(session, user_id: int) -> Word | None:
    """Найкраще слово для re-engage push: останнє з 'forgot' (це точка болю
    яку легко повернути), fallback — найсвіжіше слово юзера загалом."""
    # 1) Останнє слово з останнього 'forgot'-рев'ю
    forgot_review = (await session.execute(
        select(Review)
        .where(Review.user_id == user_id, Review.result == "forgot")
        .order_by(Review.reviewed_at.desc())
        .limit(1)
    )).scalar_one_or_none()
    if forgot_review is not None:
        word = (await session.execute(
            select(Word).where(Word.id == forgot_review.word_id)
        )).scalar_one_or_none()
        if word is not None:
            return word

    # 2) Fallback — найсвіжіше додане
    return (await session.execute(
        select(Word)
        .where(Word.user_id == user_id)
        .order_by(Word.created_at.desc())
        .limit(1)
    )).scalar_one_or_none()


async def _eligible_users(session) -> list[tuple[User, int]]:
    """Юзери, яких варто розштовхати. Повертає (user, days_since_last_review).

    Критерії:
      - reminders_enabled = True
      - total_reviews > 0 (юзер таки колись щось робив, не онбординг-стелс)
      - MAX(reviews.reviewed_at) < now - INACTIVE_DAYS
      - last_reengage_push_at NULL або < now - COOLDOWN_DAYS
    """
    now = datetime.now(timezone.utc)
    inactive_before = now - timedelta(days=INACTIVE_DAYS)
    cooldown_before = now - timedelta(days=COOLDOWN_DAYS)

    # Subquery: MAX(reviewed_at) per user
    last_review_sq = (
        select(
            Review.user_id.label("uid"),
            func.max(Review.reviewed_at).label("last_review"),
        )
        .group_by(Review.user_id)
        .subquery()
    )

    rows = (await session.execute(
        select(User, last_review_sq.c.last_review)
        .join(last_review_sq, last_review_sq.c.uid == User.id)
        .where(
            User.reminders_enabled == True,  # noqa: E712
            User.role == "student",  # викладачам re-engage не шлемо
            User.total_reviews > 0,
            last_review_sq.c.last_review < inactive_before,
            (User.last_reengage_push_at.is_(None))
            | (User.last_reengage_push_at < cooldown_before),
        )
        .order_by(last_review_sq.c.last_review.asc())
        .limit(MAX_PER_TICK)
    )).all()

    out: list[tuple[User, int]] = []
    for user, last_review in rows:
        days_since = (now - last_review).days if last_review else INACTIVE_DAYS
        out.append((user, days_since))
    return out


async def send_reengage_for_user(bot: Bot, user: User, days_since: int) -> bool:
    """Один push для конкретного юзера. Повертає True якщо реально відправили."""
    async with SessionLocal() as session:
        word = await _pick_reengage_word(session, user.id)
        if not word:
            return False

        lang = user.native_lang or "uk"
        title = bt("reengage.title", lang, days=days_since)
        body = bt(
            "reengage.body",
            lang,
            days=days_since,
            word=escape(word.word),
            translation=escape(word.translation or ""),
        )
        text = f"{title}\n\n{body}"

        try:
            await bot.send_message(chat_id=user.telegram_id, text=text)
        except Exception as e:
            logger.warning(
                "reengage send failed for user %s: %s", user.telegram_id, e
            )
            from core.user_service import disable_reminders_if_blocked
            await disable_reminders_if_blocked(user.telegram_id, e, tenant_id=user.tenant_id)
            return False

        await session.execute(
            sa_update(User)
            .where(User.id == user.id)
            .values(last_reengage_push_at=datetime.now(timezone.utc))
        )
        await session.commit()

    analytics.capture(user.telegram_id, "reengage_push_sent", {
        "days_since_last_review": days_since,
        "word_id": word.id,
        "word_status": word.status,
    })
    return True


async def check_and_send_reengage(bot: Bot) -> None:
    try:
        async with SessionLocal() as session:
            candidates = await _eligible_users(session)

        if not candidates:
            return

        from core.bot_registry import get_bot
        sent = 0
        for user, days_since in candidates:
            try:
                # Пуш із бота власного тенанта юзера (фолбек — переданий, тенант 1).
                user_bot = get_bot(user.tenant_id) or bot
                if await send_reengage_for_user(user_bot, user, days_since):
                    sent += 1
                    await asyncio.sleep(0.05)
            except Exception as e:
                logger.warning(
                    "reengage iter failed for user %s: %s", user.telegram_id, e
                )

        if sent:
            logger.info("💌 Sent %d re-engagement pushes", sent)

    except Exception as e:
        logger.error("reengage job error: %s", e, exc_info=True)


async def reengage_loop(bot: Bot) -> None:
    """Раз на 60 хв перевіряємо. Чaстіше не треба - re-engage не term-sensitive,
    а кожна хвилина — зайве навантаження на запит з JOIN'ом."""
    logger.info("💌 Re-engagement scheduler started (every 60 min)")
    while True:
        try:
            await check_and_send_reengage(bot)
        except Exception as e:
            logger.error("reengage loop error: %s", e)
        await asyncio.sleep(60 * 60)
