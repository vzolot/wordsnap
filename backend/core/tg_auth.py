"""Валідація Telegram WebApp initData.

Mini-app шле підписаний рядок `initData` (з `Telegram.WebApp.initData`) у
заголовку `X-Telegram-Init-Data`. Тут перевіряємо HMAC-підпис ключем,
похідним від токена бота — і лише тоді довіряємо `telegram_id`. Без цього
бекенд сліпо вірив `telegram_id` з query-параметра → будь-хто міг читати/
міняти чужий акаунт (IDOR).

Спека: https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time
from urllib.parse import parse_qsl

logger = logging.getLogger(__name__)


def verify_init_data(init_data: str, max_age_seconds: int | None = None) -> int | None:
    """Повертає telegram user id якщо підпис initData валідний, інакше None.

    `max_age_seconds`: якщо задано — відхиляє надто старий `auth_date`. За
    замовчуванням None (не обмежуємо), щоб не розлогінювати юзерів із довгою
    сесією — підпис сам по собі доводить автентичність.
    """
    if not init_data:
        return None
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.error("verify_init_data: TELEGRAM_BOT_TOKEN not set")
        return None

    try:
        # keep_blank_values — щоб не загубити порожні поля при побудові
        # data-check-string; parse_qsl одразу percent-decode'ить значення,
        # а саме decoded-значення вимагає алгоритм Telegram.
        pairs = parse_qsl(init_data, keep_blank_values=True)
    except Exception:
        return None

    data = dict(pairs)
    received_hash = data.pop("hash", None)
    if not received_hash:
        return None

    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(data.items()))
    secret_key = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    calc_hash = hmac.new(
        secret_key, data_check_string.encode(), hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(calc_hash, received_hash):
        return None

    if max_age_seconds is not None:
        try:
            auth_date = int(data.get("auth_date", "0"))
            if auth_date and (time.time() - auth_date) > max_age_seconds:
                logger.info("verify_init_data: rejecting stale auth_date")
                return None
        except (ValueError, TypeError):
            pass

    try:
        user = json.loads(data.get("user", "{}"))
        return int(user["id"])
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        return None
