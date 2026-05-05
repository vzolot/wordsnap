"""
Idempotent schema migrations виконуються ПЕРЕД стартом бота.

Кожна "міграція" — окремий SQL який можна виконати безпечно скільки завгодно
разів (IF NOT EXISTS, ADD COLUMN IF NOT EXISTS тощо). Якщо колонки/таблиці
немає — створюється; якщо є — нічого не відбувається.

Це усуває корінь усіх «бот падає бо колонки немає у БД» проблем — кожен
push автоматично синхронізує схему.
"""
import logging

from sqlalchemy import text

from .db import engine

logger = logging.getLogger(__name__)


# Список міграцій. ПОРЯДОК ВАЖЛИВИЙ — нові додавай у кінець, не змінюй старі.
MIGRATIONS: list[tuple[str, str]] = [
    (
        "users.region",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS region VARCHAR(50)",
    ),
    (
        "users.total_xp",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS total_xp INTEGER DEFAULT 0",
    ),
    (
        "users.target_lang_nullable",
        "ALTER TABLE users ALTER COLUMN target_lang DROP NOT NULL",
    ),
    (
        "words.last_reminder_at",
        "ALTER TABLE words ADD COLUMN IF NOT EXISTS last_reminder_at TIMESTAMPTZ",
    ),
    (
        "ai_cache table",
        """
        CREATE TABLE IF NOT EXISTS ai_cache (
            id BIGSERIAL PRIMARY KEY,
            word VARCHAR(100) NOT NULL,
            target_lang VARCHAR(5) NOT NULL,
            native_lang VARCHAR(5) NOT NULL,
            data JSONB NOT NULL,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE(word, target_lang, native_lang)
        )
        """,
    ),
    (
        "ai_cache index",
        "CREATE INDEX IF NOT EXISTS idx_ai_cache_lookup "
        "ON ai_cache(word, target_lang, native_lang)",
    ),
    (
        "users.last_streak_save_date",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS last_streak_save_date DATE",
    ),
    (
        "users.referral_code",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS referral_code VARCHAR(16) UNIQUE",
    ),
    (
        "users.referred_by",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS referred_by BIGINT REFERENCES users(id) ON DELETE SET NULL",
    ),
    (
        "users.referrals_count",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS referrals_count INTEGER NOT NULL DEFAULT 0",
    ),
    (
        "users.referral_code idx",
        "CREATE INDEX IF NOT EXISTS idx_users_referral_code ON users(referral_code)",
    ),
]


async def run_auto_migrations() -> None:
    """Виконує всі ідемпотентні міграції. Логує кожну."""
    logger.info("🔧 Running auto-migrations…")
    applied = 0
    failed = 0

    async with engine.begin() as conn:
        for name, sql in MIGRATIONS:
            try:
                await conn.execute(text(sql))
                logger.info(f"  ✓ {name}")
                applied += 1
            except Exception as e:
                # Помилка не валить процес — але логуємо
                logger.error(f"  ✗ {name}: {e}")
                failed += 1

    logger.info(f"🔧 Auto-migrations done: {applied} ok, {failed} failed")
