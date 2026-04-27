"""
WordSnap Bot — Day 1: Hello World
Перша версія: бот відповідає на /start і повторює будь-які повідомлення.
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

# Завантажуємо змінні з .env файлу
load_dotenv()

# Налаштування логування — будемо бачити що відбувається
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)
logger = logging.getLogger(__name__)

# Перевіряємо що токен є
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не знайдено в .env файлі!")

# Створюємо бота і диспатчер
bot = Bot(
    token=TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()


@dp.message(CommandStart())
async def cmd_start(message: Message):
    """Обробник команди /start — перше привітання"""
    user_name = message.from_user.first_name or "друже"
    
    welcome_text = (
        f"👋 Привіт, <b>{user_name}</b>!\n\n"
        f"Я <b>WordSnap</b> — твій AI-помічник у вивченні іноземних мов 🧠\n\n"
        f"<i>Поки що я тільки вчуся, але вже скоро навчуся:</i>\n"
        f"• Перекладати слова з контекстом\n"
        f"• Показувати приклади вживання\n"
        f"• Нагадувати повторити в правильний час\n\n"
        f"Спробуй надіслати мені будь-яке повідомлення 👇"
    )
    
    await message.answer(welcome_text)
    logger.info(f"User {message.from_user.id} started the bot")


@dp.message(Command("help"))
async def cmd_help(message: Message):
    """Обробник команди /help"""
    help_text = (
        "❓ <b>Як користуватись WordSnap</b>\n\n"
        "Поки що бот в розробці. Скоро з'являться:\n"
        "• /add — додати слово\n"
        "• /review — повторити слова\n"
        "• /settings — налаштування\n\n"
        "Слідкуй за оновленнями! 🚀"
    )
    await message.answer(help_text)


@dp.message()
async def echo_handler(message: Message):
    """Тимчасовий echo — повторюємо те, що написав юзер"""
    if message.text:
        await message.answer(
            f"📝 Ти написав: <i>{message.text}</i>\n\n"
            f"<i>Поки я не вмію обробляти слова, але скоро навчуся!</i>"
        )
    else:
        await message.answer("Я поки розумію тільки текст 🙂")


async def main():
    """Точка входу"""
    logger.info("🚀 WordSnap Bot starting...")
    
    # Видаляємо webhook на випадок якщо він був
    await bot.delete_webhook(drop_pending_updates=True)
    
    # Запускаємо polling (бот опитує Telegram про нові повідомлення)
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped")