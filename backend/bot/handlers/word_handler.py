"""
Хендлер для обробки слів від юзера.
"""
import asyncio
import logging
from html import escape

from aiogram import Router, F
from aiogram.types import Message, URLInputFile
from aiogram.filters import Command
from aiogram.enums import ChatAction

from core.bot_i18n import t as bt
from core.languages import lang_flag, lang_name
from core.openai_client import get_word_data
from core.unsplash_client import search_image
from core.user_service import get_or_create_user, can_add_word, increment_word_counter
from core.word_service import word_exists, save_word

logger = logging.getLogger(__name__)
router = Router()


def format_word_response(word: str, data: dict, native_lang: str = "uk", has_image: bool = False) -> str:
    """Форматує AI-відповідь у HTML-текст для Telegram"""
    word_safe = escape(word)
    translation = escape(data.get('translation', ''))
    pos = escape(data.get('part_of_speech', ''))
    difficulty = escape(data.get('difficulty', ''))
    memory_tip = escape(data.get('memory_tip', ''))

    text = f"📚 <b>{word_safe}</b>"
    if pos:
        text += f" <i>({pos})</i>"
    if difficulty:
        text += f" • {difficulty}"
    text += "\n"

    text += f"{lang_flag(native_lang)} <b>{translation}</b>\n\n"

    text += bt("word.examples_label", native_lang) + "\n"
    for i, ex in enumerate(data.get('examples', []), 1):
        sentence = escape(ex.get('sentence', ''))
        explanation = escape(ex.get('explanation', ''))
        text += f"\n<b>{i}.</b> {sentence}\n"
        if explanation:
            text += f"   <i>→ {explanation}</i>\n"

    if memory_tip:
        text += f"\n{bt('word.tip_label', native_lang)} <i>{memory_tip}</i>\n"

    text += "\n" + bt("word.remind_in_1d", native_lang)

    return text


async def _typing_loop(bot, chat_id: int, stop_event: asyncio.Event):
    try:
        while not stop_event.is_set():
            try:
                await bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
            except Exception:
                pass
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=4.0)
            except asyncio.TimeoutError:
                continue
    except Exception:
        pass


@router.message(Command("add"))
async def cmd_add(message: Message):
    user = await get_or_create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
    )
    lang = user.native_lang or "uk"
    target_name = lang_name(user.target_lang or "en")
    text = (
        f"{bt('add.title', lang)}\n\n"
        f"{bt('add.body', lang, lang_name=target_name)}\n\n"
        f"{bt('add.example', lang)}"
    )
    await message.answer(text)


@router.message(F.text & ~F.text.startswith('/'))
async def handle_word(message: Message):
    word = message.text.strip()

    # Спершу витягуємо юзера, бо для повідомлень помилок потрібна мова
    user = await get_or_create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
    )
    lang = user.native_lang or "uk"

    if len(word) > 100:
        await message.answer(bt("word.too_long", lang))
        return
    if len(word) < 2:
        await message.answer(bt("word.too_short", lang))
        return

    if not user.target_lang:
        await message.answer(bt("word.setup_first", lang))
        return

    can_add, reason = await can_add_word(user, lang)
    if not can_add:
        await message.answer(reason)
        return

    if await word_exists(user.id, word, user.target_lang):
        await message.answer(bt("word.duplicate", lang, word=escape(word)))
        return

    stop_typing = asyncio.Event()
    typing_task = asyncio.create_task(
        _typing_loop(message.bot, message.chat.id, stop_typing)
    )

    try:
        ai_data = await get_word_data(
            word,
            target_lang=user.target_lang,
            native_lang=lang,
        )

        if ai_data is None:
            stop_typing.set()
            await typing_task
            await message.answer(bt("word.ai_failed", lang))
            return

        image_keyword = ai_data.get("image_keyword", word)
        image_task = asyncio.create_task(search_image(image_keyword))
        image_url = await image_task

        success = await save_word(
            user_id=user.id,
            word=word,
            target_lang=user.target_lang,
            ai_data=ai_data,
            image_url=image_url,
        )

        if not success:
            stop_typing.set()
            await typing_task
            await message.answer(bt("word.save_failed", lang))
            return

        await increment_word_counter(message.from_user.id)

        stop_typing.set()
        await typing_task

        formatted = format_word_response(word, ai_data, native_lang=lang, has_image=bool(image_url))

        if image_url:
            try:
                await message.answer_photo(photo=URLInputFile(image_url), caption=formatted)
            except Exception as e:
                logger.warning(f"Failed to send photo, falling back to text: {e}")
                await message.answer(formatted)
        else:
            await message.answer(formatted)

        logger.info(f"User {message.from_user.id} added word: {word}")

    except Exception as e:
        logger.error(f"Error processing word '{word}': {e}", exc_info=True)
        stop_typing.set()
        try:
            await typing_task
        except Exception:
            pass
        try:
            await message.answer(bt("word.error", lang))
        except Exception:
            pass
