"""
Helper для надсилання Telegram-повідомлень з контексту, де немає
доступу до aiogram Bot — наприклад, з API-роутів.
Використовує raw HTTP API.
"""
import logging
import os

import aiohttp

logger = logging.getLogger(__name__)


async def send_message(
    chat_id: int,
    text: str,
    parse_mode: str = "HTML",
    reply_markup: dict | None = None,
) -> bool:
    """Надсилає повідомлення через Bot API. Повертає True при успіху."""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.warning("TELEGRAM_BOT_TOKEN missing — skipping send_message")
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
