"""
Тест підключення до БД.
Запусти: python test_db.py
"""
import asyncio
from sqlalchemy import text
from core.db import engine


async def test_connection():
    print("🔌 Перевіряю підключення до Supabase...")
    
    try:
        async with engine.connect() as conn:
            # Перевірка 1: підключення
            result = await conn.execute(text("SELECT version()"))
            version = result.scalar()
            print(f"✅ Підключено! {version[:60]}...")
            
            # Перевірка 2: чи є наші таблиці
            result = await conn.execute(text("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public'
                  AND table_type = 'BASE TABLE'
                ORDER BY table_name
            """))
            tables = [row[0] for row in result.fetchall()]
            
            print(f"\n📋 Знайдено таблиць: {len(tables)}")
            for t in tables:
                print(f"   • {t}")
            
            expected = {
                "users", "words", "reviews", "subscriptions",
                "theme_packs", "theme_pack_words", "user_theme_packs"
            }
            missing = expected - set(tables)
            
            if missing:
                print(f"\n⚠️  Не вистачає: {missing}")
            else:
                print("\n🎉 Всі таблиці на місці!")
                
    except Exception as e:
        print(f"❌ ПОМИЛКА: {e}")
        print("\nПеревір:")
        print("  1. DATABASE_URL у .env правильний?")
        print("  2. Порт 6543 (а не 5432)?")
        print("  3. Пароль БД правильний?")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(test_connection())