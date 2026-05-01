"""
Сервіс роботи зі словами в БД.
"""
import logging
from datetime import datetime, timedelta, timezone
from sqlalchemy import select, and_
from sqlalchemy.exc import IntegrityError

from .models import Word
from .db import SessionLocal
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
) -> tuple[Word | None, float]:
    """
    Обробляє відповідь юзера на повторення.
    Returns: (updated_word, new_interval_days)
    """
    async with SessionLocal() as session:
        db_result = await session.execute(
            select(Word).where(Word.id == word_id)
        )
        word = db_result.scalar_one_or_none()

        if not word:
            return None, 0

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
            interval_before=word.interval_days,
            interval_after=new_interval,
            ease_before=word.ease_factor,
            ease_after=new_ease,
        )
        session.add(review_record)

        await session.commit()
        await session.refresh(word)

        logger.info(
            f"Review: word_id={word_id} result={result} "
            f"new_interval={new_interval:.1f}d ease={new_ease:.2f}"
        )

        return word, new_interval
