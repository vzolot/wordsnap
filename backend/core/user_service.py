"""
Сервіс роботи з юзерами в БД.
"""
import logging
from datetime import date, datetime, timezone, timedelta
from sqlalchemy import select, func

from . import analytics
from .models import User, Word
from .db import SessionLocal

logger = logging.getLogger(__name__)

# Free post-trial: rolling-week «хвіст», щоб юзер не відвалився після trial
# на нулі. 3 додавання за останні 7 днів — мінімум щоб залишити денну
# звичку живою, але мало для повного активного користування без Pro.
FREE_WEEKLY_LIMIT = 3
FREE_WEEKLY_WINDOW_DAYS = 7


async def _count_adds_last_7d(session, user_id: int) -> int:
    """Скільки слів юзер додав у rolling 7-day window до зараз."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=FREE_WEEKLY_WINDOW_DAYS)
    n = (await session.execute(
        select(func.count(Word.id)).where(
            Word.user_id == user_id,
            Word.created_at >= cutoff,
        )
    )).scalar()
    return int(n or 0)


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
            from .referral import generate_code
            user = User(
                telegram_id=telegram_id,
                username=username,
                first_name=first_name,
                last_name=last_name,
                language_code=language_code,
                native_lang="uk",
                target_lang=None,
                plan="free",
                referral_code=generate_code(telegram_id),
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            logger.info(f"Created new user: telegram_id={telegram_id}")
            analytics.identify(telegram_id, {
                "username": username,
                "language_code": language_code,
                "plan": "free",
            })
            analytics.capture(telegram_id, "user_started", {
                "language_code": language_code,
            })
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
    - Після trial: 3 слова на rolling 7-day window («хвіст», не повний блок).
      Коли вичерпано — потрібен Pro (XP дає знижки на Pro у tier-системі).
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

    # Trial скінчився → free-tier rolling-week «хвіст»
    async with SessionLocal() as session:
        used_week = await _count_adds_last_7d(session, user.id)
    if used_week < FREE_WEEKLY_LIMIT:
        return True, ""
    return False, bt(
        "limit.free_weekly",
        msg_lang,
        used=used_week,
        limit=FREE_WEEKLY_LIMIT,
        xp=user.total_xp or 0,
    )


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

    is_free_post_trial = (user.plan != "pro") and (not is_trial)

    if user.plan == "pro":
        daily_limit = 100
        used = user.words_added_today
        plan_label = bt("stats.plan.pro", msg_lang)
    elif is_trial:
        daily_limit = 10
        used = user.words_added_today
        plan_label = bt("stats.plan.trial", msg_lang, days=trial_days_left)
    else:
        # Free post-trial: limit і used виражені у тижневих одиницях, але
        # повертаємо їх у тих самих полях `daily_limit`/`used_today` (frontend
        # бачить is_free_post_trial=True і знає що це тижневі цифри).
        daily_limit = FREE_WEEKLY_LIMIT
        async with SessionLocal() as session:
            used = await _count_adds_last_7d(session, user.id)
        plan_label = bt("stats.plan.free", msg_lang)

    return {
        "plan": user.plan,
        "plan_label": plan_label,
        "is_trial": is_trial,
        "trial_days_left": trial_days_left,
        "is_free_post_trial": is_free_post_trial,
        "daily_limit": daily_limit,
        "used_today": used,
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

        analytics.capture(telegram_id, "payment_succeeded", {
            "duration_days": duration_days,
            "auto_renew": user.auto_renew,
            "plan_expires_at": user.plan_expires_at.isoformat() if user.plan_expires_at else None,
        })
        analytics.identify(telegram_id, {"plan": "pro"})

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