"""Брендоване Telegram-меню для ботів тенантів (white-label).

Кожен бот тенанта отримує СВОЄ меню команд, опис і кнопку-меню (без згадок
WordSnap, без білінг-команд). Для викладача (owner_telegram_id) — розширене
chat-scope меню з підказкою відкрити режим викладача. Головний бот WordSnap
(тенант 1) налаштовується окремо у setup_bot_commands (bot/main.py) — тут не чіпаємо.
"""
from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.types import (
    BotCommand, BotCommandScopeChat, BotCommandScopeDefault,
    MenuButtonWebApp, WebAppInfo,
)

from core.constants import MINI_APP_URL
from core.models import Tenant

logger = logging.getLogger(__name__)

# Меню учня (білінг-команд немає — у white-label оплати в додатку немає).
_STUDENT_COMMANDS = [
    BotCommand(command="start", description="Почати / відкрити"),
    BotCommand(command="review", description="🔁 Повторити слова"),
    BotCommand(command="app", description="📱 Відкрити додаток"),
    BotCommand(command="stats", description="📊 Моя статистика"),
]

# Меню викладача — те саме, але /app веде в кабінет викладача (без дублів команд).
_TEACHER_COMMANDS = [
    BotCommand(command="start", description="Почати / відкрити"),
    BotCommand(command="app", description="📱 Кабінет викладача"),
    BotCommand(command="review", description="🔁 Повторити слова"),
    BotCommand(command="stats", description="📊 Статистика"),
]


async def setup_tenant_bot(bot: Bot, tenant: Tenant) -> None:
    """Ставить брендоване меню/опис/кнопку-меню боту тенанта."""
    brand = (tenant.display_name or "Words").strip()

    # 1) Дефолтне меню команд (для всіх користувачів бота).
    await bot.set_my_commands(_STUDENT_COMMANDS, scope=BotCommandScopeDefault())

    # 2) Кнопка-меню одразу відкриває Mini App (без ручного кроку в BotFather).
    try:
        await bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(text="Відкрити", web_app=WebAppInfo(url=MINI_APP_URL))
        )
    except Exception as e:
        logger.warning("set_chat_menu_button failed for %s: %s", tenant.slug, e)

    # 3) Опис бренду (видно у профілі бота / при пошуку) — без згадок WordSnap.
    # Двомовний: за замовчуванням укр+англ (щоб бачили обидві), а для en-клієнтів
    # — чистий англійський.
    desc_uk = (
        f"{brand} — вивчай слова зі своїм викладачем.\n\n"
        f"Відкрий додаток кнопкою нижче: повторюй слова з інтервальним "
        f"повторенням, стеж за прогресом і бронюй уроки."
    )
    desc_en = (
        f"{brand} — learn words with your teacher.\n\n"
        f"Open the app with the button below: review words with spaced "
        f"repetition, track your progress and book lessons."
    )
    desc_both = f"{desc_uk}\n\n———\n\n{desc_en}"
    short_both = f"{brand} — words from your teacher · слова від твого викладача"
    try:
        await bot.set_my_description(description=desc_both)                        # дефолт (вкл. uk-клієнт): обидві
        await bot.set_my_description(description=desc_en, language_code="en")      # en-клієнт: чистий англ
        await bot.set_my_short_description(short_description=short_both)
        await bot.set_my_short_description(short_description=f"{brand} — words from your teacher", language_code="en")
    except Exception as e:
        logger.warning("set_my_description failed for %s: %s", tenant.slug, e)

    # 4) Викладачу (owner_telegram_id) — окреме chat-scope меню.
    if tenant.owner_telegram_id:
        try:
            await bot.set_my_commands(
                _TEACHER_COMMANDS,
                scope=BotCommandScopeChat(chat_id=tenant.owner_telegram_id),
            )
        except Exception as e:
            logger.warning("teacher-scope commands failed for %s: %s", tenant.slug, e)
