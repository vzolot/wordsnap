"""
Сервіс роботи з юзерами в БД.
"""
import logging
from datetime import date, datetime, timezone, timedelta
from sqlalchemy import select

from .models import User
from .db import SessionLocal

logger = logging.getLogger(__name__)


async def get_or_create_user(
    telegram_id: int,
    username: str | None = None,
    first_name: str | None = None,
    last_name: str | None = None,
    language_code: str | None = None,
) -> User:
    """Отримує юзера або створює нового. Скидає денний лічильник якщо новий день."""
    async with SessionLocal() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        user = result.scalar_one_or_none()
        
        if user is None:
            user = User(
                telegram_id=telegram_id,
                username=username,
                first_name=first_name,
                last_name=last_name,
                language_code=language_code,
                native_lang="uk",
                target_lang=None,
                plan="free",
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            logger.info(f"Created new user: telegram_id={telegram_id}")
        else:
            user.username = username or user.username
            user.first_name = first_name or user.first_name
            
            today = date.today()
            if user.last_reset_date != today:
                user.words_added_today = 0
                user.last_reset_date = today
                logger.info(f"Reset daily counter for user {telegram_id}")
            
            await session.commit()
            await session.refresh(user)
        
        return user


async def can_add_word(user: User, lang: str | None = None) -> tuple[bool, str]:
    """
    Логіка лімітів:
    - PRO активна: 100 слів/день
    - TRIAL (перші 7 днів): 10 слів/день
    - Після trial: блокування, потрібен Pro (XP дає знижки на Pro у tier-системі).
    """
    from .bot_i18n import t as bt
    msg_lang = lang or user.native_lang or "uk"

    if user.plan == "pro":
        if user.plan_expires_at and user.plan_expires_at > datetime.now(timezone.utc):
            if user.words_added_today >= 100:
                return False, bt("limit.pro", msg_lang)
            return True, ""

    trial_active = False
    if user.created_at:
        trial_end = user.created_at + timedelta(days=7)
        if datetime.now(timezone.utc) < trial_end:
            trial_active = True

    if trial_active:
        if user.words_added_today >= 10:
            return False, bt("limit.trial", msg_lang)
        return True, ""

    # Trial скінчився — тільки Pro
    return False, bt("limit.expired", msg_lang, xp=user.total_xp or 0)


async def get_user_status(user: User, lang: str | None = None) -> dict:
    """Повертає поточний статус юзера для відображення."""
    from .bot_i18n import t as bt
    msg_lang = lang or user.native_lang or "uk"

    is_trial = False
    trial_days_left = 0

    if user.plan != "pro" and user.created_at:
        trial_end = user.created_at + timedelta(days=7)
        now = datetime.now(timezone.utc)
        if now < trial_end:
            is_trial = True
            trial_days_left = (trial_end - now).days + 1

    if user.plan == "pro":
        daily_limit = 100
        plan_label = bt("stats.plan.pro", msg_lang)
    elif is_trial:
        daily_limit = 10
        plan_label = bt("stats.plan.trial", msg_lang, days=trial_days_left)
    else:
        daily_limit = 0  # post-trial: блок, тільки Pro
        plan_label = bt("stats.plan.free", msg_lang)

    return {
        "plan": user.plan,
        "plan_label": plan_label,
        "is_trial": is_trial,
        "trial_days_left": trial_days_left,
        "daily_limit": daily_limit,
        "used_today": user.words_added_today,
    }


async def increment_word_counter(telegram_id: int) -> None:
    """Інкрементує лічильник слів за сьогодні"""
    async with SessionLocal() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        user = result.scalar_one_or_none()
        if user:
            user.words_added_today += 1
            user.total_words += 1
            await session.commit()


# === Day 7: Pro subscription with recurring ===

async def activate_pro_subscription(
    telegram_id: int,
    rec_token: str | None = None,
    duration_days: int = 30,
) -> User | None:
    """
    Активує Pro підписку для юзера.
    Викликається після успішного платежу WayForPay.
    
    Args:
        telegram_id: Telegram ID юзера
        rec_token: Токен картки для майбутніх auto-charge (опціонально)
        duration_days: На скільки днів активувати
    """
    async with SessionLocal() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            logger.error(f"User {telegram_id} not found for Pro activation")
            return None
        
        now = datetime.now(timezone.utc)
        
        # Якщо вже Pro і підписка не закінчилась — додаємо до існуючої дати
        if user.plan == "pro" and user.plan_expires_at and user.plan_expires_at > now:
            new_expires = user.plan_expires_at + timedelta(days=duration_days)
        else:
            new_expires = now + timedelta(days=duration_days)
        
        user.plan = "pro"
        user.plan_expires_at = new_expires
        user.last_payment_date = now
        user.subscription_status = "active"
        
        # Списуємо за день до закінчення
        user.next_charge_date = new_expires - timedelta(days=1)
        
        # Зберігаємо токен якщо отримали — це для майбутніх auto-charge
        if rec_token:
            user.payment_rec_token = rec_token
            user.auto_renew = True
            logger.info(f"Saved recToken for user {telegram_id}, auto-renew enabled")
        
        await session.commit()
        await session.refresh(user)
        
        logger.info(
            f"Activated Pro for user {telegram_id}, "
            f"expires at {user.plan_expires_at}, auto_renew={user.auto_renew}"
        )
        return user


async def cancel_subscription(telegram_id: int) -> User | None:
    """
    Скасовує auto-renew. Pro залишається активним до plan_expires_at.
    """
    async with SessionLocal() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            return None
        
        user.auto_renew = False
        user.subscription_status = "cancelled"
        user.next_charge_date = None
        
        await session.commit()
        await session.refresh(user)
        
        logger.info(f"Cancelled auto-renew for user {telegram_id}")
        return user


async def update_user_languages(
    telegram_id: int,
    native_lang: str,
    target_lang: str,
) -> None:
    """Зберігає вибір рідної та цільової мови."""
    async with SessionLocal() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        user = result.scalar_one_or_none()
        if user:
            user.native_lang = native_lang
            user.target_lang = target_lang
            await session.commit()
            logger.info(f"Updated languages for user {telegram_id}: {native_lang} → {target_lang}")


async def expire_subscription(telegram_id: int) -> User | None:
    """
    Деактивує Pro коли підписка закінчилась і автопродовження не вдалось.
    """
    async with SessionLocal() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            return None
        
        user.plan = "free"
        user.subscription_status = "expired"
        user.auto_renew = False
        user.next_charge_date = None
        
        await session.commit()
        await session.refresh(user)
        
        logger.info(f"Expired subscription for user {telegram_id}")
        return user