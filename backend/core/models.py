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

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
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
