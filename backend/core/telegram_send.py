"""
Helper для надсилання Telegram-повідомлень з контексту, де немає
доступу до aiogram Bot — наприклад, з API-роутів.
Використовує raw HTTP API.
"""
import logging
import os

import aiohttp

logger = logging.getLogger(__name__)


def _token_for_tenant(tenant_id: int) -> str | None:
    """Токен бота відповідного тенанта — щоб повідомлення йшло з ПРАВИЛЬНОГО
    бренду. Для тенанта 1 (або невідомого) — env TELEGRAM_BOT_TOKEN. Токени
    ботів тенантів беремо з реєстру (наповнюється на старті в тому ж процесі)."""
    if tenant_id and tenant_id != 1:
        try:
            from core.bot_registry import get_bot
            b = get_bot(tenant_id)
            if b:
                return b.token
        except Exception:
            pass
    return os.getenv("TELEGRAM_BOT_TOKEN")


async def send_message(
    chat_id: int,
    text: str,
    parse_mode: str = "HTML",
    reply_markup: dict | None = None,
    tenant_id: int = 1,
) -> bool:
    """Надсилає повідомлення через Bot API з бота тенанта. Повертає True при успіху."""
    token = _token_for_tenant(tenant_id)
    if not token:
        logger.warning("no bot token for tenant %s — skipping send_message", tenant_id)
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload: dict = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup

    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
            async with s.post(url, json=payload) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    logger.warning(f"Telegram sendMessage {resp.status}: {body[:200]}")
                    return False
        return True
    except Exception as e:
        logger.warning(f"Failed to send Telegram message: {e}")
        return False


async def send_document(
    chat_id: int,
    file_bytes: bytes,
    filename: str,
    caption: str | None = None,
    mime_type: str = "application/octet-stream",
    tenant_id: int = 1,
) -> bool:
    """Надсилає файл у бот-чат через Telegram Bot API (multipart/form-data)
    з бота відповідного тенанта."""
    token = _token_for_tenant(tenant_id)
    if not token:
        logger.warning("no bot token for tenant %s — skipping send_document", tenant_id)
        return False

    url = f"https://api.telegram.org/bot{token}/sendDocument"
    form = aiohttp.FormData()
    form.add_field("chat_id", str(chat_id))
    if caption:
        form.add_field("caption", caption)
        form.add_field("parse_mode", "HTML")
    form.add_field(
        "document",
        file_bytes,
        filename=filename,
        content_type=mime_type,
    )
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as s:
            async with s.post(url, data=form) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    logger.warning(f"Telegram sendDocument {resp.status}: {body[:200]}")
                    return False
        return True
    except Exception as e:
        logger.warning(f"Failed to send Telegram document: {e}")
        return False
