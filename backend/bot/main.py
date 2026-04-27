"""
WordSnap Bot — Day 4: Database integration
"""
import asyncio
import logging
import os
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.types import Message
from dotenv import load_dotenv

from bot.handlers.word_handler import router as word_router
from bot.handlers.review_handler import router as review_router
from scheduler.reminder import reminder_loop
from core.user_service import get_or_create_user

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
    
    from core.user_service import get_user_status
    status = await get_user_status(user)
    
    # Привітання залежно від статусу
    if status["is_trial"]:
        plan_text = (
            f"🎁 <b>У тебе TRIAL: {status['trial_days_left']} днів повного доступу!</b>\n"
            f"Користуйся всім без обмежень — а потім вирішиш чи лишатись на Pro."
        )
    elif status["plan"] == "pro":
        plan_text = f"💎 <b>План:</b> PRO"
    else:
        plan_text = (
            f"📊 <b>План:</b> FREE (10 слів/день)\n"
            f"<i>Хочеш більше? /premium</i>"
        )
    
    welcome_text = (
        f"👋 Привіт, <b>{tg_user.first_name}</b>!\n\n"
        f"Я <b>WordSnap</b> — твій AI-помічник у вивченні англійської 🧠\n\n"
        f"<b>Як це працює:</b>\n"
        f"1️⃣ Надішли слово або фразу англійською\n"
        f"2️⃣ Я зроблю переклад, приклади і memory tip\n"
        f"3️⃣ Нагадаю повторити в правильний час 🔔\n\n"
        f"{plan_text}\n\n"
        f"📝 Сьогодні додано: {status['used_today']}/{status['daily_limit']}\n\n"
        f"<i>Спробуй: ephemeral, breakthrough, take advantage of</i>"
    )
    
    await message.answer(welcome_text)
    logger.info(f"User {tg_user.id} ({tg_user.username}) started the bot")


@dp.message(Command("help"))
async def cmd_help(message: Message):
    help_text = (
        "❓ <b>Як користуватись WordSnap</b>\n\n"
        "• Просто надсилай слова — я перекладатиму\n"
        "• /add — як додавати слова\n"
        "• /stats — твоя статистика\n"
        "• /help — ця підказка\n\n"
        "<b>Free план:</b> 10 слів/день\n"
        "<b>Pro план:</b> 100 слів/день (скоро доступний)\n"
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
    
    from core.user_service import get_user_status
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
        "✅ <b>Тематичні набори:</b> Travel, Business, IT, Songs\n"
        "✅ <b>Розширена статистика</b> прогресу\n"
        "✅ <b>Експорт</b> словника\n"
        "✅ <b>Підтримка</b> розробника :)\n\n"
        "💰 <b>$1.49/міс</b> або <b>$14.99/рік</b> (-16%)\n\n"
        "<i>🔧 Платежі WayForPay скоро будуть доступні!</i>\n"
        "<i>А поки — у тебе є 7 днів TRIAL з повним доступом.</i>"
    )
    await message.answer(text)

# Підключаємо роутер з обробкою слів
dp.include_router(word_router)
dp.include_router(review_router)


async def main():
    logger.info("🚀 WordSnap Bot starting...")
    await bot.delete_webhook(drop_pending_updates=True)
    
    # Запускаємо паралельно: бот polling + планувальник нагадувань
    await asyncio.gather(
        dp.start_polling(bot),
        reminder_loop(bot),
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped")