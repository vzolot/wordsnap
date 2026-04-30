"""
Database connection module.
Створює engine для асинхронного підключення до Supabase PostgreSQL.
"""
import os
import uuid
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool
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


# Engine з налаштуваннями для Supabase Pooler (pgbouncer transaction mode)
engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    poolclass=NullPool,  # Не кешуємо з'єднання — критично для pgbouncer
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