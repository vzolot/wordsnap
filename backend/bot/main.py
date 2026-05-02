"""
WordSnap Bot — Day 7: Recurring payments + webhook server
"""
import asyncio
import logging
import os
from datetime import datetime, timezone

import uvicorn
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from dotenv import load_dotenv

from bot.handlers.word_handler import router as word_router
from bot.handlers.review_handler import router as review_router
from bot.handlers.setup_handler import router as setup_router, native_lang_keyboard, ask_native_lang_text
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
        await message.answer(
            f"👋 Привіт, <b>{tg_user.first_name}</b>! Я <b>WordSnap</b> — "
            f"твій AI-помічник у вивченні мов 🧠\n\n"
            + ask_native_lang_text(),
            reply_markup=native_lang_keyboard(),
        )
        logger.info(f"New user {tg_user.id} — started language setup")
        return

    status = await get_user_status(user)

    if status["is_trial"]:
        plan_text = (
            f"🎁 <b>У тебе TRIAL: {status['trial_days_left']} днів повного доступу!</b>\n"
            f"Користуйся всім без обмежень — а потім вирішиш чи лишатись на Pro."
        )
    elif status["plan"] == "pro":
        plan_text = "💎 <b>План:</b> PRO"
    else:
        plan_text = (
            f"📊 <b>План:</b> FREE (10 слів/день)\n"
            f"<i>Хочеш більше? /premium</i>"
        )

    from core.languages import lang_flag, lang_name
    target = user.target_lang or "en"
    welcome_text = (
        f"👋 Привіт, <b>{tg_user.first_name}</b>!\n\n"
        f"Я <b>WordSnap</b> — твій AI-помічник у вивченні мов 🧠\n\n"
        f"<b>Як це працює:</b>\n"
        f"1️⃣ Надішли слово або фразу {lang_name(target).lower()}\n"
        f"2️⃣ Я зроблю переклад, приклади і memory tip\n"
        f"3️⃣ Нагадаю повторити в правильний час 🔔\n\n"
        f"🎯 Зараз вивчаємо: <b>{lang_flag(target)} {lang_name(target)}</b>\n\n"
        f"{plan_text}\n\n"
        f"📝 Сьогодні додано: {status['used_today']}/{status['daily_limit']}\n\n"
        f"<i>Змінити мову: /language</i>"
    )

    mini_app_url = "https://miniapp-omega-three.vercel.app"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="📱 Відкрити WordSnap App",
            web_app=WebAppInfo(url=mini_app_url),
        )]
    ])
    await message.answer(welcome_text, reply_markup=keyboard)
    logger.info(f"User {tg_user.id} ({tg_user.username}) started the bot")


@dp.message(Command("help"))
async def cmd_help(message: Message):
    help_text = (
        "❓ <b>Команди WordSnap</b>\n\n"
        "<b>Навчання:</b>\n"
        "• Просто надсилай слова — я перекладатиму\n"
        "• /review — повторити слова зараз\n"
        "• /stats — твоя статистика\n"
        "• /language — змінити мову навчання\n\n"
        "<b>Підписка:</b>\n"
        "• /premium — інфо про Pro\n"
        "• /buy — оформити Pro\n"
        "• /subscription — статус підписки\n"
        "• /unsubscribe — скасувати автопродовження\n\n"
        "<b>Free:</b> 10 слів/день\n"
        "<b>Pro:</b> 100 слів/день, $1.49/міс"
    )
    await message.answer(help_text)


@dp.message(Command("stats"))
async def cmd_stats(message: Message):
    """Статистика юзера"""
    user = await get_or_create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
    )
    
    status = await get_user_status(user)
    
    text = (
        f"📊 <b>Твоя статистика</b>\n\n"
        f"📝 Слів сьогодні: <b>{status['used_today']}/{status['daily_limit']}</b>\n"
        f"📚 Всього слів: <b>{user.total_words}</b>\n"
        f"🔄 Всього повторень: <b>{user.total_reviews}</b>\n"
        f"⭐️ План: <b>{status['plan_label']}</b>\n"
    )
    
    if status["is_trial"]:
        text += f"\n🎁 <i>Trial закінчиться через {status['trial_days_left']} днів</i>"
    elif status["plan"] != "pro":
        text += f"\n💎 <i>Хочеш більше можливостей? /premium</i>"
    
    await message.answer(text)


