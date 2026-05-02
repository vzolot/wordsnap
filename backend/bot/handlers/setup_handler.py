"""
Хендлер налаштування мов при першому запуску.
"""
import logging
from aiogram import Router, F
from aiogram.types import (
    CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, Message, WebAppInfo
)
from aiogram.filters import Command

from core.languages import LANGUAGES, lang_flag, lang_name
from core.user_service import get_or_create_user, update_user_languages

logger = logging.getLogger(__name__)

router = Router()

MINI_APP_URL = "https://miniapp-omega-three.vercel.app"


def native_lang_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"{flag} {name}",
            callback_data=f"setup_native:{code}",
        )]
        for code, (name, flag) in LANGUAGES.items()
    ])


def target_lang_keyboard(native_code: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"{flag} {name}",
            callback_data=f"setup_target:{native_code}:{code}",
        )]
        for code, (name, flag) in LANGUAGES.items()
        if code != native_code
    ])


def ask_native_lang_text() -> str:
    return "🌍 <b>Яка твоя рідна мова?</b>\n\n<i>Переклади будуть показані цією мовою.</i>"


@router.message(Command("language"))
async def cmd_language(message: Message):
    """Змінити мови навчання"""
    await message.answer(ask_native_lang_text(), reply_markup=native_lang_keyboard())


@router.callback_query(F.data.startswith("setup_native:"))
async def handle_native_lang(callback: CallbackQuery):
    native_code = callback.data.split(":")[1]
    if native_code not in LANGUAGES:
        await callback.answer("Невідома мова", show_alert=True)
        return

    await callback.message.edit_text(
        f"✅ Рідна мова: <b>{lang_flag(native_code)} {lang_name(native_code)}</b>\n\n"
        f"🎯 <b>Яку мову хочеш вивчати?</b>",
        reply_markup=target_lang_keyboard(native_code),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("setup_target:"))
async def handle_target_lang(callback: CallbackQuery):
    parts = callback.data.split(":")
    if len(parts) != 3:
        await callback.answer("Помилка", show_alert=True)
        return

    _, native_code, target_code = parts
    if native_code not in LANGUAGES or target_code not in LANGUAGES:
        await callback.answer("Невідома мова", show_alert=True)
        return

    await update_user_languages(
        telegram_id=callback.from_user.id,
        native_lang=native_code,
        target_lang=target_code,
    )

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="📱 Відкрити WordSnap App",
            web_app=WebAppInfo(url=MINI_APP_URL),
        )]
    ])

    await callback.message.edit_text(
        f"✅ <b>Налаштування збережено!</b>\n\n"
        f"🏠 Рідна мова: <b>{lang_flag(native_code)} {lang_name(native_code)}</b>\n"
        f"🎯 Вивчаємо: <b>{lang_flag(target_code)} {lang_name(target_code)}</b>\n\n"
        f"<b>Як хочеш користуватись:</b>\n"
        f"💬 <b>У чаті</b> — просто надсилай слова сюди, бот робить переклад і нагадування\n"
        f"📱 <b>У додатку</b> — натисни кнопку нижче, додавай слова, повторюй у зручному UI\n\n"
        f"<i>Можеш користуватись і там, і там — все синхронізовано.</i>\n"
        f"<i>Змінити мови: /language</i>",
        reply_markup=keyboard,
    )
    await callback.answer()
