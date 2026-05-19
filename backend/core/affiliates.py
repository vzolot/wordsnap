"""Affiliate / influencer revenue-share program.

Юзер тапає `t.me/WordSnapBot?start=aff_<slug>` (або `aff_<slug>` через
landing-bridge), бот ставить йому `users.affiliate_slug = '<slug>'`,
`users.affiliate_at = now()`. Коли цей юзер платить підписку, payment
webhook викликає `record_payment_share()` що:

  1. Дивиться `users.affiliate_slug` + `affiliate_at`.
  2. Перевіряє чи payment-час у вікні `[affiliate_at, affiliate_at + duration_days]`.
  3. Якщо так - вставляє row у `affiliate_revenue` зі сумою share
     (`payment_amount * rev_share_pct / 100`).

Це source-of-truth для виплат інфлюенсерам (Rue, etc.) і для адмін-stats.

Виплати самі не автоматизовані — це manual once-per-month flow.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select, func
from sqlalchemy import update as sa_update

from .db import SessionLocal
from .models import Affiliate, AffiliateRevenue, PaymentHistory, User

logger = logging.getLogger(__name__)

# Допустимий формат slug у URL: lowercase, [a-z0-9_-], 2-40 символів.
# Telegram /start payload limit — 64 chars, після префіксу `aff_` лишається 60.
_SLUG_RE = re.compile(r"^[a-z0-9_-]{2,40}$")


def is_valid_slug(slug: str) -> bool:
    return bool(_SLUG_RE.match(slug))


def parse_affiliate_payload(payload: str) -> str | None:
    """`aff_rue` → `rue`. Інакше None."""
    if not payload or not payload.startswith("aff_"):
        return None
    slug = payload[4:].strip().lower()
    return slug if is_valid_slug(slug) else None


def affiliate_deeplink(slug: str, *, bot_username: str = "WordSnapBot") -> str:
    """Канонічна URL'а для cap'іту інфлюенсеру. Direct mini-app universal
    link, як ad-flow — start_param приходить у SPA, але атрибуція все
    одно зберігається на бекенді через POST /api/onboarding/save_survey
    (як для igads-cohort) АБО через /start payload якщо юзер пройде через
    bot-chat-flow. Подвійне покриття."""
    return f"https://t.me/{bot_username}/app?startapp=aff_{slug}"


async def get_affiliate(slug: str) -> Affiliate | None:
    async with SessionLocal() as session:
        return (await session.execute(
            select(Affiliate).where(Affiliate.slug == slug)
        )).scalar_one_or_none()


async def create_affiliate(
    slug: str,
    name: str,
    *,
    rev_share_pct: float = 20.0,
    duration_days: int = 180,
    notes: str | None = None,
) -> Affiliate:
    """Створити/підняти Affiliate. Idempotent — повторний виклик update'не
    rev_share/duration якщо змінились."""
    if not is_valid_slug(slug):
        raise ValueError(f"Invalid slug: {slug!r}. Must be {_SLUG_RE.pattern}.")
    async with SessionLocal() as session:
        existing = (await session.execute(
            select(Affiliate).where(Affiliate.slug == slug)
        )).scalar_one_or_none()
        if existing:
            await session.execute(
                sa_update(Affiliate).where(Affiliate.slug == slug).values(
                    name=name,
                    rev_share_pct=rev_share_pct,
                    duration_days=duration_days,
                    notes=notes,
                )
            )
            await session.commit()
            await session.refresh(existing)
            return existing
        aff = Affiliate(
            slug=slug,
            name=name,
            rev_share_pct=rev_share_pct,
            duration_days=duration_days,
            notes=notes,
        )
        session.add(aff)
        await session.commit()
        await session.refresh(aff)
        return aff


async def apply_affiliate_to_user(user_id: int, slug: str) -> bool:
    """First-touch: якщо юзер ще не має affiliate_slug, ставимо. Інакше
    залишаємо. Повертає True якщо встановили вперше."""
    async with SessionLocal() as session:
        user = (await session.execute(
            select(User).where(User.id == user_id)
        )).scalar_one_or_none()
        if user is None:
            return False
        if user.affiliate_slug:
            return False  # first-touch — не перетираємо
        # Перевіряємо що такий affiliate існує (без FK violation)
        aff = (await session.execute(
            select(Affiliate).where(Affiliate.slug == slug)
        )).scalar_one_or_none()
        if aff is None:
            logger.warning(
                "affiliate slug %r не існує у БД — юзеру %s не призначено",
                slug, user_id,
            )
            return False
        await session.execute(
            sa_update(User).where(User.id == user_id).values(
                affiliate_slug=slug,
                affiliate_at=datetime.now(timezone.utc),
            )
        )
        await session.commit()
        logger.info("affiliate %r applied to user %s", slug, user_id)
        return True


async def record_payment_share(
    *,
    user_id: int,
    payment_id: int,
    payment_amount: float,
    payment_currency: str = "USD",
    payment_at: datetime | None = None,
) -> AffiliateRevenue | None:
    """Викликати з payment-webhook'а одразу після успішної оплати.
    Перевіряє правомочність (slug існує, у window'і), фіксує share-row.

    Idempotent по `payment_id` — якщо row уже існує, no-op."""
    payment_at = payment_at or datetime.now(timezone.utc)
    async with SessionLocal() as session:
        user = (await session.execute(
            select(User).where(User.id == user_id)
        )).scalar_one_or_none()
        if not user or not user.affiliate_slug or not user.affiliate_at:
            return None
        aff = (await session.execute(
            select(Affiliate).where(Affiliate.slug == user.affiliate_slug)
        )).scalar_one_or_none()
        if aff is None:
            logger.warning(
                "user %s has affiliate_slug=%r but affiliate row gone — skip share",
                user_id, user.affiliate_slug,
            )
            return None
        window_end = user.affiliate_at + timedelta(days=int(aff.duration_days))
        if payment_at > window_end:
            logger.info(
                "user %s payment %s outside affiliate window (%s > %s), skip",
                user_id, payment_id, payment_at, window_end,
            )
            return None
        # Idempotency
        existing = (await session.execute(
            select(AffiliateRevenue).where(AffiliateRevenue.payment_id == payment_id)
        )).scalar_one_or_none()
        if existing:
            return existing
        share = round(float(payment_amount) * float(aff.rev_share_pct) / 100.0, 2)
        row = AffiliateRevenue(
            affiliate_slug=aff.slug,
            user_id=user_id,
            payment_id=payment_id,
            payment_amount=payment_amount,
            payment_currency=payment_currency,
            rev_share_pct=float(aff.rev_share_pct),
            share_amount=share,
            payment_at=payment_at,
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        logger.info(
            "affiliate share recorded: %s gets $%.2f from user %s payment $%.2f",
            aff.slug, share, user_id, payment_amount,
        )
        return row


# --- Stats (use this from admin command) ----------------------------------


async def get_affiliate_stats(slug: str, *, days: int | None = None) -> dict[str, Any]:
    """Aggregate stats для slug за вікно `days` від зараз, або all-time
    якщо days=None."""
    async with SessionLocal() as session:
        aff = (await session.execute(
            select(Affiliate).where(Affiliate.slug == slug)
        )).scalar_one_or_none()
        if aff is None:
            return {"error": f"affiliate {slug!r} not found"}

        rev_q = select(
            func.count(AffiliateRevenue.id).label("payments"),
            func.coalesce(func.sum(AffiliateRevenue.payment_amount), 0).label("gross"),
            func.coalesce(func.sum(AffiliateRevenue.share_amount), 0).label("share"),
            func.count(func.distinct(AffiliateRevenue.user_id)).label("paying_users"),
        ).where(AffiliateRevenue.affiliate_slug == slug)
        if days is not None:
            cutoff = datetime.now(timezone.utc) - timedelta(days=days)
            rev_q = rev_q.where(AffiliateRevenue.payment_at >= cutoff)
        rev = (await session.execute(rev_q)).one()

        users_q = select(func.count(User.id)).where(User.affiliate_slug == slug)
        if days is not None:
            cutoff = datetime.now(timezone.utc) - timedelta(days=days)
            users_q = users_q.where(User.affiliate_at >= cutoff)
        total_users = (await session.execute(users_q)).scalar() or 0

        return {
            "slug": aff.slug,
            "name": aff.name,
            "rev_share_pct": float(aff.rev_share_pct),
            "duration_days": aff.duration_days,
            "window_days": days,
            "users_acquired": int(total_users),
            "paying_users": int(rev.paying_users or 0),
            "payments_count": int(rev.payments or 0),
            "gross_amount": float(rev.gross or 0),
            "share_owed": float(rev.share or 0),
        }


async def list_affiliates() -> list[Affiliate]:
    async with SessionLocal() as session:
        return list((await session.execute(
            select(Affiliate).order_by(Affiliate.created_at.desc())
        )).scalars().all())
