"""
Хендлер налаштування мов та onboarding-флоу при першому запуску.
"""
import logging

from aiogram import Router, F
from aiogram.types import (
    CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, Message, WebAppInfo,
    URLInputFile,
)
from aiogram.filters import Command

from core.bot_i18n import t as bt
from core.constants import MINI_APP_URL
from core.languages import LANGUAGES, lang_flag, lang_name
from core.onboarding import get_cities, get_demo_word
from core.rewards import current_tier
from core.unsplash_client import search_image
from core.user_service import (
    get_or_create_user,
    increment_word_counter,
    update_user_languages,
)
from core.word_service import save_word, word_exists

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


def city_keyboard(native_code: str, target_code: str, lang: str) -> InlineKeyboardMarkup:
    cities = get_cities(target_code)
    rows = []
    for city_id, city_name in cities:
        rows.append([InlineKeyboardButton(
            text=city_name,
            callback_data=f"setup_city:{native_code}:{target_code}:{city_id}",
        )])
    rows.append([
        InlineKeyboardButton(
            text=bt("onboard.other_city", lang),
            callback_data=f"setup_city:{native_code}:{target_code}:other",
        ),
        InlineKeyboardButton(
            text=bt("onboard.skip_city", lang),
            callback_data=f"setup_city:{native_code}:{target_code}:skip",
        ),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def demo_keyboard(target_code: str, lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=bt("onboard.demo_snap_btn", lang),
            callback_data=f"demo_snap:{target_code}",
        )],
        [InlineKeyboardButton(
            text=bt("setup.open_app", lang),
            web_app=WebAppInfo(url=MINI_APP_URL),
        )],
    ])


def open_app_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text=bt("setup.open_app", lang),
            web_app=WebAppInfo(url=MINI_APP_URL),
        ),
    ]])


def ask_native_lang_text(lang: str = "uk") -> str:
    return bt("setup.ask_native", lang)


# === /language — змінити мови вже існуючому юзеру ===

@router.message(Command("language"))
async def cmd_language(message: Message):
    user = await get_or_create_user(telegram_id=message.from_user.id)
    lang = user.native_lang or "uk"
    await message.answer(ask_native_lang_text(lang), reply_markup=native_lang_keyboard())


@router.message(Command("demo"))
async def cmd_demo(message: Message):
    """Показати демо-слово для поточних налаштувань (без зміни мов)."""
    user = await get_or_create_user(telegram_id=message.from_user.id)
    native = user.native_lang or "uk"
    target = user.target_lang
    if not target:
        await message.answer(bt("word.setup_first", native))
        return

    demo = get_demo_word(target, native)
    if not demo:
        await message.answer("Demo для цієї пари мов ще немає. Просто надішли будь-яке слово 👋")
        return

    intro = bt("onboard.demo_intro", native, city=lang_name(target), flag=lang_flag(target))
    await message.answer(intro)

    from html import escape
    word_safe = escape(demo["word"])
    pos = escape(demo.get("part_of_speech") or "")
    translation = escape(demo.get("translation") or "")

    card = f"📚 <b>{word_safe}</b>"
    if pos:
        card += f" <i>({pos})</i>"
    card += "\n"
    card += f"{lang_flag(native)} <b>{translation}</b>\n\n"
    card += bt("word.examples_label", native) + "\n"
    for i, ex in enumerate(demo.get("examples", [])[:3], 1):
        sentence = escape(ex.get("sentence", ""))
        explanation = escape(ex.get("explanation", ""))
        card += f"\n<b>{i}.</b> {sentence}\n"
        if explanation:
            card += f"   <i>→ {explanation}</i>\n"
    if demo.get("memory_tip"):
        card += f"\n💡 <i>{escape(demo['memory_tip'])}</i>"

    await message.answer(card, reply_markup=demo_keyboard(target, native))


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
    from core import analytics
    analytics.capture(callback.from_user.id, "lang_selected", {
        "native_lang": native_code,
        "target_lang": target_code,
    })
    analytics.identify(callback.from_user.id, {
        "native_lang": native_code,
        "target_lang": target_code,
    })

    cities = get_cities(target_code)
    if not cities:
        # Немає підтримки міст для цієї мови — одразу до завершення
        await _finish_setup(callback, native_code, target_code)
        return

    # Питаємо про місто
    await callback.message.edit_text(
        bt("onboard.target_picked", native_code, flag=lang_flag(target_code)),
        reply_markup=city_keyboard(native_code, target_code, native_code),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("setup_city:"))
