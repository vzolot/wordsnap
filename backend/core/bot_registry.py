"""Реєстр aiogram Bot-інстансів по тенантах (мультибот на polling).

Диспетчер один спільний (bot/instance.dp), а Bot-інстансів багато — по одному
на тенанта. Хендлери отримують від aiogram той `bot`, що прийняв апдейт, тож
`message.answer()` автоматично відповідає з правильного бота. Там, де треба
слати проактивно (шедулери, нагадування) — беремо бота через get_bot(tenant_id).
"""
from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

logger = logging.getLogger(__name__)

_bots_by_tenant: dict[int, Bot] = {}   # tenant_id -> Bot
_tenant_by_botid: dict[int, int] = {}  # telegram bot.id -> tenant_id


def make_bot(token: str) -> Bot:
    """Створює Bot з тими самими дефолтами (HTML parse mode), що головний."""
    return Bot(token=token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))


def register(tenant_id: int, bot: Bot) -> None:
    _bots_by_tenant[tenant_id] = bot
    _tenant_by_botid[bot.id] = tenant_id


def get_bot(tenant_id: int) -> Bot | None:
    return _bots_by_tenant.get(tenant_id)


def tenant_id_for_bot(bot: Bot) -> int:
    """Тенант, якому належить цей Bot-інстанс. Фолбек — базовий тенант 1
    (напр. якщо бот якось не зареєстрований — безпечно не ламати флоу)."""
    return _tenant_by_botid.get(bot.id, 1)


def all_bots() -> list[Bot]:
    return list(_bots_by_tenant.values())


def registered_tenant_ids() -> list[int]:
    return list(_bots_by_tenant.keys())
