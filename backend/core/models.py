"""
SQLAlchemy моделі — Python представлення таблиць БД.
"""
from datetime import datetime, time, date
from sqlalchemy import (
    BigInteger, Integer, String, Text, Boolean, DateTime, Date, Time,
    Float, Numeric, ForeignKey, JSON, UniqueConstraint
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from .db import Base


class User(Base):
    """Користувач Telegram бота"""
    __tablename__ = "users"
    # Учень може існувати в кількох тенантів під тим самим telegram_id —
    # унікальність саме по парі, не по telegram_id окремо.
    __table_args__ = (UniqueConstraint("telegram_id", "tenant_id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    # Multi-tenancy: кожен користувач належить рівно одному тенанту. Учень у
    # двох викладачів = два незалежні рядки (унікальність (telegram_id,
    # tenant_id), НЕ лише telegram_id). Дефолт 1 = базовий WordSnap-тенант,
    # щоб усі старі записи автоматично лишились у ньому.
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id"), nullable=False,
        default=1, server_default="1",
    )
    # 'student' | 'teacher' | 'owner'. Викладач тенанта бачить вкладку
    # «Викладач» у Mini App. owner (M14) — власник тенанта-школи.
    role: Mapped[str] = mapped_column(
        String(20), nullable=False, default="student", server_default="student",
    )
    telegram_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    username: Mapped[str | None] = mapped_column(String(100))
    first_name: Mapped[str | None] = mapped_column(String(100))
    last_name: Mapped[str | None] = mapped_column(String(100))
    language_code: Mapped[str | None] = mapped_column(String(10))

    # Налаштування мов
    native_lang: Mapped[str] = mapped_column(String(5), default="uk")
    target_lang: Mapped[str | None] = mapped_column(String(5))
    # True коли користувач САМ обрав рідну мову (бот-сетап або Settings), на
    # відміну від авто-визначеної з language_code телефона. Mini-app тоді
    # показує UI цією мовою навіть якщо мова телефона інша. Default false —
    # авто-визначена мова НЕ override'ить мову телефона (tApps-вимога).
    lang_explicit: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    region: Mapped[str | None] = mapped_column(String(50))
    # Аватар у leaderboard. None → детермінований default з telegram_id.
    avatar_emoji: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # Opt-out з leaderboard. Default true (показувати).
    show_on_leaderboard: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")

    # Підписка
    plan: Mapped[str] = mapped_column(String(20), default="free")
    plan_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    trial_used: Mapped[bool] = mapped_column(Boolean, default=False)

    # === Day 7: Recurring payments ===
    payment_rec_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    auto_renew: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    last_payment_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    next_charge_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    subscription_status: Mapped[str] = mapped_column(
        String(20), default="none", server_default="none"
    )  # none, active, cancelled, expired, failed
    # orderReference активної WayForPay-регулярки — ключ для скасування
    # підписки через regularApi REMOVE.
    subscription_order_ref: Mapped[str | None] = mapped_column(String(80), nullable=True)

    # Нагадування
    reminder_time: Mapped[time] = mapped_column(Time, default=time(9, 0))
    timezone: Mapped[str] = mapped_column(String(50), default="Europe/Kiev")
    reminders_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    # Антиспам для streak-save push (одне на день локального часу)
    last_streak_save_date: Mapped[date | None] = mapped_column(Date)
    # Антиспам для денного word-of-the-day push (legacy, лишилось як date —
    # використовується для backwards-compat міграції; нова логіка cooldown'у
    # читає last_push_at нижче)
    last_daily_push_date: Mapped[date | None] = mapped_column(Date)
    # Час останнього reminder-push (UTC). Scheduler шле повторні пуші коли
    # черга росте: до 3/день у вікні reminder_time...+12h з 5h cooldown.
    last_push_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Анти-спам для re-engagement push (один на 30 днів максимум на юзера).
    last_reengage_push_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Мотивація з ad-cohort опитника: living/work/studying/family/travel/self.
    # NULL = organic (не питали). Сегментує themes-personalization і analytics.
    motivation: Mapped[str | None] = mapped_column(String(20))
    # Acquisition payload зі /start (igads_*, ref_*, etc.). Зберігаємо на
    # bot-side щоб не залежати від WebApp SDK перенесення start_param.
    acquisition_payload: Mapped[str | None] = mapped_column(String(64))
    # Influencer/affiliate slug якщо юзер прийшов через aff_<slug> deeplink.
    # Дає інфлюенсеру revenue-share від платежів цього юзера протягом
    # affiliate.duration_days з affiliate_at. First-touch — не перетирається.
    affiliate_slug: Mapped[str | None] = mapped_column(String(40))
    affiliate_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # M12: анти-спам для алерту ризику відтоку (макс 1 на 7 днів на учня).
    last_churn_alert_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # M14: owner може деактивувати викладача (не видаляючи). Для non-teacher — no-op.
    is_active_teacher: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )

    # Referrals: унікальний код для запрошень + хто запросив + лічильник
    referral_code: Mapped[str | None] = mapped_column(String(16))
    referred_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"))
    referrals_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    # Денні ліміти
    words_added_today: Mapped[int] = mapped_column(Integer, default=0)
    last_reset_date: Mapped[date] = mapped_column(Date, server_default=func.current_date())

    # Статистика
    total_words: Mapped[int] = mapped_column(Integer, default=0)
    total_reviews: Mapped[int] = mapped_column(Integer, default=0)
    total_xp: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    streak_days: Mapped[int] = mapped_column(Integer, default=0)
    last_activity_date: Mapped[date | None] = mapped_column(Date)

    # When True, this row is excluded from admin/product analytics (admin_report.
    # py and any other internal stats) — for the founder's own account and any
    # future internal testers. Real product behavior (Pro, streaks shown to the
    # user, reminders) is unaffected; only analytics filter on this.
    is_test_account: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )

    # Часові мітки
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_active_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Зв'язок: один юзер → багато слів
    words: Mapped[list["Word"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin"
    )


class Word(Base):
    """Слово, яке вчить користувач"""
    __tablename__ = "words"
    __table_args__ = (UniqueConstraint("user_id", "word", "target_lang"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"))
    # Денормалізований tenant_id для швидкого скоупінгу без join через users.
    # Дефолт 1 = базовий тенант (усі старі слова).
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id"), nullable=False,
        default=1, server_default="1",
    )
    # Якщо слово матеріалізоване з колоди викладача — посилання на неї.
    # NULL = звичайне особисте слово учня (класичний WordSnap-флоу).
    deck_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("decks.id", ondelete="SET NULL"), nullable=True,
    )

    # Контент
    word: Mapped[str] = mapped_column(String(255), nullable=False)
    translation: Mapped[str] = mapped_column(Text, nullable=False)
    part_of_speech: Mapped[str | None] = mapped_column(String(50))
    difficulty: Mapped[str | None] = mapped_column(String(5))
    examples: Mapped[dict | None] = mapped_column(JSON)
    memory_tip: Mapped[str | None] = mapped_column(Text)
    image_url: Mapped[str | None] = mapped_column(Text)
    image_keyword: Mapped[str | None] = mapped_column(String(100))
    target_lang: Mapped[str] = mapped_column(String(5), nullable=False)

    # SRS стан
    next_review: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    interval_days: Mapped[float] = mapped_column(Float, default=1.0)
    ease_factor: Mapped[float] = mapped_column(Float, default=2.5)
    review_count: Mapped[int] = mapped_column(Integer, default=0)
    correct_count: Mapped[int] = mapped_column(Integer, default=0)

    # Статус
    status: Mapped[str] = mapped_column(String(20), default="learning")
    source: Mapped[str] = mapped_column(String(50), default="manual")

    # Часові мітки
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_reminder_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Зв'язок назад до юзера
    user: Mapped["User"] = relationship(back_populates="words")


class Review(Base):
    """Запис кожного повторення (для аналітики)"""
    __tablename__ = "reviews"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    word_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("words.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"))
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id"), nullable=False,
        default=1, server_default="1",
    )
    result: Mapped[str] = mapped_column(String(20), nullable=False)
    interval_before: Mapped[float | None] = mapped_column(Float)
    interval_after: Mapped[float | None] = mapped_column(Float)
    ease_before: Mapped[float | None] = mapped_column(Float)
    ease_after: Mapped[float | None] = mapped_column(Float)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AiCache(Base):
    """Кеш OpenAI-відповідей за (word, target_lang, native_lang).
    Перетинаючий запит з ідентичними параметрами повертає кеш миттєво
    замість виклику OpenAI (~3 сек → ~50 мс)."""
    __tablename__ = "ai_cache"
    __table_args__ = (UniqueConstraint("word", "target_lang", "native_lang"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    word: Mapped[str] = mapped_column(String(100), nullable=False)
    target_lang: Mapped[str] = mapped_column(String(5), nullable=False)
    native_lang: Mapped[str] = mapped_column(String(5), nullable=False)
    data: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class PaymentHistory(Base):
    """Історія платежів — для аналітики, дебагу і фінансової звітності"""
    __tablename__ = "payment_history"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"))
    order_reference: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="USD")
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    transaction_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    reason_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_recurring: Mapped[bool] = mapped_column(Boolean, default=False)
    rec_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

class Affiliate(Base):
    """Програма для інфлюенсерів — кожен має slug, який зашитий у deeplink
    `aff_<slug>`. При платежі юзера, який прийшов через slug, протягом
    `duration_days` від `users.affiliate_at` — фіксуємо `rev_share_pct`
    у `affiliate_revenue`. Дефолти: 20% × 6 міс (180 днів)."""
    __tablename__ = "affiliates"

    slug: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    rev_share_pct: Mapped[float] = mapped_column(Numeric(5, 2), default=20.0)
    duration_days: Mapped[int] = mapped_column(Integer, default=180)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class AffiliateRevenue(Base):
    """Кожна успішна оплата (`payment_history`) від юзера з активним
    affiliate_slug → row тут зі сумою share. Це source-of-truth для виплат
    і для адмін-статистики."""
    __tablename__ = "affiliate_revenue"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    affiliate_slug: Mapped[str] = mapped_column(
        String(40), ForeignKey("affiliates.slug", ondelete="CASCADE")
    )
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"))
    payment_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("payment_history.id", ondelete="SET NULL"), nullable=True
    )
    payment_amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    payment_currency: Mapped[str] = mapped_column(String(10), default="USD")
    rev_share_pct: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    share_amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    payment_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Lead(Base):
    """Email-leads з демо-лендера (`/demo`). Email-fallback потік для юзерів
    без Telegram. Конвертимо в `users` коли той самий email пізніше
    пройде через бота — `converted_at` ставимо тоді."""
    __tablename__ = "leads"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    source: Mapped[str | None] = mapped_column(String(60), nullable=True)
    campaign: Mapped[str | None] = mapped_column(String(120), nullable=True)
    ui_lang: Mapped[str | None] = mapped_column(String(8), nullable=True)
    target_lang: Mapped[str | None] = mapped_column(String(8), nullable=True)
    distinct_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    telegram_user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    converted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    unsubscribed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


