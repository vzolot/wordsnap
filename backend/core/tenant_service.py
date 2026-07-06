"""Сервіс тенантів (white-label мультитенантність).

Резолв тенанта, конфіг бренду, синхронізація базового тенанта (id=1) з env,
парсинг bot_id з токена. bot_token — СЕКРЕТ: ніколи не логуємо і не віддаємо
назовні (в API/Sentry).
"""
from __future__ import annotations

import logging
import os

from sqlalchemy import select, update

from .db import SessionLocal
from .models import Tenant

logger = logging.getLogger(__name__)

DEFAULT_TENANT_ID = 1


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


async def create_tenant(
    slug: str,
    display_name: str,
    bot_token: str,
    owner_telegram_id: int | None = None,
    logo_url: str | None = None,
    color_primary: str | None = None,
    color_accent: str | None = None,
    plan: str = "trial",
) -> Tenant:
    """Створює новий тенант (викликає admin-скрипт add_tenant.py). bot_id
    парситься з токена. billing_ui_enabled лишається false (white-label)."""
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
