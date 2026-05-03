"""
WordSnap Bot — Day 7: Recurring payments + webhook server
"""
import asyncio
import logging
import os
from datetime import datetime, timezone

import uvicorn
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo,
    BotCommand, BotCommandScopeDefault,
)
from dotenv import load_dotenv

from bot.handlers.word_handler import router as word_router
from bot.handlers.review_handler import router as review_router
from bot.handlers.setup_handler import router as setup_router, native_lang_keyboard, ask_native_lang_text
from bot.handlers.songs_handler import router as songs_router
from core.bot_i18n import help_text, premium_text, buy_text, t as bt
from core.constants import MINI_APP_URL
from core.languages import lang_flag, lang_name
from scheduler.reminder import reminder_loop
from scheduler.recurring_charges import recurring_charges_loop
from webhook.server import app as webhook_app
from core.user_service import (
    get_or_create_user,
    get_user_status,
    cancel_subscription,
)
from core.wayforpay_client import create_payment_link

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не знайдено в .env файлі!")

bot = Bot(
    token=TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()


@dp.message(CommandStart())
async def cmd_start(message: Message):
    """Реєстрація юзера в БД при /start"""
    tg_user = message.from_user

    user = await get_or_create_user(
        telegram_id=tg_user.id,
        username=tg_user.username,
        first_name=tg_user.first_name,
        last_name=tg_user.last_name,
        language_code=tg_user.language_code,
    )

    # Новий юзер або ще не обрав мову — запускаємо онбординг
    if not user.target_lang:
        lang = user.native_lang or "uk"
        # Single-message welcome (новий копірайт), потім питаємо рідну мову
        await message.answer(bt("onboard.welcome", lang))
        await message.answer(
            ask_native_lang_text(lang),
            reply_markup=native_lang_keyboard(),
        )
        logger.info(f"New user {tg_user.id} — started language setup")
        return

    lang = user.native_lang or "uk"
    status = await get_user_status(user)
    target = user.target_lang or "en"

    if status["is_trial"]:
        plan_text = bt("start.plan_trial", lang, days=status["trial_days_left"])
    elif status["plan"] == "pro":
        plan_text = bt("start.plan_pro", lang)
    else:
        plan_text = bt("start.plan_free", lang)

    welcome_text = (
        f"{bt('start.hi', lang, name=tg_user.first_name)}\n\n"
        f"{bt('start.intro', lang)}\n\n"
        f"{bt('start.how_works', lang)}\n"
        f"{bt('start.step1', lang, lang_name=lang_name(target))}\n"
        f"{bt('start.step2', lang)}\n"
        f"{bt('start.step3', lang)}\n\n"
        f"{bt('start.learning', lang, flag=lang_flag(target), lang_name=lang_name(target))}\n\n"
        f"{plan_text}\n\n"
        f"{bt('start.added_today', lang, used=status['used_today'], limit=status['daily_limit'])}\n\n"
        f"{bt('start.change_hint', lang)}"
    )

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=bt("setup.open_app", lang),
            web_app=WebAppInfo(url=MINI_APP_URL),
        )]
    ])
    await message.answer(welcome_text, reply_markup=keyboard)
    logger.info(f"User {tg_user.id} ({tg_user.username}) started the bot")


@dp.message(Command("help"))
async def cmd_help(message: Message):
    user = await get_or_create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
    )
    lang = user.native_lang or "uk"
    await message.answer(help_text(lang))


@dp.message(Command("app"))
async def cmd_app(message: Message):
    user = await get_or_create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
    )
    lang = user.native_lang or "uk"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text=bt("setup.open_app", lang),
            web_app=WebAppInfo(url=MINI_APP_URL),
        )
    ]])
    await message.answer(bt("app.intro", lang), reply_markup=keyboard)


@dp.message(Command("settings"))
async def cmd_settings(message: Message):
    user = await get_or_create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
    )
    lang = user.native_lang or "uk"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=bt("settings.lang_btn", lang),
            callback_data="settings:language",
        )],
        [InlineKeyboardButton(
            text=bt("settings.app_btn", lang),
            web_app=WebAppInfo(url=MINI_APP_URL),
        )],
    ])
    await message.answer(bt("settings.title", lang), reply_markup=keyboard)


@dp.callback_query(F.data == "settings:language")
async def settings_language(callback: CallbackQuery):
    user = await get_or_create_user(telegram_id=callback.from_user.id)
    lang = user.native_lang or "uk"
    await callback.message.edit_text(
        ask_native_lang_text(lang),
        reply_markup=native_lang_keyboard(),
    )
    await callback.answer()


@dp.message(Command("stats"))
async def cmd_stats(message: Message):
    user = await get_or_create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
    )
    lang = user.native_lang or "uk"
    status = await get_user_status(user, lang)

    text = (
        f"{bt('stats.title', lang)}\n\n"
        f"{bt('stats.today', lang, used=status['used_today'], limit=status['daily_limit'])}\n"
        f"{bt('stats.total', lang, n=user.total_words)}\n"
        f"{bt('stats.reviews', lang, n=user.total_reviews)}\n"
        f"{bt('stats.plan_label', lang, label=status['plan_label'])}"
    )
    if status["is_trial"]:
        text += "\n\n" + bt("stats.trial_left", lang, days=status["trial_days_left"])
    elif status["plan"] != "pro":
        text += "\n\n" + bt("stats.want_more", lang)

    await message.answer(text)


