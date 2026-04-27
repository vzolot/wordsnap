"""
Сервіс роботи з юзерами в БД.
"""
import logging
from datetime import date
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
    """
    Отримує юзера або створює нового.
    Скидає денний лічильник якщо новий день.
    """
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
                target_lang="en",
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


async def can_add_word(user: User) -> tuple[bool, str]:
    """
    Перевіряє чи може юзер додати ще одне слово.
    Логіка:
    - Pro юзер → 100/день
    - Перші 7 днів від реєстрації (trial) → 100/день, як Pro
    - Free після trial → 10/день
    """
    from datetime import datetime, timezone, timedelta
    
    # Pro юзер з активною підпискою
    if user.plan == "pro":
        if user.plan_expires_at and user.plan_expires_at > datetime.now(timezone.utc):
            if user.words_added_today >= 100:
                return False, "Ти досяг ліміту 100 слів/день навіть для Pro 😱"
            return True, ""
    
    # Перевірка trial: перші 7 днів від реєстрації
    trial_active = False
    if user.created_at:
        trial_end = user.created_at + timedelta(days=7)
        if datetime.now(timezone.utc) < trial_end:
            trial_active = True
    
    if trial_active:
        # Trial = повний доступ, як Pro
        if user.words_added_today >= 100:
            return False, "Ти досяг ліміту 100 слів/день. Завтра можна знову!"
        return True, ""
    
    # Free після trial
    if user.words_added_today >= 10:
        return False, (
            "⛔️ Денний ліміт 10 слів вичерпано.\n\n"
            "💎 Купи <b>Pro</b> за $1.49/міс і отримай:\n"
            "• 100 слів на день\n"
            "• Тематичні набори (Travel, Business, Songs)\n"
            "• Розширена статистика\n\n"
            "Команда /premium для оформлення"
        )
    
    return True, ""


async def get_user_status(user: User) -> dict:
    """
    Повертає поточний статус юзера для відображення.
    Returns: {plan, is_trial, trial_days_left, daily_limit, used_today}
    """
    from datetime import datetime, timezone, timedelta
    
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
        plan_label = "PRO"
    elif is_trial:
        daily_limit = 100
        plan_label = f"TRIAL ({trial_days_left} дн)"
    else:
        daily_limit = 10
        plan_label = "FREE"
    
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