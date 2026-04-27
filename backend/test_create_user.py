"""
Тестове створення юзера в БД.
Запусти: python test_create_user.py
"""
import asyncio
from core.db import SessionLocal, engine
from core.models import User


async def create_test_user():
    print("👤 Створюю тестового юзера...")
    
    async with SessionLocal() as session:
        # Створюємо юзера з фейковим Telegram ID
        new_user = User(
            telegram_id=999999999,
            username="test_user",
            first_name="Test",
            native_lang="uk",
            target_lang="en",
            plan="free",
        )
        
        session.add(new_user)
        await session.commit()
        await session.refresh(new_user)
        
        print(f"✅ Юзер створений!")
        print(f"   ID: {new_user.id}")
        print(f"   Telegram ID: {new_user.telegram_id}")
        print(f"   Username: {new_user.username}")
        print(f"   Plan: {new_user.plan}")
        print(f"   Native: {new_user.native_lang} → Target: {new_user.target_lang}")
        print(f"   Created: {new_user.created_at}")
    
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(create_test_user())