@dp.message(Command("premium"))
async def cmd_premium(message: Message):
    user = await get_or_create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
    )
    lang = user.native_lang or "uk"
    await message.answer(premium_text(lang))


@dp.message(Command("buy"))
async def cmd_buy(message: Message):
    user = await get_or_create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
    )
    lang = user.native_lang or "uk"

    try:
        payment = create_payment_link(
            user_telegram_id=user.telegram_id,
            amount=1.49,
            currency="USD",
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=bt("buy.btn", lang), url=payment["payment_url"])]
        ])
        await message.answer(buy_text(lang), reply_markup=keyboard)
        logger.info(f"Sent payment link to user {user.telegram_id}, order {payment['order_reference']}")
    except ValueError as e:
        logger.error(f"WayForPay config error: {e}")
        await message.answer(bt("buy.unavailable", lang))
    except Exception as e:
        logger.error(f"Error creating payment: {e}", exc_info=True)
        await message.answer(bt("buy.error", lang))


@dp.message(Command("subscription"))
async def cmd_subscription(message: Message):
    user = await get_or_create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
    )
    lang = user.native_lang or "uk"

    if user.plan == "pro" and user.plan_expires_at:
        is_active = user.plan_expires_at > datetime.now(timezone.utc)
        if is_active:
            renew_state = bt("sub.autorenew.on" if user.auto_renew else "sub.autorenew.off", lang)
            text = (
                f"{bt('sub.pro_title', lang)}\n\n"
                f"{bt('sub.valid_until', lang, date=user.plan_expires_at.strftime('%d.%m.%Y'))}\n"
                f"{bt('sub.autorenew_state', lang, state=renew_state)}\n"
            )
            if user.auto_renew:
                text += "\n" + bt("sub.will_renew", lang)
                text += "\n\n" + bt("sub.cancel_hint", lang)
            else:
                text += "\n" + bt("sub.wont_renew", lang)
                text += "\n\n" + bt("sub.renew_hint", lang)
        else:
            text = bt("sub.expired_title", lang) + "\n\n" + bt("sub.buy_again", lang)
    else:
        text = bt("sub.no_pro", lang)

    await message.answer(text)


@dp.message(Command("unsubscribe"))
async def cmd_unsubscribe(message: Message):
    user = await get_or_create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
    )
    lang = user.native_lang or "uk"

    if user.plan != "pro":
        await message.answer(bt("unsub.no_active", lang))
        return

    if not user.auto_renew:
        date_str = user.plan_expires_at.strftime('%d.%m.%Y') if user.plan_expires_at else "—"
        await message.answer(bt("unsub.already_off", lang, date=date_str))
        return

    cancelled = await cancel_subscription(user.telegram_id)
    if cancelled:
        date_str = cancelled.plan_expires_at.strftime('%d.%m.%Y') if cancelled.plan_expires_at else "—"
        await message.answer(bt("unsub.cancelled", lang, date=date_str))
    else:
        await message.answer(bt("unsub.error", lang))


# Підключаємо роутери (setup першим — має пріоритет над word_router)
dp.include_router(setup_router)
dp.include_router(songs_router)
dp.include_router(review_router)
dp.include_router(word_router)


async def setup_bot_commands():
    """Оновлює меню команд бота. Викликається на старті."""
    commands = [
        BotCommand(command="start", description="Почати або змінити налаштування"),
        BotCommand(command="songs", description="🎵 Слова з популярних пісень"),
        BotCommand(command="review", description="Повторити слова"),
        BotCommand(command="app", description="📱 Відкрити додаток"),
        BotCommand(command="stats", description="Моя статистика"),
        BotCommand(command="language", description="Змінити мову навчання"),
        BotCommand(command="premium", description="Pro-підписка"),
        BotCommand(command="help", description="Як користуватись"),
    ]
    await bot.set_my_commands(commands, scope=BotCommandScopeDefault())


async def main():
    logger.info("🚀 WordSnap Bot starting...")
    await bot.delete_webhook(drop_pending_updates=True)
    try:
        await setup_bot_commands()
    except Exception as e:
        logger.warning(f"Failed to set bot commands: {e}")
    
    # Конфігурація FastAPI server
    port = int(os.getenv("PORT", "8000"))
    config = uvicorn.Config(
        webhook_app,
        host="0.0.0.0",
        port=port,
        log_level="info",
    )
    server = uvicorn.Server(config)
    
    logger.info(f"📡 Webhook server starting on port {port}")
    
    # Запускаємо паралельно: bot polling + reminder + recurring charges + webhook
    await asyncio.gather(
        dp.start_polling(bot),
        reminder_loop(bot),
        recurring_charges_loop(bot),
        server.serve(),
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped")