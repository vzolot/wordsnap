"""Сервіс тенантів (white-label мультитенантність).

Резолв тенанта, конфіг бренду, синхронізація базового тенанта (id=1) з env,
парсинг bot_id з токена. bot_token — СЕКРЕТ: ніколи не логуємо і не віддаємо
назовні (в API/Sentry).
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from .db import SessionLocal
from .models import AiSnapUsage, Tenant

logger = logging.getLogger(__name__)

DEFAULT_TENANT_ID = 1


def _current_month() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def parse_bot_id(token: str) -> int | None:
    """bot_id = числова частина токена до ':'. Токен формату
    `<bot_id>:<hash>`. Повертає None якщо токен нерозбірливий."""
    if not token or ":" not in token:
        return None
    head = token.split(":", 1)[0].strip()
    try:
        return int(head)
    except ValueError:
        return None


async def sync_default_tenant() -> Tenant | None:
    """Гарантує, що тенант id=1 має bot_token і bot_id з env TELEGRAM_BOT_TOKEN.
    Викликається на старті — щоб резолв initData основного бота (M3) працював,
    а мультибот-полінг (M2) підхопив і головного бота теж."""
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    bot_id = parse_bot_id(token) if token else None
    async with SessionLocal() as session:
        tenant = (await session.execute(
            select(Tenant).where(Tenant.id == DEFAULT_TENANT_ID)
        )).scalar_one_or_none()
        if tenant is None:
            logger.warning("sync_default_tenant: тенант id=1 відсутній (міграція не пройшла?)")
            return None
        changed = False
        if token and tenant.bot_token != token:
            tenant.bot_token = token
            changed = True
        if bot_id and tenant.bot_id != bot_id:
            tenant.bot_id = bot_id
            changed = True
        if changed:
            await session.commit()
            await session.refresh(tenant)
            logger.info("sync_default_tenant: оновлено bot_token/bot_id тенанта 1")
        return tenant


async def get_active_tenants() -> list[Tenant]:
    """Усі тенанти, чиї боти треба піднімати (мають bot_token і plan != paused)."""
    async with SessionLocal() as session:
        rows = (await session.execute(
            select(Tenant).where(
                Tenant.bot_token.isnot(None),
                Tenant.plan != "paused",
            ).order_by(Tenant.id)
        )).scalars().all()
        return list(rows)


async def get_tenant_by_id(tenant_id: int) -> Tenant | None:
    async with SessionLocal() as session:
        return (await session.execute(
            select(Tenant).where(Tenant.id == tenant_id)
        )).scalar_one_or_none()


async def get_tenant_by_bot_id(bot_id: int) -> Tenant | None:
    """Резолв тенанта з bot_id (витягнутого з initData на бекенді)."""
    async with SessionLocal() as session:
        return (await session.execute(
            select(Tenant).where(Tenant.bot_id == bot_id)
        )).scalar_one_or_none()


async def get_tenant_by_slug(slug: str) -> Tenant | None:
    async with SessionLocal() as session:
        return (await session.execute(
            select(Tenant).where(Tenant.slug == slug)
        )).scalar_one_or_none()


async def get_ai_snap_count(tenant_id: int, month: str | None = None) -> int:
    """Скільки AI-снапів витрачено тенантом за місяць (дефолт — поточний)."""
    month = month or _current_month()
    async with SessionLocal() as session:
        row = (await session.execute(
            select(AiSnapUsage.count).where(
                AiSnapUsage.tenant_id == tenant_id,
                AiSnapUsage.month == month,
            )
        )).scalar_one_or_none()
        return int(row or 0)


async def ai_snap_available(tenant: Tenant) -> bool:
    """True якщо тенант ще може робити AI-снап цього місяця. ліміт NULL =
    без обмежень (тенант id=1). Інакше — count < limit."""
    if tenant.ai_snap_monthly_limit is None:
        return True
    used = await get_ai_snap_count(tenant.id)
    return used < tenant.ai_snap_monthly_limit


async def incr_ai_snap_usage(tenant_id: int, n: int = 1) -> int:
    """Атомарно інкрементує лічильник AI-снапів тенанта за поточний місяць
    (upsert). Повертає нове значення count. Викликати ПІСЛЯ реального виклику
    OpenAI vision (фото/войс снап)."""
    month = _current_month()
    async with SessionLocal() as session:
        stmt = (
            pg_insert(AiSnapUsage)
            .values(tenant_id=tenant_id, month=month, count=n)
            .on_conflict_do_update(
                index_elements=["tenant_id", "month"],
                set_={"count": AiSnapUsage.count + n},
            )
            .returning(AiSnapUsage.count)
        )
        new_count = (await session.execute(stmt)).scalar_one()
        await session.commit()
        return int(new_count)


def config_payload(tenant: Tenant, ai_available: bool) -> dict:
    """Публічний конфіг бренду для Mini App. bot_token НЕ включаємо (секрет)."""
    return {
        "tenant_id": tenant.id,
        "slug": tenant.slug,
        "display_name": tenant.display_name,
        "logo_url": tenant.logo_url,
        "color_primary": tenant.color_primary,
        "color_accent": tenant.color_accent,
        "ai_snap_available": ai_available,
        "billing_ui_enabled": tenant.billing_ui_enabled,
        # @username бота (публічний) — для кнопки «поділитися ботом» у викладача.
        "bot_username": tenant.bot_username,
        # Режим школи — щоб нижня навігація показувала вкладку «Школа».
        "is_school": tenant.is_school,
    }


TENANT_SUB_DAYS = 30


async def activate_tenant_subscription(
    tenant_id: int, rec_token: str | None = None, order_ref: str | None = None,
    days: int = TENANT_SUB_DAYS,
) -> Tenant | None:
    """Активує/продовжує підписку викладача після успішної оплати. Продовжує від
    поточного sub_expires_at (якщо ще активна), інакше від тепер. Зберігає токен
    картки для автосписання, знімає паузу з бота."""
    from datetime import timedelta
    async with SessionLocal() as session:
        tenant = (await session.execute(
            select(Tenant).where(Tenant.id == tenant_id)
        )).scalar_one_or_none()
        if tenant is None:
            return None
        now = datetime.now(timezone.utc)
        base = tenant.sub_expires_at if (tenant.sub_expires_at and tenant.sub_expires_at > now) else now
        tenant.sub_expires_at = base + timedelta(days=days)
        tenant.sub_status = "active"
        tenant.sub_last_payment_at = now
        tenant.sub_reminder_sent_at = None
        tenant.sub_next_charge_at = tenant.sub_expires_at  # автосписання в день закінчення
        if order_ref and not tenant.sub_order_ref:
            tenant.sub_order_ref = order_ref
        if rec_token:
            tenant.sub_rec_token = rec_token
            tenant.sub_auto_renew = True
        if tenant.plan == "paused":
            tenant.plan = "active"  # оплата знімає паузу (бот підніметься на redeploy)
        await session.commit()
        await session.refresh(tenant)
        logger.info("activate_tenant_subscription: tenant %s → %s", tenant_id, tenant.sub_expires_at)
        return tenant


def tenant_billing_status(tenant: Tenant) -> dict:
    """Публічний статус підписки для UI викладача (без rec_token)."""
    now = datetime.now(timezone.utc)
    exp = tenant.sub_expires_at
    active = bool(tenant.sub_status == "active" and exp and exp > now)
    days_left = max(0, (exp - now).days) if exp and exp > now else 0
    return {
        "status": tenant.sub_status,
        "active": active,
        "price_usd": float(tenant.sub_price_usd or 19),
        "expires_at": exp.isoformat() if exp else None,
        "days_left": days_left,
        "auto_renew": bool(tenant.sub_auto_renew),
    }


async def set_tenant_bot_username(tenant_id: int, username: str | None) -> None:
    """Зберігає @username бота тенанта (без '@'), якщо змінився. Викликається
    на старті після getMe. username публічний — не секрет."""
    if not username:
        return
    async with SessionLocal() as session:
        tenant = (await session.execute(
            select(Tenant).where(Tenant.id == tenant_id)
        )).scalar_one_or_none()
        if tenant is not None and tenant.bot_username != username:
            tenant.bot_username = username
            await session.commit()
            logger.info("set_tenant_bot_username: tenant %s → @%s", tenant_id, username)


async def create_tenant(
    slug: str,
    display_name: str,
    bot_token: str,
    owner_telegram_id: int | None = None,
    logo_url: str | None = None,
    color_primary: str | None = None,
    color_accent: str | None = None,
    plan: str = "trial",
    is_school: bool = False,
) -> Tenant:
    """Створює новий тенант (викликає admin-скрипт add_tenant.py). bot_id
    парситься з токена. billing_ui_enabled лишається false (white-label).
    is_school=True → режим школи (кілька викладачів + групи, вкладка «Школа»)."""
    bot_id = parse_bot_id(bot_token)
    if bot_id is None:
        raise ValueError(f"Не вдалося витягти bot_id з токена (формат <id>:<hash>)")
    async with SessionLocal() as session:
        tenant = Tenant(
            slug=slug,
            display_name=display_name,
            bot_token=bot_token,
            bot_id=bot_id,
            owner_telegram_id=owner_telegram_id,
            logo_url=logo_url,
            plan=plan,
            is_school=is_school,
        )
        if color_primary:
            tenant.color_primary = color_primary
        if color_accent:
            tenant.color_accent = color_accent
        session.add(tenant)
        await session.commit()
        await session.refresh(tenant)
        logger.info("create_tenant: %s (id=%s, bot_id=%s)", slug, tenant.id, bot_id)
        return tenant
