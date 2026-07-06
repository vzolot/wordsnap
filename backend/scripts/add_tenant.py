"""Admin-скрипт: додати нового white-label тенанта (викладача).

Оператор (Vova) створює бота в BotFather, потім запускає це зі своєї машини
(або Railway shell). Скрипт: парсить bot_id з токена, валідує токен через
getMe, створює рядок у `tenants`, і друкує готове посилання на Mini App для
кнопки-меню в BotFather.

Транспорт — polling (не вебхуки), тож setWebhook НЕ викликається. Щоб новий
бот почав приймати повідомлення, оператор має ПЕРЕЗАПУСТИТИ сервіс
(Railway → Redeploy) — при старті мультибот-полінг підхопить усіх активних
тенантів.

Usage:
  python -m scripts.add_tenant \
      --slug oksana \
      --display-name "Слова з Оксаною" \
      --bot-token 123456:ABC-DEF... \
      --owner-telegram-id 469478065 \
      [--logo-url https://...] \
      [--color-primary '#0EA5E9'] [--color-accent '#22C55E'] \
      [--plan trial]
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from core.constants import MINI_APP_URL
from core.tenant_service import (
    create_tenant,
    get_tenant_by_slug,
    get_tenant_by_bot_id,
    parse_bot_id,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger("add_tenant")


async def _validate_token(token: str) -> dict:
    """getMe — переконатися, що токен живий, і забрати username бота."""
    bot = Bot(token=token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    try:
        me = await bot.get_me()
        return {"id": me.id, "username": me.username, "first_name": me.first_name}
    finally:
        await bot.session.close()


async def main() -> int:
    p = argparse.ArgumentParser(description="Додати white-label тенанта")
    p.add_argument("--slug", required=True, help="унікальний slug, напр. oksana")
    p.add_argument("--display-name", required=True, help="бренд, напр. «Слова з Оксаною»")
    p.add_argument("--bot-token", required=True, help="токен бота від BotFather")
    p.add_argument("--owner-telegram-id", type=int, default=None,
                   help="telegram_id викладача (майбутній role=teacher)")
    p.add_argument("--logo-url", default=None)
    p.add_argument("--color-primary", default=None)
    p.add_argument("--color-accent", default=None)
    p.add_argument("--plan", default="trial", choices=["trial", "active", "paused"])
    args = p.parse_args()

    token = args.bot_token.strip()
    bot_id = parse_bot_id(token)
    if bot_id is None:
        logger.error("Токен нерозбірливий (очікую формат <id>:<hash>)")
        return 1

    # Дублікати: slug і bot_id мають бути унікальні.
    if await get_tenant_by_slug(args.slug):
        logger.error("Тенант зі slug=%s вже існує", args.slug)
        return 1
    if await get_tenant_by_bot_id(bot_id):
        logger.error("Тенант із цим ботом (bot_id=%s) вже існує", bot_id)
        return 1

    # Валідація токена через getMe.
    try:
        me = await _validate_token(token)
    except Exception as e:
        logger.error("getMe не пройшов — токен недійсний або бот не існує: %s", e)
        return 1
    if me["id"] != bot_id:
        logger.error("bot_id з токена (%s) ≠ getMe.id (%s) — підозрілий токен", bot_id, me["id"])
        return 1

    tenant = await create_tenant(
        slug=args.slug,
        display_name=args.display_name,
        bot_token=token,
        owner_telegram_id=args.owner_telegram_id,
        logo_url=args.logo_url,
        color_primary=args.color_primary,
        color_accent=args.color_accent,
        plan=args.plan,
    )

    # bot_token НЕ друкуємо (секрет).
    print("\n" + "═" * 64)
    print(f"✅ Тенант створено: {tenant.display_name}")
    print("═" * 64)
    print(f"  id:            {tenant.id}")
    print(f"  slug:          {tenant.slug}")
    print(f"  bot:           @{me['username']} (bot_id={tenant.bot_id})")
    print(f"  owner tg id:   {tenant.owner_telegram_id}")
    print(f"  plan:          {tenant.plan}")
    print(f"  колір бренду:  {tenant.color_primary} / {tenant.color_accent}")
    print("─" * 64)
    print("  BotFather → Bot Settings → Menu Button → URL:")
    print(f"    {MINI_APP_URL}")
    print("─" * 64)
    print("  ⚠️  Далі ОБОВʼЯЗКОВО: Railway → Redeploy сервісу —")
    print("     тоді мультибот-полінг підхопить цього бота.")
    print("  Після старту: призначити викладачу role=teacher (див. M7).")
    print("═" * 64 + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