@dp.message(Command("premium"))
async def cmd_premium(message: Message):
    """Інформація про Pro підписку"""
    text = (
        "💎 <b>WordSnap Pro</b>\n\n"
        "<b>Що отримуєш:</b>\n"
        "✅ <b>100 слів на день</b> (замість 10)\n"
        "✅ <b>Розширена статистика</b> прогресу\n"
        "✅ <b>Тематичні набори</b> (скоро): Travel, Business, IT\n\n"
        "💰 <b>$1.49/міс</b>\n"
        "🔄 Автоматичне продовження\n"
        "❌ Скасувати можна в будь-який момент: /unsubscribe\n\n"
        "Натисни /buy щоб оформити 👇"
    )
    await message.answer(text)


@dp.message(Command("buy"))
async def cmd_buy(message: Message):
    """Створює посилання на оплату Pro"""
    user_id = message.from_user.id
    
    try:
        payment = create_payment_link(
            user_telegram_id=user_id,
            amount=1.49,
            currency="USD",
        )
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="💳 Перейти до оплати",
                url=payment["payment_url"],
            )]
        ])
        
        text = (
            "💎 <b>Оплата WordSnap Pro</b>\n\n"
            "💰 Сума: <b>$1.49</b>\n"
            "📅 Період: 30 днів\n"
            "🔄 Автопродовження: <b>так</b> (можна скасувати)\n"
            "💳 Платіжна система: WayForPay\n\n"
            "Натисни кнопку нижче, заповни дані картки і отримай Pro!\n\n"
            "<i>Картка буде збережена для автоматичних щомісячних списань. "
            "Скасувати в будь-який момент: /unsubscribe</i>"
        )
        
        await message.answer(text, reply_markup=keyboard)
        logger.info(f"Sent payment link to user {user_id}, order {payment['order_reference']}")
        
    except ValueError as e:
        logger.error(f"WayForPay config error: {e}")
        await message.answer(
            "⚠️ Платіжна система тимчасово недоступна. Спробуй пізніше."
        )
    except Exception as e:
        logger.error(f"Error creating payment: {e}", exc_info=True)
        await message.answer("❌ Сталася помилка. Спробуй ще раз.")


@dp.message(Command("subscription"))
async def cmd_subscription(message: Message):
    """Інфо про поточну підписку"""
    user = await get_or_create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
    )
    
    if user.plan == "pro" and user.plan_expires_at:
        is_active = user.plan_expires_at > datetime.now(timezone.utc)
        
        if is_active:
            text = (
                "💎 <b>Твоя підписка: PRO</b>\n\n"
                f"📅 Дійсна до: <b>{user.plan_expires_at.strftime('%d.%m.%Y')}</b>\n"
                f"🔄 Автопродовження: <b>{'✅ ввімкнено' if user.auto_renew else '❌ вимкнено'}</b>\n"
            )
            
            if user.auto_renew:
                text += "\n<i>Підписка автоматично продовжиться за день до закінчення.</i>\n"
                text += "\n/unsubscribe — скасувати автопродовження"
            else:
                text += "\n<i>Автопродовження вимкнено. Підписка закінчиться у вказану дату.</i>\n"
                text += "\n/buy — поновити"
        else:
            text = (
                "⚠️ <b>Твоя Pro підписка закінчилась</b>\n\n"
                "/buy — оформити знов"
            )
    else:
        text = (
            "📊 <b>У тебе немає активної Pro підписки</b>\n\n"
            "/premium — дізнатись про переваги\n"
            "/buy — оформити"
        )
    
    await message.answer(text)


@dp.message(Command("unsubscribe"))
async def cmd_unsubscribe(message: Message):
    """Скасовує автопродовження"""
    user = await get_or_create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
    )
    
    if user.plan != "pro":
        await message.answer(
            "У тебе немає активної підписки.\n"
            "/premium — дізнатись про Pro"
        )
        return
    
    if not user.auto_renew:
        await message.answer(
            "🟡 Автопродовження вже вимкнено.\n\n"
            f"Pro дійсна до: <b>{user.plan_expires_at.strftime('%d.%m.%Y')}</b>"
        )
        return
    
    cancelled = await cancel_subscription(user.telegram_id)
    
    if cancelled:
        await message.answer(
            "✅ <b>Автопродовження скасовано</b>\n\n"
            f"Pro залишається активною до: <b>{cancelled.plan_expires_at.strftime('%d.%m.%Y')}</b>\n\n"
            "<i>Після цієї дати акаунт перейде на FREE план.</i>\n"
            "Передумаєш — /buy щоб поновити."
        )
    else:
        await message.answer("❌ Сталася помилка. Спробуй ще раз.")


# Підключаємо роутери (setup першим — має пріоритет над word_router)
dp.include_router(setup_router)
dp.include_router(word_router)
dp.include_router(review_router)


async def main():
    logger.info("🚀 WordSnap Bot starting...")
    await bot.delete_webhook(drop_pending_updates=True)
    
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