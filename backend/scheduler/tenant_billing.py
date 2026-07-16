"""Оплата сервісу тенантами (викладачами): $19/міс.

Раз на годину:
1. Автопродовження — якщо настав sub_next_charge_at і є збережений токен картки,
   списуємо $19 через charge_tenant_recurring і продовжуємо на 30 днів.
2. Помилка списання → sub_status='past_due' + нагадування власнику.
3. Нагадування за REMINDER_DAYS до кінця (для тих, хто без автопродовження).
4. Автопауза — прострочено понад GRACE_DAYS → tenant.plan='paused'
   (бот перестає підніматись при наступному redeploy) + сповіщення.

Тенант 1 (WordSnap) не має сервіс-плати — пропускаємо.
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

from aiogram import Bot
from sqlalchemy import select

from core.db import SessionLocal
from core.models import Tenant
from core.telegram_send import send_message
from core.tenant_service import DEFAULT_TENANT_ID, activate_tenant_subscription
from core.wayforpay_client import charge_tenant_recurring

logger = logging.getLogger(__name__)

GRACE_DAYS = 3
REMINDER_DAYS = 3
CHECK_INTERVAL_SEC = 3600  # щогодини


async def _set(tenant_id: int, **fields) -> None:
    async with SessionLocal() as s:
        t = (await s.execute(select(Tenant).where(Tenant.id == tenant_id))).scalar_one_or_none()
        if not t:
            return
        for k, v in fields.items():
            setattr(t, k, v)
        await s.commit()


async def _run_once() -> None:
    now = datetime.now(timezone.utc)
    async with SessionLocal() as session:
        tenants = (await session.execute(
            select(Tenant).where(Tenant.id != DEFAULT_TENANT_ID)
        )).scalars().all()

    from core.tenant_service import compute_tenant_price
    for t in tenants:
        try:
            price = await compute_tenant_price(t)

            # 1) Автопродовження.
            if (t.sub_auto_renew and t.sub_rec_token and t.sub_next_charge_at
                    and t.sub_next_charge_at <= now and t.sub_status in ("active", "past_due")):
                res = await charge_tenant_recurring(t.sub_rec_token, t.id, price)
                if res.get("success"):
                    await activate_tenant_subscription(t.id, order_ref=res["order_reference"], days=30)
                    logger.info("tenant_billing: auto-renewed tenant %s", t.id)
                else:
                    await _set(t.id, sub_status="past_due")
                    if t.owner_telegram_id:
                        await send_message(
                            t.owner_telegram_id,
                            f"⚠️ Не вдалось автоматично списати оплату за сервіс (${price:g}). "
                            "Перевір картку і оплати в кабінеті: Викладач → Підписка.",
                            tenant_id=t.id,
                        )
                    logger.warning("tenant_billing: charge failed for tenant %s (%s)",
                                   t.id, res.get("reason"))
                continue

            # 2) Нагадування за кілька днів до кінця (лише без автопродовження).
            if (t.sub_status == "active" and not t.sub_auto_renew and t.sub_expires_at
                    and now <= t.sub_expires_at <= now + timedelta(days=REMINDER_DAYS)
                    and t.sub_reminder_sent_at is None and t.owner_telegram_id):
                await send_message(
                    t.owner_telegram_id,
                    f"🔔 Підписка на сервіс закінчується {t.sub_expires_at.strftime('%d.%m')}. "
                    "Продовж у кабінеті: Викладач → Підписка.",
                    tenant_id=t.id,
                )
                await _set(t.id, sub_reminder_sent_at=now)

            # 3) Автопауза при простроченні понад grace (тільки для тих, хто вже платив).
            if (t.sub_expires_at and t.sub_status in ("active", "past_due")
                    and t.sub_expires_at + timedelta(days=GRACE_DAYS) < now
                    and t.plan != "paused"):
                await _set(t.id, plan="paused", sub_status="past_due")
                logger.info("tenant_billing: paused tenant %s (unpaid)", t.id)
                if t.owner_telegram_id:
                    await send_message(
                        t.owner_telegram_id,
                        "⏸ Сервіс призупинено через несплату. Оплати в кабінеті "
                        "(Викладач → Підписка), щоб відновити.",
                        tenant_id=t.id,
                    )
        except Exception as e:
            logger.warning("tenant_billing: tenant %s failed: %s", t.id, e)


async def tenant_billing_loop(bot: Bot) -> None:
    logger.info("💳 Tenant-billing scheduler started (hourly)")
    while True:
        try:
            await _run_once()
        except Exception as e:
            logger.error("tenant_billing loop error: %s", e, exc_info=True)
        await asyncio.sleep(CHECK_INTERVAL_SEC)
