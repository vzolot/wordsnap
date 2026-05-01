from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from core.db import get_db_connection
import os

router = Router()

MINI_APP_URL = os.getenv("MINI_APP_URL", "https://miniapp-omega-three.vercel.app")

@router.message(Command("start"))
async def start(message: Message):
    conn = get_db_connection()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO users (telegram_id, username, first_name) VALUES (?, ?, ?)",
            (message.from_user.id, message.from_user.username, message.from_user.first_name)
        )
        conn.commit()
    finally:
        conn.close()

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="📱 Відкрити WordSnap",
            web_app={"url": MINI_APP_URL}
        )]
    ])

    await message.answer(
        f"👋 Привіт, {message.from_user.first_name}!\n\n"
        "📖 *WordSnap* — твій розумний словник\n\n"
        "Просто надішли мені англійське слово і я:\n"
        "• Перекладу його\n"
        "• Дам приклад вживання\n"
        "• Покажу картинку\n"
        "• Нагадаю повторити у потрібний час\n\n"
        "Або відкрий міні-додаток 👇",
        parse_mode="Markdown",
        reply_markup=keyboard
    )
