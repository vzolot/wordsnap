"""Backfill для слів без image_url.

При додаванні слова через /api/words ми робимо один синхронний виклик
Unsplash. Він може повернути None через rate-limit (free tier 50/hour),
network blip чи відсутність результатів. Тоді word зберігається з
image_url=NULL, і user бачить 📸 placeholder.

Цей loop раз на 30 хв витягає до 20 таких "сирітських" слів і пробує
ще раз. Gentle 2-секундна пауза між викликами щоб не вичерпати
rate limit Unsplash.
"""
import asyncio
import logging

from aiogram import Bot
from sqlalchemy import func, select, update

from core.db import SessionLocal
from core.models import Word
from core.unsplash_client import search_image

logger = logging.getLogger(__name__)

BATCH_SIZE = 20
PAUSE_BETWEEN_CALLS_SEC = 2
LOOP_INTERVAL_SEC = 30 * 60  # 30 хв


async def backfill_once() -> int:
    """Один прохід — шукає слова без картинки і пробує Unsplash. Повертає
    скільки оновлено."""
    async with SessionLocal() as session:
        # Випадковий порядок, не newest-first: інакше якщо найновіші 20 «сиріт»
        # стабільно не мають картинки в Unsplash, цикл ретраїв їх вічно і
        # ніколи не доходить до старіших. random() поступово покриває всі.
        rows = (await session.execute(
            select(Word).where(Word.image_url.is_(None))
            .order_by(func.random())
            .limit(BATCH_SIZE)
        )).scalars().all()

    if not rows:
        return 0

    logger.info(f"🖼  Backfill: {len(rows)} words without image_url")
    updated = 0
    for word in rows:
        keyword = word.image_keyword or word.word
        try:
            url = await search_image(keyword)
        except Exception as e:
            logger.warning(f"backfill search_image failed for '{keyword}': {e}")
            url = None

        if url:
            try:
                async with SessionLocal() as session:
                    await session.execute(
                        update(Word).where(Word.id == word.id).values(image_url=url)
                    )
                    await session.commit()
                updated += 1
            except Exception as e:
                logger.warning(f"backfill update failed for word {word.id}: {e}")

        await asyncio.sleep(PAUSE_BETWEEN_CALLS_SEC)

    if updated:
        logger.info(f"🖼  Backfill: filled {updated}/{len(rows)} images")
    return updated


async def image_backfill_loop(bot: Bot | None = None) -> None:
    logger.info("🖼  Image backfill scheduler started")
    while True:
        try:
            await backfill_once()
        except Exception as e:
            logger.error(f"image_backfill loop error: {e}", exc_info=True)
        await asyncio.sleep(LOOP_INTERVAL_SEC)
