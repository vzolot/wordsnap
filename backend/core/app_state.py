"""Простий персистентний key-value стан у БД (`app_state` таблиця).

Для глобальних прапорців, які мають пережити перезапуск процесу — напр.
"коли востаннє слали адмін-звіт", щоб redeploy під час 09:xx не задвоїв
розсилку. In-memory state скидається на restart; це — ні.
"""
import logging

from sqlalchemy import text

from .db import SessionLocal

logger = logging.getLogger(__name__)


async def get_state(key: str) -> str | None:
    try:
        async with SessionLocal() as session:
            row = (await session.execute(
                text("SELECT value FROM app_state WHERE key = :k"), {"k": key}
            )).first()
            return row[0] if row else None
    except Exception as e:
        logger.warning(f"app_state get '{key}' failed: {e}")
        return None


async def set_state(key: str, value: str) -> None:
    try:
        async with SessionLocal() as session:
            await session.execute(
                text(
                    "INSERT INTO app_state (key, value, updated_at) "
                    "VALUES (:k, :v, NOW()) "
                    "ON CONFLICT (key) DO UPDATE SET value = :v, updated_at = NOW()"
                ),
                {"k": key, "v": value},
            )
            await session.commit()
    except Exception as e:
        logger.warning(f"app_state set '{key}' failed: {e}")
