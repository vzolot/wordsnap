"""
Сервіс роботи зі словами в БД.
"""
import logging
from datetime import datetime, timedelta, timezone
from sqlalchemy import select, and_, update
from sqlalchemy.exc import IntegrityError

from .models import Word, User
from .db import SessionLocal
from .rewards import detect_tier_crossed, xp_for_result
from .srs import calculate_next_review, ReviewResult

logger = logging.getLogger(__name__)


async def word_exists(user_id: int, word: str, target_lang: str) -> bool:
    """Перевіряє чи юзер вже додавав це слово"""
    async with SessionLocal() as session:
        result = await session.execute(
            select(Word).where(
                Word.user_id == user_id,
                Word.word == word.lower().strip(),
                Word.target_lang == target_lang,
            )
        )
        return result.scalar_one_or_none() is not None


async def save_word(
    user_id: int,
    word: str,
    target_lang: str,
    ai_data: dict,
    image_url: str | None = None,
) -> bool:
    """
    Зберігає слово в БД з даними від AI і картинкою.
    Повертає True якщо успішно, False якщо помилка.
    Прибрано session.refresh() — економія часу.
    """
    word_clean = word.lower().strip()
    next_review = datetime.now(timezone.utc) + timedelta(days=1)

    try:
        async with SessionLocal() as session:
            new_word = Word(
                user_id=user_id,
                word=word_clean,
                translation=ai_data.get("translation", ""),
                part_of_speech=ai_data.get("part_of_speech"),
                difficulty=ai_data.get("difficulty"),
                examples=ai_data.get("examples"),
                memory_tip=ai_data.get("memory_tip"),
                image_url=image_url,
                image_keyword=ai_data.get("image_keyword"),
                target_lang=target_lang,
                next_review=next_review,
                interval_days=1.0,
                ease_factor=2.5,
                review_count=0,
                status="learning",
                source="manual",
            )

            session.add(new_word)
            await session.commit()
            # session.refresh() ПРИБРАНО — економимо ~1с

            logger.info(f"Saved word '{word_clean}' for user_id={user_id}")
            return True

    except IntegrityError:
        logger.warning(f"Word '{word_clean}' already exists for user_id={user_id}")
        return False
    except Exception as e:
        logger.error(f"Error saving word: {e}")
        return False


async def get_words_due_review(user_id: int, limit: int = 10) -> list[Word]:
    """Повертає слова яким час повторити"""
    async with SessionLocal() as session:
        now = datetime.now(timezone.utc)
        result = await session.execute(
            select(Word)
            .where(
                and_(
                    Word.user_id == user_id,
                    Word.status == "learning",
                    Word.next_review <= now,
                )
            )
            .order_by(Word.next_review)
            .limit(limit)
        )
        return list(result.scalars().all())


async def get_word_for_reminder(user_id: int, cooldown_hours: int) -> Word | None:
    """
    Повертає одне слово для нагадування — таке, де next_review <= now,
    і яке не нагадували протягом останніх cooldown_hours.
    """
    async with SessionLocal() as session:
        now = datetime.now(timezone.utc)
        cooldown_threshold = now - timedelta(hours=cooldown_hours)
        result = await session.execute(
            select(Word)
            .where(
                Word.user_id == user_id,
                Word.status == "learning",
                Word.next_review <= now,
                (Word.last_reminder_at.is_(None)) | (Word.last_reminder_at < cooldown_threshold),
            )
            .order_by(Word.next_review)
            .limit(1)
        )
        return result.scalar_one_or_none()


async def mark_word_reminded(word_id: int) -> None:
    """Записує час останнього нагадування — щоб не спамити те саме слово."""
    async with SessionLocal() as session:
        result = await session.execute(select(Word).where(Word.id == word_id))
        word = result.scalar_one_or_none()
        if word:
            word.last_reminder_at = datetime.now(timezone.utc)
            await session.commit()


async def get_word_by_id(word_id: int) -> Word | None:
    """Отримати слово за ID"""
    async with SessionLocal() as session:
        result = await session.execute(
            select(Word).where(Word.id == word_id)
        )
        return result.scalar_one_or_none()


async def process_review(
    word_id: int,
    result: ReviewResult,
    user_id: int | None = None,
) -> tuple[Word | None, float, tuple[int, str, str | None] | None]:
    """
    Обробляє відповідь юзера на повторення.

    `user_id` (коли передано) гейтить доступ — слово мусить належати цьому
    юзеру. Без цього будь-хто міг би слати рев'ю по чужих word_id і псувати
    їхній SRS-графік / накручувати XP. None лишено для внутрішніх викликів.

    Returns: (updated_word, new_interval_days, tier_crossed_or_None)
    tier_crossed — нагорода за подоланий поріг. None якщо tier не змінився.
    """
    async with SessionLocal() as session:
        stmt = select(Word).where(Word.id == word_id)
        if user_id is not None:
            stmt = stmt.where(Word.user_id == user_id)
        db_result = await session.execute(stmt)
        word = db_result.scalar_one_or_none()

        if not word:
            return None, 0, None

        # Знімаємо ДО-значення перед перезаписом — інакше interval_before/
        # ease_before дорівнювали б *after* (поля вже оновлені) і історія рев'ю
        # завжди була б порожньою.
        prev_interval = word.interval_days
        prev_ease = word.ease_factor

        new_interval, new_ease, next_review, new_status = calculate_next_review(
            result=result,
            current_interval=word.interval_days,
            current_ease=word.ease_factor,
            review_count=word.review_count,
        )

        word.interval_days = new_interval
        word.ease_factor = new_ease
        word.next_review = next_review
        word.review_count += 1
        word.status = new_status
        word.last_reviewed_at = datetime.now(timezone.utc)

        if result == "knew":
            word.correct_count += 1

        from .models import Review
        review_record = Review(
            word_id=word.id,
            user_id=word.user_id,
            result=result,
            interval_before=prev_interval,
            interval_after=new_interval,
            ease_before=prev_ease,
            ease_after=new_ease,
        )
        session.add(review_record)

        # Нараховуємо XP — спершу читаємо поточне значення для tier-detection
        old_xp_row = await session.execute(
            select(User.total_xp).where(User.id == word.user_id)
        )
        old_xp = old_xp_row.scalar() or 0
        xp = xp_for_result(result)
        new_xp = old_xp + xp

        await session.execute(
            update(User).where(User.id == word.user_id).values(
                total_xp=new_xp,
                total_reviews=User.total_reviews + 1,
            )
        )

        await session.commit()
        await session.refresh(word)

        tier_up = detect_tier_crossed(old_xp, new_xp)

        logger.info(
            f"Review: word_id={word_id} result={result} "
            f"new_interval={new_interval:.1f}d ease={new_ease:.2f} "
            f"xp={old_xp}→{new_xp}{' TIER+' if tier_up else ''}"
        )

        return word, new_interval, tier_up
