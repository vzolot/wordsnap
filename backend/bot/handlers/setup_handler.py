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
from core.bot_i18n import t as bt
from core.constants import MINI_APP_URL

logger = logging.getLogger(__name__)

router = Router()


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


def ask_native_lang_text(lang: str = "uk") -> str:
    return bt("setup.ask_native", lang)


@router.message(Command("language"))
async def cmd_language(message: Message):
    """Змінити мови навчання"""
    user = await get_or_create_user(telegram_id=message.from_user.id)
    lang = user.native_lang or "uk"
    await message.answer(ask_native_lang_text(lang), reply_markup=native_lang_keyboard())


@router.callback_query(F.data.startswith("setup_native:"))
async def handle_native_lang(callback: CallbackQuery):
    native_code = callback.data.split(":")[1]
    if native_code not in LANGUAGES:
        await callback.answer("?", show_alert=True)
        return

    await callback.message.edit_text(
        bt("setup.ask_target", native_code, flag=lang_flag(native_code), name=lang_name(native_code)),
        reply_markup=target_lang_keyboard(native_code),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("setup_target:"))
async def handle_target_lang(callback: CallbackQuery):
    parts = callback.data.split(":")
    if len(parts) != 3:
        await callback.answer("Error", show_alert=True)
        return

    _, native_code, target_code = parts
    if native_code not in LANGUAGES or target_code not in LANGUAGES:
        await callback.answer("?", show_alert=True)
        return

    await update_user_languages(
        telegram_id=callback.from_user.id,
        native_lang=native_code,
        target_lang=target_code,
    )

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=bt("setup.open_app", native_code),
            web_app=WebAppInfo(url=MINI_APP_URL),
        )]
    ])

    text = (
        f"{bt('setup.saved', native_code)}\n\n"
        f"{bt('setup.native', native_code)}: <b>{lang_flag(native_code)} {lang_name(native_code)}</b>\n"
        f"{bt('setup.target', native_code)}: <b>{lang_flag(target_code)} {lang_name(target_code)}</b>\n\n"
        f"{bt('setup.how_to_use', native_code)}\n"
        f"{bt('setup.via_chat', native_code)}\n"
        f"{bt('setup.via_app', native_code)}\n\n"
        f"{bt('setup.synced', native_code)}\n"
        f"{bt('setup.change_lang', native_code)}"
    )

    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()
