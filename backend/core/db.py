"""
Database connection module.
Створює engine для асинхронного підключення до Supabase PostgreSQL.
"""
import os
import uuid
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from dotenv import load_dotenv

load_dotenv()

raw_url = os.getenv("DATABASE_URL", "")
if not raw_url:
    raise ValueError("DATABASE_URL не знайдено в .env файлі!")

raw_url = raw_url.strip().strip('"').strip("'")


def clean_url_for_asyncpg(url: str) -> str:
    """
    Очищає URL від параметрів, які asyncpg не розуміє.
    Конвертує postgresql:// → postgresql+asyncpg://
    """
    incompatible_params = {"pgbouncer", "sslmode", "channel_binding"}
    
    parsed = urlparse(url)
    query_params = parse_qs(parsed.query)
    
    cleaned_params = {
        k: v for k, v in query_params.items() 
        if k not in incompatible_params
    }
    
    new_query = urlencode(cleaned_params, doseq=True)
    new_scheme = "postgresql+asyncpg"
    
    cleaned = urlunparse((
        new_scheme,
        parsed.netloc,
        parsed.path,
        parsed.params,
        new_query,
        parsed.fragment
    ))
    
    return cleaned


DATABASE_URL = clean_url_for_asyncpg(raw_url)


# Унікальне ім'я prepared statement для кожного підключення
# Це обходить проблему з pgbouncer transaction mode
def _get_unique_statement_name():
    return f"__asyncpg_{uuid.uuid4().hex}__"


# Engine для Supabase Pooler (pgbouncer transaction mode).
#
# Раніше тут стояв NullPool — кожен запит відкривав свіже TCP+TLS+PG
# з'єднання, що додавало ~2-3 секунди на простий SELECT 1. NullPool
# був не потрібен — pgbouncer-сумісність забезпечують ось ці параметри:
#   - statement_cache_size=0 + prepared_statement_cache_size=0
#     → asyncpg не кешує prepared statements, які зламали б transaction-mode
#   - prepared_statement_name_func → унікальне ім'я per-call, на випадок
#     якщо asyncpg все ж створить ad-hoc prepared statement
#
# З нормальним pool маємо warm з'єднання, /health → ~150мс замість 2.5с,
# /api/stats з 6 паралельних запитів → ~150мс замість 5.7с.
engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_size=5,           # Базовий пул — стільки warm з'єднань тримаємо
    max_overflow=10,       # Burst-овери при сплеску трафіку (peak = 15)
    pool_pre_ping=True,    # Перевіряти SELECT 1 перед повторним використанням,
                           # щоб не натрапити на закрите Supabase-з'єднання
    pool_recycle=1800,     # Через 30 хв ідлу — рециклити (Supabase сам ріже idle)
    connect_args={
        "statement_cache_size": 0,
        "prepared_statement_cache_size": 0,
        "prepared_statement_name_func": _get_unique_statement_name,
        "ssl": "require",
    }
)

SessionLocal = async_sessionmaker(
    engine,
    expire_on_commit=False,
    class_=AsyncSession
)


class Base(DeclarativeBase):
    """Базовий клас для всіх SQLAlchemy моделей"""
    pass


async def get_db():
    """Dependency для FastAPI"""
    async with SessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()