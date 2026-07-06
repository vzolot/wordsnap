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


def _verify_with_token(
    init_data: str, token: str, max_age_seconds: int | None = None
) -> int | None:
    """Перевіряє підпис initData конкретним токеном бота. Повертає telegram
    user id, якщо підпис валідний саме цим токеном, інакше None."""
    if not init_data or not token:
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


def verify_init_data(init_data: str, max_age_seconds: int | None = None) -> int | None:
    """Backward-compat: перевіряє initData токеном головного бота (env
    TELEGRAM_BOT_TOKEN = тенант 1). Повертає telegram user id або None.
    Для мультитенантного резолву — resolve_init_data() нижче."""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.error("verify_init_data: TELEGRAM_BOT_TOKEN not set")
        return None
    return _verify_with_token(init_data, token, max_age_seconds)


def resolve_init_data(
    init_data: str, max_age_seconds: int | None = None
) -> tuple[int, int] | None:
    """Мультитенантний резолв. Перевіряє підпис initData проти токена КОЖНОГО
    зареєстрованого бота тенанта; той, що збігся, визначає тенант. Повертає
    (tenant_id, telegram_user_id) або None.

    Безпека: tenant_id НЕ приходить від клієнта — він випливає з того, чиїм
    токеном підписано initData. Підробити чужий підпис без токена неможливо.
    """
    if not init_data:
        return None

    # Реєстр ботів наповнюється на старті (bot/main.py) у тому ж процесі, що й
    # FastAPI. Тенант 1 зареєстрований першим → найшвидший шлях для основного
    # трафіку. Імпорт лінивий — уникаємо циклічної залежності.
    try:
        from core.bot_registry import all_bots, tenant_id_for_bot
        bots = all_bots()
    except Exception:
        bots = []

    for bot in bots:
        uid = _verify_with_token(init_data, bot.token, max_age_seconds)
        if uid is not None:
            return (tenant_id_for_bot(bot), uid)

    # Фолбек: реєстр порожній (напр. процес без піднятих ботів) — пробуємо
    # env-токен головного бота як тенант 1.
    env_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if env_token:
        uid = _verify_with_token(init_data, env_token, max_age_seconds)
        if uid is not None:
            return (1, uid)
    return None
