"""Referral system: запроси друга — обом +30 днів Pro.

Код юзера — base36(telegram_id), padded до ≥6 символів. Це детерміновано
(один юзер = один код), не вгадується (telegram_id ховається), і не
конфліктує з іншими.
"""
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update

from . import analytics
from .db import SessionLocal
from .models import User

logger = logging.getLogger(__name__)

REFERRAL_BONUS_DAYS = 10
TRIAL_DAYS = 7  # дзеркалить логіку у user_service.is_trial — стек бонусу на trial
_BASE36 = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def generate_code(telegram_id: int) -> str:
    """Детерміністичний унікальний код з telegram_id."""
    n = abs(int(telegram_id))
    out = ""
    while n:
        n, r = divmod(n, 36)
        out = _BASE36[r] + out
    return (out or "0").zfill(6)


async def ensure_code(user: User) -> str:
    """Повертає код юзера — створює якщо ще немає."""
    if user.referral_code:
        return user.referral_code
    code = generate_code(user.telegram_id)
    async with SessionLocal() as session:
        await session.execute(
            update(User).where(User.id == user.id).values(referral_code=code)
        )
        await session.commit()
    user.referral_code = code
    return code


async def find_referrer(code: str) -> User | None:
    code = (code or "").strip().upper()
    if not code:
        return None
    async with SessionLocal() as session:
        return (await session.execute(
            select(User).where(User.referral_code == code)
        )).scalar_one_or_none()


async def apply_referral(invitee_id: int, referrer_code: str) -> tuple[User, User] | None:
    """Реалізує бонус для обох сторін, якщо умови виконуються.

    Returns (referrer, invitee) при успіху, інакше None.
    """
    async with SessionLocal() as session:
        invitee = (await session.execute(
            select(User).where(User.id == invitee_id)
        )).scalar_one_or_none()
        if not invitee:
            return None
        # Запрошуваний уже має referrer'а — реферал одноразовий
        if invitee.referred_by is not None:
            return None

        referrer = (await session.execute(
            select(User).where(User.referral_code == (referrer_code or "").strip().upper())
        )).scalar_one_or_none()
        if not referrer:
            return None
        # Не дозволяємо self-referral
        if referrer.id == invitee.id:
            return None

        invitee.referred_by = referrer.id
        # +10 днів Pro обом — стекаємо на існуюче:
        # - якщо юзер уже Pro з активним plan_expires_at → продовжуємо від нього
        # - інакше базою береться кінець trial-періоду (created_at + 7 днів),
        #   або зараз — якщо trial уже минув. Так новий запрошений отримує
        #   trial 7 днів + 10 бонусних = 17 днів реального free-Pro.
        now = datetime.now(timezone.utc)
        for u in (invitee, referrer):
            if u.plan == "pro" and u.plan_expires_at and u.plan_expires_at > now:
                base = u.plan_expires_at
            else:
                trial_end = (u.created_at + timedelta(days=TRIAL_DAYS)) if u.created_at else now
                base = max(trial_end, now)
            u.plan = "pro"
            u.plan_expires_at = base + timedelta(days=REFERRAL_BONUS_DAYS)
            u.subscription_status = "active"
        referrer.referrals_count = (referrer.referrals_count or 0) + 1

        await session.commit()
        await session.refresh(invitee)
        await session.refresh(referrer)

    analytics.capture(invitee.telegram_id, "referral_signup", {
        "referrer_telegram_id": referrer.telegram_id,
        "bonus_days": REFERRAL_BONUS_DAYS,
    })
    analytics.capture(referrer.telegram_id, "referral_completed", {
        "invitee_telegram_id": invitee.telegram_id,
        "bonus_days": REFERRAL_BONUS_DAYS,
        "total_referrals": referrer.referrals_count,
    })
    analytics.identify(invitee.telegram_id, {"plan": "pro"})
    analytics.identify(referrer.telegram_id, {"plan": "pro"})

    logger.info(
        f"Referral applied: {referrer.telegram_id} → {invitee.telegram_id}, "
        f"both got +{REFERRAL_BONUS_DAYS}d Pro"
    )
    return (referrer, invitee)