async def handle_city(callback: CallbackQuery):
    parts = callback.data.split(":")
    if len(parts) != 4:
        await callback.answer("Error", show_alert=True)
        return

    _, native_code, target_code, city_id = parts
    user = await get_or_create_user(telegram_id=callback.from_user.id)

    # Зберігаємо region (skip → None)
    if city_id != "skip":
        from core.db import SessionLocal
        from sqlalchemy import update
        from core.models import User
        async with SessionLocal() as session:
            await session.execute(
                update(User).where(User.telegram_id == callback.from_user.id).values(region=city_id)
            )
            await session.commit()
    from core import analytics
    analytics.capture(callback.from_user.id, "region_selected", {
        "region": city_id,
        "skipped": city_id == "skip",
    })

    # Якщо є демо-слово для цієї пари — показуємо демо
    demo = get_demo_word(target_code, native_code)
    if demo:
        await _show_demo(callback, native_code, target_code, city_id, demo)
        return

    # Інакше — стандартне завершення
    await _finish_setup(callback, native_code, target_code)


# === Демо-snap ===

async def _show_demo(callback: CallbackQuery, native_code: str, target_code: str, city_id: str, demo: dict):
    """Показує демо-слово як картку з кнопкою «Snap it»."""
    from core.onboarding import get_cities
    cities = dict(get_cities(target_code))
    city_label = cities.get(city_id, bt("onboard.other_city", native_code))
    if city_id == "skip":
        city_label = lang_name(target_code)

    intro_text = bt("onboard.demo_intro", native_code, city=city_label, flag=lang_flag(target_code))
    await callback.message.edit_text(intro_text)
    await callback.answer()

    # Картка слова
    from html import escape
    word_safe = escape(demo["word"])
    pos = escape(demo.get("part_of_speech") or "")
    translation = escape(demo.get("translation") or "")

    card = f"📚 <b>{word_safe}</b>"
    if pos:
        card += f" <i>({pos})</i>"
    card += "\n"
    card += f"{lang_flag(native_code)} <b>{translation}</b>\n\n"
    card += bt("word.examples_label", native_code) + "\n"
    for i, ex in enumerate(demo.get("examples", [])[:3], 1):
        sentence = escape(ex.get("sentence", ""))
        explanation = escape(ex.get("explanation", ""))
        card += f"\n<b>{i}.</b> {sentence}\n"
        if explanation:
            card += f"   <i>→ {explanation}</i>\n"
    if demo.get("memory_tip"):
        card += f"\n💡 <i>{escape(demo['memory_tip'])}</i>"

    await callback.message.answer(card, reply_markup=demo_keyboard(target_code, native_code))


@router.callback_query(F.data.startswith("demo_snap:"))
async def handle_demo_snap(callback: CallbackQuery):
    target_code = callback.data.split(":")[1]
    user = await get_or_create_user(telegram_id=callback.from_user.id)
    native = user.native_lang or "uk"

    demo = get_demo_word(target_code, native)
    if not demo:
        await callback.answer("?", show_alert=True)
        return

    # Якщо вже додано — просто підтверджуємо
    if await word_exists(user.id, demo["word"], target_code):
        await callback.answer(bt("songs.duplicate_alert", native), show_alert=True)
        return

    # Зберігаємо в словник (без чекання картинки)
    success = await save_word(
        user_id=user.id,
        word=demo["word"],
        target_lang=target_code,
        ai_data=demo,
        image_url=None,
    )
    if not success:
        await callback.answer(bt("word.save_failed", native), show_alert=True)
        return

    await increment_word_counter(callback.from_user.id)

    # Картинку довантажуємо у фон
    import asyncio as _aio
    _aio.create_task(_attach_demo_image(user.id, demo["word"], target_code, demo.get("image_keyword", demo["word"])))

    # Підтвердження + XP-натяк
    tier = current_tier(0)  # Новачок (за наявністю xp ще нема за snap, тільки за review)
    text = (
        f"<b>{bt('onboard.demo_done_title', native)}</b>\n\n"
        f"{bt('onboard.demo_done_body', native)}\n\n"
        f"{bt('onboard.demo_xp', native, tier=bt(tier[1], native))}"
    )
    await callback.message.answer(text, reply_markup=open_app_keyboard(native))
    await callback.answer()


async def _attach_demo_image(user_id: int, word: str, target_code: str, keyword: str):
    """Фон-таск: довантажує Unsplash-картинку для щойно доданого демо-слова."""
    try:
        url = await search_image(keyword)
        if not url:
            return
        from core.db import SessionLocal
        from core.models import Word
        from sqlalchemy import update
        async with SessionLocal() as session:
            await session.execute(
                update(Word)
                .where(Word.user_id == user_id, Word.word == word, Word.target_lang == target_code)
                .values(image_url=url)
            )
            await session.commit()
    except Exception as e:
        logger.warning(f"Failed to attach demo image: {e}")


async def _finish_setup(callback: CallbackQuery, native_code: str, target_code: str):
    """Завершення без демо — стандартне «Setup saved» + Open App кнопка."""
    text = bt(
        "onboard.no_demo",
        native_code,
        flag_n=lang_flag(native_code), name_n=lang_name(native_code),
        flag_t=lang_flag(target_code), name_t=lang_name(target_code),
    )
    await callback.message.edit_text(text, reply_markup=open_app_keyboard(native_code))
    await callback.answer()