# ─── White-label мультитенантність ──────────────────────────────────────────

class Tenant(Base):
    """Один тенант = один бренд викладача = один Telegram-бот. Дані тенантів
    повністю ізольовані через tenant_id у кожній таблиці з даними користувачів.
    Тенант id=1 — базовий WordSnap (billing-UI увімкнено, AI-снап без ліміту)."""
    __tablename__ = "tenants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String(60), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    # bot_token — секрет. НІКОЛИ не логувати, не віддавати в API, не слати в Sentry.
    bot_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Числова частина токена до ':' — для резолву тенанта з initData (bot_id).
    bot_id: Mapped[int | None] = mapped_column(BigInteger, unique=True, nullable=True)
    logo_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    color_primary: Mapped[str] = mapped_column(
        String(9), nullable=False, default="#7C3AED", server_default="#7C3AED"
    )
    color_accent: Mapped[str] = mapped_column(
        String(9), nullable=False, default="#EC4899", server_default="#EC4899"
    )
    owner_telegram_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    # 'trial' | 'active' | 'paused'. (M14 додасть 'solo' / 'school' для типу.)
    plan: Mapped[str] = mapped_column(
        String(20), nullable=False, default="trial", server_default="trial"
    )
    # Місячний ліміт AI-снапів (керування витратами OpenAI). NULL = без ліміту
    # (тенант id=1). Дефолт 30/міс для white-label.
    ai_snap_monthly_limit: Mapped[int | None] = mapped_column(
        Integer, nullable=True, default=30, server_default="30"
    )
    # Чи показувати учням екрани підписки/оплати. True лише для id=1.
    billing_ui_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    # Передурочний дайджест (M10): за скільки годин до уроку слати. Конфіг/тенант.
    digest_lead_hours: Mapped[int] = mapped_column(
        Integer, nullable=False, default=3, server_default="3"
    )
    # Календар (M9): тривалість уроку = тривалість слота; дедлайн скасування.
    lesson_duration_min: Mapped[int] = mapped_column(
        Integer, nullable=False, default=60, server_default="60"
    )
    cancel_cutoff_hours: Mapped[int] = mapped_column(
        Integer, nullable=False, default=12, server_default="12"
    )
    # M12: поріг днів бездіяльності для алерту ризику відтоку (конфіг/тенант).
    churn_alert_days: Mapped[int] = mapped_column(
        Integer, nullable=False, default=5, server_default="5"
    )
    # M14: режим школи (кілька викладачів+групи). false = solo-репетитор.
    is_school: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class AiSnapUsage(Base):
    """Лічильник AI-снапів на тенант за місяць — для контролю
    ai_snap_monthly_limit. Один рядок на (tenant_id, month='YYYY-MM')."""
    __tablename__ = "ai_snap_usage"
    __table_args__ = (UniqueConstraint("tenant_id", "month"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    month: Mapped[str] = mapped_column(String(7), nullable=False)  # 'YYYY-MM'
    count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")


class Deck(Base):
    """Колода викладача (шаблон). Слова-шаблони живуть у deck_words; учням
    вони матеріалізуються у words при призначенні (зберігаючи SRS-механіку).
    assign_to_all=true → всі учні тенанта; false → лише через deck_assignments."""
    __tablename__ = "decks"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False,
        default=1, server_default="1",
    )
    owner_user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    target_lang: Mapped[str | None] = mapped_column(String(5), nullable=True)
    assign_to_all: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    # M14: колода адресована групі (school-режим). NULL = не груповий таргет.
    group_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("groups.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class DeckWord(Base):
    """Слово-шаблон у колоді викладача (не має SRS-стану — це вихідний список)."""
    __tablename__ = "deck_words"
    __table_args__ = (UniqueConstraint("deck_id", "word"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    deck_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("decks.id", ondelete="CASCADE"), nullable=False
    )
    word: Mapped[str] = mapped_column(String(255), nullable=False)
    translation: Mapped[str] = mapped_column(Text, nullable=False)
    target_lang: Mapped[str | None] = mapped_column(String(5), nullable=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class DeckAssignment(Base):
    """Персональне призначення колоди учню (для assign_to_all=false)."""
    __tablename__ = "deck_assignments"
    __table_args__ = (UniqueConstraint("deck_id", "user_id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    deck_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("decks.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


# ─── Календар уроків (M9) ────────────────────────────────────────────────────

class TeacherAvailability(Base):
    """Тижневий шаблон доступності викладача. weekday 0=Пн..6=Нд; start_min/
    end_min — хвилини від опівночі у ЛОКАЛЬНІЙ таймзоні викладача."""
    __tablename__ = "teacher_availability"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    teacher_user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    weekday: Mapped[int] = mapped_column(Integer, nullable=False)
    start_min: Mapped[int] = mapped_column(Integer, nullable=False)
    end_min: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class TeacherClosedDate(Base):
    """Конкретна закрита дата викладача (відпустка/вихідний)."""
    __tablename__ = "teacher_closed_dates"
    __table_args__ = (UniqueConstraint("tenant_id", "teacher_user_id", "day"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    teacher_user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    day: Mapped[date] = mapped_column(Date, nullable=False)


class Lesson(Base):
    """Заброньований урок. Час зберігається в UTC; показ — у локальному часі
    кожного користувача (users.timezone)."""
    __tablename__ = "lessons"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    teacher_user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    student_user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    starts_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    duration_min: Mapped[int] = mapped_column(Integer, nullable=False, default=60, server_default="60")
    # 'booked' | 'cancelled' | 'completed'
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="booked", server_default="booked"
    )
    reminder_24_sent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    reminder_1_sent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    digest_sent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Homework(Base):
    """Домашнє завдання (M13): пройти колоду до дедлайну. status: assigned /
    in_progress / done / overdue. Одне ДЗ на (deck_id, user_id)."""
    __tablename__ = "homework"
    __table_args__ = (UniqueConstraint("deck_id", "user_id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    deck_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("decks.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    due_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="assigned", server_default="assigned"
    )
    reminder_sent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


# ─── Режим школи (M14) ───────────────────────────────────────────────────────

class Group(Base):
    """Група учнів у школі-тенанті, привʼязана до викладача."""
    __tablename__ = "groups"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    teacher_user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class GroupMember(Base):
    __tablename__ = "group_members"
    __table_args__ = (UniqueConstraint("group_id", "user_id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    group_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("groups.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
