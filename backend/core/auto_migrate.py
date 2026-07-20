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
        "users.demo_pitch_sent",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS demo_pitch_sent BOOLEAN NOT NULL DEFAULT FALSE",
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
    # Flag for internal/test accounts (founder, future testers) so they don't
    # dilute product analytics. `admin_report.py` filters this out everywhere.
    # Set manually via SQL (`UPDATE users SET is_test_account=TRUE WHERE
    # telegram_id=<id>`) — not auto-managed.
    (
        "users.is_test_account",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_test_account BOOLEAN NOT NULL DEFAULT FALSE",
    ),
    # True коли користувач явно обрав рідну мову (бот-сетап / Settings). Mini-app
    # тоді показує UI цією мовою навіть якщо мова телефона інша. Авто-визначена
    # мова лишає false → UI слідує за мовою телефона (tApps-вимога).
    (
        "users.lang_explicit",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS lang_explicit BOOLEAN NOT NULL DEFAULT FALSE",
    ),
    # ════════════════════════════════════════════════════════════════════
    # WHITE-LABEL M1 — мультитенантна схема. Все ідемпотентне і безпечне для
    # прод-бази: усі нові колонки з DEFAULT 1, тому старий код, що вставляє
    # users/words/reviews без tenant_id, продовжує працювати (запис їде у
    # тенант 1 = базовий WordSnap). DEFAULT приберемо пізніше (M4), коли весь
    # код стане tenant-aware.
    # ════════════════════════════════════════════════════════════════════
    (
        "tenants table",
        """
        CREATE TABLE IF NOT EXISTS tenants (
            id                     SERIAL PRIMARY KEY,
            slug                   VARCHAR(60) UNIQUE NOT NULL,
            display_name           TEXT NOT NULL,
            bot_token              TEXT,
            bot_id                 BIGINT UNIQUE,
            logo_url               TEXT,
            color_primary          VARCHAR(9) NOT NULL DEFAULT '#7C3AED',
            color_accent           VARCHAR(9) NOT NULL DEFAULT '#EC4899',
            owner_telegram_id      BIGINT,
            plan                   VARCHAR(20) NOT NULL DEFAULT 'trial',
            ai_snap_monthly_limit  INTEGER DEFAULT 30,
            billing_ui_enabled     BOOLEAN NOT NULL DEFAULT FALSE,
            digest_lead_hours      INTEGER NOT NULL DEFAULT 3,
            created_at             TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
    ),
    (
        "tenants.seed_default",
        # Базовий WordSnap-тенант. billing_ui увімкнено, AI-снап без ліміту
        # (NULL). bot_id/bot_token заповнюються на старті з TELEGRAM_BOT_TOKEN
        # (див. sync_default_tenant у M2/M3), тут не чіпаємо.
        """
        INSERT INTO tenants (id, slug, display_name, color_primary, color_accent,
                             plan, ai_snap_monthly_limit, billing_ui_enabled)
        VALUES (1, 'wordsnap', 'WordSnap', '#7C3AED', '#EC4899',
                'active', NULL, TRUE)
        ON CONFLICT (id) DO NOTHING
        """,
    ),
    (
        "tenants.seq_bump",
        # id=1 вставлено явно — рухаємо sequence, щоб наступний тенант отримав
        # id=2, а не спробував 1 і впав на PK-конфлікті.
        "SELECT setval(pg_get_serial_sequence('tenants','id'), "
        "GREATEST((SELECT COALESCE(MAX(id),1) FROM tenants), 1))",
    ),
    # ── users: tenant_id + role ───────────────────────────────────────────
    (
        "users.tenant_id",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS tenant_id INTEGER NOT NULL DEFAULT 1",
    ),
    (
        "users.role",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS role VARCHAR(20) NOT NULL DEFAULT 'student'",
    ),
    (
        "users.tenant_id_fk",
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'users_tenant_id_fkey'
            ) THEN
                ALTER TABLE users ADD CONSTRAINT users_tenant_id_fkey
                    FOREIGN KEY (tenant_id) REFERENCES tenants(id);
            END IF;
        END $$;
        """,
    ),
    (
        "users.drop_telegram_unique",
        # Знімаємо будь-який single-column UNIQUE на telegram_id (авто-ім'я
        # users_telegram_id_key, але шукаємо надійно за колонками), щоб той
        # самий учень міг існувати у кількох тенантів. Композитний unique нижче.
        """
        DO $$
        DECLARE r record;
        BEGIN
            FOR r IN
                SELECT con.conname
                FROM pg_constraint con
                JOIN pg_class rel ON rel.oid = con.conrelid
                WHERE rel.relname = 'users' AND con.contype = 'u'
                  AND con.conkey = ARRAY[
                      (SELECT attnum FROM pg_attribute
                       WHERE attrelid = rel.oid AND attname = 'telegram_id')
                  ]
            LOOP
                EXECUTE 'ALTER TABLE users DROP CONSTRAINT ' || quote_ident(r.conname);
            END LOOP;
        END $$;
        """,
    ),
    (
        "users.telegram_tenant_unique",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_users_telegram_tenant "
        "ON users(telegram_id, tenant_id)",
    ),
    (
        "users.tenant_idx",
        "CREATE INDEX IF NOT EXISTS idx_users_tenant ON users(tenant_id)",
    ),
    # ── decks / deck_words / deck_assignments ─────────────────────────────
    (
        "decks table",
        """
        CREATE TABLE IF NOT EXISTS decks (
            id             BIGSERIAL PRIMARY KEY,
            tenant_id      INTEGER NOT NULL DEFAULT 1 REFERENCES tenants(id) ON DELETE CASCADE,
            owner_user_id  BIGINT REFERENCES users(id) ON DELETE SET NULL,
            title          TEXT NOT NULL,
            target_lang    VARCHAR(5),
            assign_to_all  BOOLEAN NOT NULL DEFAULT TRUE,
            created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
    ),
    (
        "decks.tenant_idx",
        "CREATE INDEX IF NOT EXISTS idx_decks_tenant ON decks(tenant_id)",
    ),
    (
        "deck_words table",
        """
        CREATE TABLE IF NOT EXISTS deck_words (
            id           BIGSERIAL PRIMARY KEY,
            deck_id      BIGINT NOT NULL REFERENCES decks(id) ON DELETE CASCADE,
            word         VARCHAR(255) NOT NULL,
            translation  TEXT NOT NULL,
            target_lang  VARCHAR(5),
            position     INTEGER NOT NULL DEFAULT 0,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (deck_id, word)
        )
        """,
    ),
    (
        "deck_words.deck_idx",
        "CREATE INDEX IF NOT EXISTS idx_deck_words_deck ON deck_words(deck_id)",
    ),
    (
        "deck_assignments table",
        """
        CREATE TABLE IF NOT EXISTS deck_assignments (
            id           BIGSERIAL PRIMARY KEY,
            deck_id      BIGINT NOT NULL REFERENCES decks(id) ON DELETE CASCADE,
            user_id      BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            assigned_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (deck_id, user_id)
        )
        """,
    ),
    (
        "deck_assignments.user_idx",
        "CREATE INDEX IF NOT EXISTS idx_deck_assignments_user ON deck_assignments(user_id)",
    ),
    # ── words: tenant_id + deck_id ────────────────────────────────────────
    (
        "words.tenant_id",
        "ALTER TABLE words ADD COLUMN IF NOT EXISTS tenant_id INTEGER NOT NULL DEFAULT 1",
    ),
    (
        "words.deck_id",
        "ALTER TABLE words ADD COLUMN IF NOT EXISTS deck_id BIGINT",
    ),
    (
        "words.tenant_deck_fk",
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'words_tenant_id_fkey') THEN
                ALTER TABLE words ADD CONSTRAINT words_tenant_id_fkey
                    FOREIGN KEY (tenant_id) REFERENCES tenants(id);
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'words_deck_id_fkey') THEN
                ALTER TABLE words ADD CONSTRAINT words_deck_id_fkey
                    FOREIGN KEY (deck_id) REFERENCES decks(id) ON DELETE SET NULL;
            END IF;
        END $$;
        """,
    ),
    (
        "words.tenant_idx",
        "CREATE INDEX IF NOT EXISTS idx_words_tenant ON words(tenant_id)",
    ),
    (
        "words.deck_idx",
        "CREATE INDEX IF NOT EXISTS idx_words_deck ON words(deck_id)",
    ),
    # ── reviews: tenant_id ────────────────────────────────────────────────
    (
        "reviews.tenant_id",
        "ALTER TABLE reviews ADD COLUMN IF NOT EXISTS tenant_id INTEGER NOT NULL DEFAULT 1",
    ),
    (
        "reviews.tenant_fk",
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'reviews_tenant_id_fkey') THEN
                ALTER TABLE reviews ADD CONSTRAINT reviews_tenant_id_fkey
                    FOREIGN KEY (tenant_id) REFERENCES tenants(id);
            END IF;
        END $$;
        """,
    ),
    (
        "reviews.tenant_idx",
        "CREATE INDEX IF NOT EXISTS idx_reviews_tenant ON reviews(tenant_id)",
    ),
    # ── ai_snap_usage ─────────────────────────────────────────────────────
    (
        "ai_snap_usage table",
        """
        CREATE TABLE IF NOT EXISTS ai_snap_usage (
            id         BIGSERIAL PRIMARY KEY,
            tenant_id  INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            month      VARCHAR(7) NOT NULL,
            count      INTEGER NOT NULL DEFAULT 0,
            UNIQUE (tenant_id, month)
        )
        """,
    ),
    # ── RLS на нових таблицях (як решта — прикриваємо Supabase PostgREST) ──
    ("rls.tenants",           "ALTER TABLE tenants ENABLE ROW LEVEL SECURITY"),
    ("rls.ai_snap_usage",     "ALTER TABLE ai_snap_usage ENABLE ROW LEVEL SECURITY"),
    ("rls.decks",             "ALTER TABLE decks ENABLE ROW LEVEL SECURITY"),
    ("rls.deck_words",        "ALTER TABLE deck_words ENABLE ROW LEVEL SECURITY"),
    ("rls.deck_assignments",  "ALTER TABLE deck_assignments ENABLE ROW LEVEL SECURITY"),
    # ════════════════════════════════════════════════════════════════════
    # WHITE-LABEL M9 — календар уроків.
    # ════════════════════════════════════════════════════════════════════
    (
        "tenants.lesson_config",
        # Тривалість уроку (= тривалість слота) і дедлайн скасування — конфіг/тенант.
        "ALTER TABLE tenants "
        "ADD COLUMN IF NOT EXISTS lesson_duration_min INTEGER NOT NULL DEFAULT 60, "
        "ADD COLUMN IF NOT EXISTS cancel_cutoff_hours INTEGER NOT NULL DEFAULT 12",
    ),
    (
        "teacher_availability table",
        # Тижневий шаблон доступності. weekday: 0=Пн..6=Нд; start_min/end_min —
        # хвилини від опівночі у ЛОКАЛЬНІЙ таймзоні викладача (users.timezone).
        """
        CREATE TABLE IF NOT EXISTS teacher_availability (
            id               BIGSERIAL PRIMARY KEY,
            tenant_id        INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            teacher_user_id  BIGINT REFERENCES users(id) ON DELETE CASCADE,
            weekday          SMALLINT NOT NULL,
            start_min        SMALLINT NOT NULL,
            end_min          SMALLINT NOT NULL,
            created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
    ),
    (
        "teacher_availability.idx",
        "CREATE INDEX IF NOT EXISTS idx_avail_tenant_teacher "
        "ON teacher_availability(tenant_id, teacher_user_id)",
    ),
    (
        "teacher_closed_dates table",
        """
        CREATE TABLE IF NOT EXISTS teacher_closed_dates (
            id               BIGSERIAL PRIMARY KEY,
            tenant_id        INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            teacher_user_id  BIGINT REFERENCES users(id) ON DELETE CASCADE,
            day              DATE NOT NULL,
            UNIQUE (tenant_id, teacher_user_id, day)
        )
        """,
    ),
    (
        "lessons table",
        """
        CREATE TABLE IF NOT EXISTS lessons (
            id                BIGSERIAL PRIMARY KEY,
            tenant_id         INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            teacher_user_id   BIGINT REFERENCES users(id) ON DELETE SET NULL,
            student_user_id   BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            starts_at_utc     TIMESTAMPTZ NOT NULL,
            duration_min      SMALLINT NOT NULL DEFAULT 60,
            status            VARCHAR(20) NOT NULL DEFAULT 'booked',
            reminder_24_sent  BOOLEAN NOT NULL DEFAULT FALSE,
            reminder_1_sent   BOOLEAN NOT NULL DEFAULT FALSE,
            digest_sent       BOOLEAN NOT NULL DEFAULT FALSE,
            created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
    ),
    (
        "lessons.no_double_booking",
        # Захист від подвійного бронювання: один активний ('booked') урок на
        # слот викладача. Скасовані не блокують повторне бронювання.
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_lessons_teacher_slot "
        "ON lessons(tenant_id, teacher_user_id, starts_at_utc) WHERE status = 'booked'",
    ),
    (
        "lessons.student_idx",
        "CREATE INDEX IF NOT EXISTS idx_lessons_student ON lessons(student_user_id, starts_at_utc)",
    ),
    (
        "lessons.upcoming_idx",
        "CREATE INDEX IF NOT EXISTS idx_lessons_upcoming "
        "ON lessons(tenant_id, starts_at_utc) WHERE status = 'booked'",
    ),
    ("rls.teacher_availability", "ALTER TABLE teacher_availability ENABLE ROW LEVEL SECURITY"),
    ("rls.teacher_closed_dates", "ALTER TABLE teacher_closed_dates ENABLE ROW LEVEL SECURITY"),
    ("rls.lessons",              "ALTER TABLE lessons ENABLE ROW LEVEL SECURITY"),
    # ── M12: алерти ризику відтоку ────────────────────────────────────────
    (
        "tenants.churn_alert_days",
        "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS churn_alert_days INTEGER NOT NULL DEFAULT 5",
    ),
    (
        "users.last_churn_alert_at",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS last_churn_alert_at TIMESTAMPTZ",
    ),
    # ── M13: домашнє завдання з дедлайном ─────────────────────────────────
    (
        "homework table",
        """
        CREATE TABLE IF NOT EXISTS homework (
            id           BIGSERIAL PRIMARY KEY,
            tenant_id    INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            deck_id      BIGINT NOT NULL REFERENCES decks(id) ON DELETE CASCADE,
            user_id      BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            due_at_utc   TIMESTAMPTZ NOT NULL,
            status       VARCHAR(20) NOT NULL DEFAULT 'assigned',
            reminder_sent BOOLEAN NOT NULL DEFAULT FALSE,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (deck_id, user_id)
        )
        """,
    ),
    (
        "homework.idx",
        "CREATE INDEX IF NOT EXISTS idx_homework_user ON homework(user_id, status)",
    ),
    ("rls.homework", "ALTER TABLE homework ENABLE ROW LEVEL SECURITY"),
    # ── M14: режим школи (кілька викладачів + групи) ──────────────────────
    (
        "tenants.is_school",
        "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS is_school BOOLEAN NOT NULL DEFAULT FALSE",
    ),
    (
        "users.is_active_teacher",
        # Owner може деактивувати викладача, не видаляючи. Дефолт TRUE.
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_active_teacher BOOLEAN NOT NULL DEFAULT TRUE",
    ),
    (
        "groups table",
        """
        CREATE TABLE IF NOT EXISTS groups (
            id               BIGSERIAL PRIMARY KEY,
            tenant_id        INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            name             TEXT NOT NULL,
            teacher_user_id  BIGINT REFERENCES users(id) ON DELETE SET NULL,
            created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
    ),
    (
        "groups.idx",
        "CREATE INDEX IF NOT EXISTS idx_groups_tenant_teacher ON groups(tenant_id, teacher_user_id)",
    ),
    (
        "group_members table",
        """
        CREATE TABLE IF NOT EXISTS group_members (
            id         BIGSERIAL PRIMARY KEY,
            group_id   BIGINT NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
            user_id    BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            added_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (group_id, user_id)
        )
        """,
    ),
    (
        "group_members.user_idx",
        "CREATE INDEX IF NOT EXISTS idx_group_members_user ON group_members(user_id)",
    ),
    (
        "decks.group_id",
        # Колода може адресуватись групі (school-режим).
        "ALTER TABLE decks ADD COLUMN IF NOT EXISTS group_id BIGINT REFERENCES groups(id) ON DELETE SET NULL",
    ),
    ("rls.groups",        "ALTER TABLE groups ENABLE ROW LEVEL SECURITY"),
    ("rls.group_members", "ALTER TABLE group_members ENABLE ROW LEVEL SECURITY"),
    # ── M15: місячний PDF-звіт (опція на тенанта) ─────────────────────────
    (
        "tenants.monthly_report_enabled",
        "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS monthly_report_enabled BOOLEAN NOT NULL DEFAULT FALSE",
    ),
    # ── Teacher UX: @username бота для кнопки «поділитися ботом» ───────────
    (
        "tenants.bot_username",
        "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS bot_username VARCHAR(64)",
    ),
    # ── Оплата сервісу викладачем ($19/міс, автопродовження) ──────────────
    (
        "tenants.billing",
        "ALTER TABLE tenants "
        "ADD COLUMN IF NOT EXISTS sub_status VARCHAR(20) NOT NULL DEFAULT 'trial', "
        "ADD COLUMN IF NOT EXISTS sub_price_usd NUMERIC(10,2) NOT NULL DEFAULT 19, "
        "ADD COLUMN IF NOT EXISTS sub_expires_at TIMESTAMPTZ, "
        "ADD COLUMN IF NOT EXISTS sub_order_ref TEXT, "
        "ADD COLUMN IF NOT EXISTS sub_rec_token TEXT, "
        "ADD COLUMN IF NOT EXISTS sub_auto_renew BOOLEAN NOT NULL DEFAULT FALSE, "
        "ADD COLUMN IF NOT EXISTS sub_next_charge_at TIMESTAMPTZ, "
        "ADD COLUMN IF NOT EXISTS sub_last_payment_at TIMESTAMPTZ, "
        "ADD COLUMN IF NOT EXISTS sub_reminder_sent_at TIMESTAMPTZ",
    ),
    (
        "payment_history.tenant_id",
        "ALTER TABLE payment_history ADD COLUMN IF NOT EXISTS tenant_id INTEGER",
    ),
    (
        "payment_history.user_id_nullable",
        "ALTER TABLE payment_history ALTER COLUMN user_id DROP NOT NULL",
    ),
    # ── Інвайт-посилання школи (викладачі + учні до викладача) ────────────
    (
        "tenants.teacher_invite_token",
        "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS teacher_invite_token VARCHAR(24)",
    ),
    (
        "groups.invite_token",
        "ALTER TABLE groups ADD COLUMN IF NOT EXISTS invite_token VARCHAR(24)",
    ),
    (
        "groups.invite_token_uq",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_groups_invite_token ON groups(invite_token) WHERE invite_token IS NOT NULL",
    ),
    (
        "groups.is_default",
        "ALTER TABLE groups ADD COLUMN IF NOT EXISTS is_default BOOLEAN NOT NULL DEFAULT FALSE",
    ),
    # ── Kiev → Kyiv: нормалізуємо збережений часовий пояс до канонічного IANA ─
    (
        "users.timezone_kyiv",
        "UPDATE users SET timezone='Europe/Kyiv' WHERE timezone='Europe/Kiev'",
    ),
    # ── Оплачені викладацькі місця (передоплата за N викладачів) ──────────────
    (
        "tenants.sub_teacher_seats",
        "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS sub_teacher_seats INTEGER NOT NULL DEFAULT 0",
    ),
    # ── Демо-тенанти: проспект отримує викладацький доступ на 3 дні ───────────
    (
        "tenants.is_demo",
        "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS is_demo BOOLEAN NOT NULL DEFAULT FALSE",
    ),
    (
        "users.demo_expires_at",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS demo_expires_at TIMESTAMPTZ",
    ),
    (
        "tenants.mark_demo",
        "UPDATE tenants SET is_demo = TRUE WHERE id IN (2, 3) AND is_demo = FALSE",
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
