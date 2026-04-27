"""
Хак: робить так що одне зі слів стає 'до повторення прямо зараз'.
Для тестування /review без чекання 24 годин.
"""
import asyncio
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, update
from core.db import SessionLocal, engine
from core.models import Word


async def make_word_due_now(telegram_id: int):
    """Робить найновіше слово юзера 'до повторення зараз'"""
    async with SessionLocal() as session:
        # Беремо ID юзера за telegram_id
        from core.models import User
        result = await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        user = result.scalar_one_or_none()
        if not user:
            print(f"❌ Юзер з telegram_id={telegram_id} не знайдений")
            return
        
        # Беремо слова юзера
        result = await session.execute(
            select(Word)
            .where(Word.user_id == user.id, Word.status == "learning")
            .order_by(Word.created_at.desc())
            .limit(3)
        )
        words = list(result.scalars().all())
        
        if not words:
            print("❌ У юзера немає слів")
            return
        
        # Робимо їх 'просроченими'
        past = datetime.now(timezone.utc) - timedelta(hours=1)
        for word in words:
            word.next_review = past
        
        await session.commit()
        print(f"✅ Зроблено {len(words)} слів готовими для повторення:")
        for w in words:
            print(f"   • {w.word}")
    
    await engine.dispose()


if __name__ == "__main__":
    # ⚠️ ЗАМІНИ на свій реальний telegram_id
    # Знайти можна так: натисни /start у боті, в логах буде "User XXXXXX started"
    YOUR_TELEGRAM_ID = 469478065  # ← ЗАМІНИ на свій!
    
    asyncio.run(make_word_due_now(YOUR_TELEGRAM_ID))