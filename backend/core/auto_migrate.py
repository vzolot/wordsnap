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
        "users.last_daily_push_date",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS last_daily_push_date DATE",
    ),
    (
        "users.avatar_emoji",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS avatar_emoji VARCHAR(16)",
    ),
    (
        "users.show_on_leaderboard",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS show_on_leaderboard BOOLEAN NOT NULL DEFAULT TRUE",
    ),
    (
        "users.last_push_at",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS last_push_at TIMESTAMPTZ",
    ),
    (
        "app_state table",
        """
        CREATE TABLE IF NOT EXISTS app_state (
            key VARCHAR(64) PRIMARY KEY,
            value TEXT,
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )
        """,
    ),
    ("rls.app_state", "ALTER TABLE app_state ENABLE ROW LEVEL SECURITY"),
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
    # ── Row-Level Security ──────────────────────────────────────────────
    # Supabase публічно експонує таблиці через PostgREST (REST API). Без RLS
    # будь-хто з anon-key може читати/редагувати дані. Наш backend
    # підключається як postgres-superuser → bypass RLS, тому ENABLE RLS без
    # policy = доступ є тільки у нас, REST API повертає 401.
    ("rls.users",          "ALTER TABLE users ENABLE ROW LEVEL SECURITY"),
    ("rls.words",          "ALTER TABLE words ENABLE ROW LEVEL SECURITY"),
    ("rls.reviews",        "ALTER TABLE reviews ENABLE ROW LEVEL SECURITY"),
    ("rls.ai_cache",       "ALTER TABLE ai_cache ENABLE ROW LEVEL SECURITY"),
    ("rls.payment_history","ALTER TABLE payment_history ENABLE ROW LEVEL SECURITY"),
    # Залишкові таблиці з попередніх експериментів — IF EXISTS на випадок
    # коли їх уже немає у схемі. Просто прикриваємо REST API-доступ.
    ("rls.subscriptions",     "ALTER TABLE IF EXISTS public.subscriptions ENABLE ROW LEVEL SECURITY"),
    ("rls.theme_packs",       "ALTER TABLE IF EXISTS public.theme_packs ENABLE ROW LEVEL SECURITY"),
    ("rls.theme_pack_words",  "ALTER TABLE IF EXISTS public.theme_pack_words ENABLE ROW LEVEL SECURITY"),
    ("rls.user_theme_packs",  "ALTER TABLE IF EXISTS public.user_theme_packs ENABLE ROW LEVEL SECURITY"),
    # SECURITY DEFINER views — переключаємо на security_invoker щоб view
    # викликалось правами caller'а, не creator'а. Тоді RLS на нижче-лежачих
    # таблицях нормально застосовується.
    (
        "view.user_stats.invoker",
        "ALTER VIEW IF EXISTS public.user_stats SET (security_invoker = true)",
    ),
    (
        "view.words_due_review.invoker",
        "ALTER VIEW IF EXISTS public.words_due_review SET (security_invoker = true)",
    ),
    # Функція з мутабельним search_path — фіксуємо щоб уникнути hijack-сценарію
    # коли зловмисник створює свою таблицю/функцію з тим самим іменем у власній
    # схемі і trigger її викликає замість оригіналу.
    # Postgres не підтримує "ALTER FUNCTION IF EXISTS" — обгортаємо у DO-блок
    # з перевіркою у pg_proc.
    # Anti-spam timestamp для re-engagement push (7+ днів без перевірки слів).
    (
        "users.last_reengage_push_at",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS last_reengage_push_at TIMESTAMPTZ",
    ),
    # Motivation з ad-cohort survey: «living/work/studying/family/travel/self».
    # Сегментує themes-recommendations і analytics. NULL = не питали (organic).
    (
        "users.motivation",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS motivation VARCHAR(20)",
    ),
    # Acquisition payload зі /start (igads_*, ref_*, ig_*, ...). Зберігаємо
    # на bot-side щоб не залежати від WebApp SDK перенесення start_param.
    (
        "users.acquisition_payload",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS acquisition_payload VARCHAR(64)",
    ),
    # Influencer/affiliate program — окремий канал від user-to-user
    # referrals. Слаг закодований у `aff_<slug>` deeplink payload.
    # Юзер «прийшов через Rue» → affiliate_slug='rue', affiliate_at=now.
    # Кожен payment у window [affiliate_at, affiliate_at + duration_days]
    # генерує revenue-share row у affiliate_revenue.
    (
        "users.affiliate_slug",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS affiliate_slug VARCHAR(40)",
    ),
    (
        "users.affiliate_at",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS affiliate_at TIMESTAMPTZ",
    ),
    # orderReference активної WayForPay-регулярки. Зберігаємо при першому
    # успішному платежі — потрібен для скасування підписки через regularApi.
    (
        "users.subscription_order_ref",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS subscription_order_ref VARCHAR(80)",
    ),
    (
        "affiliates table",
        """
        CREATE TABLE IF NOT EXISTS affiliates (
            slug             VARCHAR(40) PRIMARY KEY,
            name             VARCHAR(120) NOT NULL,
            rev_share_pct    NUMERIC(5,2) NOT NULL DEFAULT 20.00,
            duration_days    INTEGER NOT NULL DEFAULT 180,
            notes            TEXT,
            created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
    ),
    (
        "affiliate_revenue table",
        """
        CREATE TABLE IF NOT EXISTS affiliate_revenue (
            id               BIGSERIAL PRIMARY KEY,
            affiliate_slug   VARCHAR(40) NOT NULL REFERENCES affiliates(slug) ON DELETE CASCADE,
            user_id          BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            payment_id       BIGINT REFERENCES payment_history(id) ON DELETE SET NULL,
            payment_amount   NUMERIC(10,2) NOT NULL,
            payment_currency VARCHAR(10) NOT NULL DEFAULT 'USD',
            rev_share_pct    NUMERIC(5,2) NOT NULL,
            share_amount     NUMERIC(10,2) NOT NULL,
            payment_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
    ),
    (
        "affiliate_revenue.slug_payment_idx",
        "CREATE INDEX IF NOT EXISTS idx_aff_rev_slug_paymentat "
        "ON affiliate_revenue(affiliate_slug, payment_at DESC)",
    ),
    ("rls.affiliates", "ALTER TABLE affiliates ENABLE ROW LEVEL SECURITY"),
    ("rls.affiliate_revenue", "ALTER TABLE affiliate_revenue ENABLE ROW LEVEL SECURITY"),
    (
        "leads table",
        """
        CREATE TABLE IF NOT EXISTS leads (
            id               BIGSERIAL PRIMARY KEY,
            email            VARCHAR(320) NOT NULL,
            source           VARCHAR(60),
            campaign         VARCHAR(120),
            ui_lang          VARCHAR(8),
            target_lang      VARCHAR(8),
            distinct_id      VARCHAR(80),
            ip               VARCHAR(64),
            user_agent       TEXT,
            telegram_user_id BIGINT REFERENCES users(id) ON DELETE SET NULL,
            converted_at     TIMESTAMPTZ,
            unsubscribed_at  TIMESTAMPTZ,
            created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (email, source)
        )
        """,
    ),
    (
        "leads.created_idx",
        "CREATE INDEX IF NOT EXISTS idx_leads_created ON leads(created_at DESC)",
    ),
    (
        "leads.source_camp_idx",
        "CREATE INDEX IF NOT EXISTS idx_leads_source_campaign ON leads(source, campaign)",
    ),
    ("rls.leads", "ALTER TABLE leads ENABLE ROW LEVEL SECURITY"),
    (
        "fn.update_updated_at_column.search_path",
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_proc p
                JOIN pg_namespace n ON n.oid = p.pronamespace
                WHERE p.proname = 'update_updated_at_column'
                  AND n.nspname = 'public'
            ) THEN
                EXECUTE 'ALTER FUNCTION public.update_updated_at_column() '
                     || 'SET search_path = pg_catalog, public';
            END IF;
        END $$;
        """,
    ),
]


async def run_auto_migrations() -> None:
    """Виконує всі ідемпотентні міграції. Кожна — у власній транзакції,
    щоб помилка однієї не блокувала наступні (Postgres абортить транзакцію
    цілком при першому failure, і всі subsequent execute'и в тій же
    транзакції повертають InFailedSqlTransaction)."""
    logger.info("🔧 Running auto-migrations…")
    applied = 0
    failed = 0

    for name, sql in MIGRATIONS:
        try:
            async with engine.begin() as conn:
                await conn.execute(text(sql))
            logger.info(f"  ✓ {name}")
            applied += 1
        except Exception as e:
            # Помилка не валить процес — але логуємо. Наступні міграції
            # виконаються нормально, бо в новій транзакції.
            logger.error(f"  ✗ {name}: {e}")
            failed += 1

    logger.info(f"🔧 Auto-migrations done: {applied} ok, {failed} failed")
