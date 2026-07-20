"""Конверсійний «міст» після демо.

Проспект, який відкрив демо-тенант (Марта / Мовна школа) і отримав викладацький
демо-доступ (role=teacher/owner + demo_expires_at), за кілька хвилин отримує від
бренд-бота пітч із кнопкою на Instagram: «хочете такий застосунок під ваш бренд?».
Рівно один раз на проспекта (demo_pitch_sent). Реальний власник тенанта (Vova)
під фільтр не потрапляє — у нього demo_expires_at = NULL.
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

from aiogram import Bot
from sqlalchemy import select, update as sa_update

from core import analytics
from core.db import SessionLocal
from core.models import Tenant, User
from core.telegram_send import send_message

logger = logging.getLogger(__name__)

DELAY_MIN = 4  # надіслати ~через стільки хвилин після видачі демо-доступу
IG_URL = "https://instagram.com/vzolottop"

PITCH = (
    "🎓 <b>Це демо WordSnap</b>\n\n"
    "Ви щойно побачили справжній застосунок, зроблений під конкретного викладача — "
    "з колодами, інтервальними повтореннями, розкладом і статистикою.\n\n"
    "Хочете такий самий, але під <b>ваш бренд</b> — вашу назву, лого й кольори? "
    "Напишіть нам, і ми зберемо демо саме для вас за добу 👇"
)
MARKUP = {"inline_keyboard": [[{"text": "📸 Написати в Instagram", "url": IG_URL}]]}


async def _eligible(session) -> list[User]:
    now = datetime.now(timezone.utc)
    # grant_time = demo_expires_at - 3 дні; шлемо, коли від старту минуло ≥ DELAY_MIN.
    cutoff = now + timedelta(days=3) - timedelta(minutes=DELAY_MIN)
    return (await session.execute(
        select(User).join(Tenant, Tenant.id == User.tenant_id).where(
            Tenant.is_demo.is_(True),
            User.role.in_(("teacher", "owner")),
            User.demo_expires_at.is_not(None),
            User.demo_expires_at > now,       # ще в активному демо-вікні
            User.demo_expires_at <= cutoff,   # минуло ≥ DELAY_MIN від старту демо
            User.demo_pitch_sent.is_(False),
        )
    )).scalars().all()


async def check_and_send(bot: Bot) -> None:
    try:
        async with SessionLocal() as session:
            users = await _eligible(session)
        sent = 0
        for u in users:
            ok = await send_message(u.telegram_id, PITCH, reply_markup=MARKUP, tenant_id=u.tenant_id)
            # Позначаємо надісланим у будь-якому разі (навіть якщо бот заблоковано) —
            # щоб не намагатись повторно й не спамити.
            async with SessionLocal() as session:
                await session.execute(
                    sa_update(User).where(User.id == u.id).values(demo_pitch_sent=True)
                )
                await session.commit()
            if ok:
                sent += 1
                analytics.capture(u.telegram_id, "demo_pitch_sent", {"tenant_id": u.tenant_id})
                await asyncio.sleep(0.05)
        if sent:
            logger.info("📣 Sent %d demo-conversion pitches", sent)
    except Exception as e:
        logger.error("demo_conversion job error: %s", e, exc_info=True)


async def demo_conversion_loop(bot: Bot) -> None:
    logger.info("📣 Demo-conversion scheduler started (every 2 min, delay ~%d min)", DELAY_MIN)
    while True:
        try:
            await check_and_send(bot)
        except Exception as e:
            logger.error("demo_conversion loop error: %s", e)
        await asyncio.sleep(120)
