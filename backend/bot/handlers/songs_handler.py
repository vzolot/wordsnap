"""
Хендлер для /songs — куровані набори слів з популярних пісень.
Користувач обирає пісню → бачить ключові слова → тапає слово → воно
проходить звичайний add-flow (OpenAI + Unsplash + збереження + SRS).
"""
import asyncio
import logging
from html import escape

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message, URLInputFile
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from core.bot_i18n import t as bt
from core.openai_client import get_word_data
from core.song_packs import get_pack, get_packs
from core.unsplash_client import search_image
from core.user_service import (
    can_add_word, get_or_create_user, increment_word_counter,
)
from core.word_service import save_word, word_exists

logger = logging.getLogger(__name__)
router = Router()


def format_added_word(word: str, data: dict, native_flag: str) -> str:
    """Скорочена картка слова після додавання з пісні."""
    word_safe = escape(word)
    translation = escape(data.get("translation", ""))
    pos = escape(data.get("part_of_speech", ""))
    memory_tip = escape(data.get("memory_tip", ""))

    text = f"📚 <b>{word_safe}</b>"
    if pos:
        text += f" <i>({pos})</i>"
    text += "\n"
    text += f"{native_flag} <b>{translation}</b>\n"

    examples = data.get("examples") or []
    if examples:
        text += "\n📖 <b>Examples:</b>\n"
        for i, ex in enumerate(examples[:2], 1):
            sentence = escape(ex.get("sentence", "") if isinstance(ex, dict) else str(ex))
            text += f"<b>{i}.</b> {sentence}\n"

    if memory_tip:
        text += f"\n💡 <i>{memory_tip}</i>"

    return text


def packs_keyboard(packs: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for p in packs:
        builder.row(InlineKeyboardButton(
            text=f"{p['emoji']} {p['title']} — {p['artist']}",
            callback_data=f"songpack:{p['id']}",
        ))
    return builder.as_markup()


def words_keyboard(pack_id: str, words: list, lang: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for w in words:
        builder.row(InlineKeyboardButton(
            text=f"📚 {w}",
            callback_data=f"songword:{pack_id}:{w[:50]}",
        ))
    builder.row(InlineKeyboardButton(
        text=bt("songs.back", lang),
        callback_data="songs:list",
    ))
    return builder.as_markup()


@router.message(Command("songs"))
async def cmd_songs(message: Message):
    user = await get_or_create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
    )
    lang = user.native_lang or "uk"
    target = user.target_lang
    if not target:
        await message.answer("⚙️ /start")
        return

    packs = get_packs(target)
    if not packs:
        await message.answer(bt("songs.empty", lang))
        return

    await message.answer(bt("songs.title", lang), reply_markup=packs_keyboard(packs))


@router.callback_query(F.data == "songs:list")
async def show_songs_list(callback: CallbackQuery):
    user = await get_or_create_user(telegram_id=callback.from_user.id)
    lang = user.native_lang or "uk"
    target = user.target_lang or "en"
    packs = get_packs(target)
    await callback.message.edit_text(
        bt("songs.title", lang),
        reply_markup=packs_keyboard(packs),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("songpack:"))
async def show_pack(callback: CallbackQuery):
    pack_id = callback.data.split(":", 1)[1]
    user = await get_or_create_user(telegram_id=callback.from_user.id)
    lang = user.native_lang or "uk"
    target = user.target_lang or "en"

    pack = get_pack(target, pack_id)
    if not pack:
        await callback.answer("?", show_alert=True)
        return

    text = bt("songs.song_intro", lang,
              emoji=pack["emoji"], title=pack["title"], artist=pack["artist"])
    await callback.message.edit_text(
        text, reply_markup=words_keyboard(pack_id, pack["words"], lang)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("songword:"))
async def add_word_from_pack(callback: CallbackQuery):
    parts = callback.data.split(":", 2)
    if len(parts) != 3:
        await callback.answer("?", show_alert=True)
        return
    pack_id, word_short = parts[1], parts[2]

    user = await get_or_create_user(
        telegram_id=callback.from_user.id,
        username=callback.from_user.username,
        first_name=callback.from_user.first_name,
    )
    lang = user.native_lang or "uk"
    target = user.target_lang or "en"

    pack = get_pack(target, pack_id)
    if not pack:
        await callback.answer("?", show_alert=True)
        return

    # Знаходимо повне слово (callback_data зрізаний до 50 символів)
    word = next(
        (w for w in pack["words"] if w[:50] == word_short),
        word_short,
    )

    if await word_exists(user.id, word, target):
        await callback.answer(bt("songs.duplicate_alert", lang), show_alert=True)
        return

    can, reason = await can_add_word(user, lang)
    if not can:
        await callback.answer(reason or bt("songs.limit_alert", lang), show_alert=True)
        return

    await callback.answer(bt("songs.adding", lang))

    try:
        ai_data, image_url = await asyncio.gather(
            get_word_data(word, target_lang=target, native_lang=lang),
            asyncio.create_task(_image_for_word(word)),
        )
    except Exception as e:
        logger.error(f"Songs add: AI error for '{word}': {e}")
        await callback.message.answer(f"❌ {word}: AI error")
        return

    if not ai_data:
        await callback.message.answer(f"❌ {word}: AI error")
        return

    if not image_url:
        image_url = await search_image(ai_data.get("image_keyword", word))

    success = await save_word(
        user_id=user.id, word=word, target_lang=target,
        ai_data=ai_data, image_url=image_url,
    )
    if not success:
        await callback.message.answer(f"❌ {word}: save error")
        return

    await increment_word_counter(user.telegram_id)

    from core.languages import lang_flag
    formatted = format_added_word(word, ai_data, lang_flag(lang))

    if image_url:
        try:
            await callback.message.answer_photo(
                photo=URLInputFile(image_url),
                caption=formatted,
            )
        except Exception:
            await callback.message.answer(formatted)
    else:
        await callback.message.answer(formatted)


async def _image_for_word(word: str) -> str | None:
    """Quick image fetch — fallback if AI image_keyword is missing."""
    try:
        return await search_image(word)
    except Exception:
        return None
