"""
Хендлер повторення слів.
"""
import logging
from html import escape

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery

from core.bot_i18n import t as bt, tier_up_text
from core.languages import lang_flag
from core.srs import format_interval
from core.user_service import get_or_create_user
from core.word_service import get_word_by_id, get_words_due_review, process_review
from bot.keyboards.review_keyboards import review_answer_keyboard, show_translation_keyboard

logger = logging.getLogger(__name__)
router = Router()


def format_review_question(word) -> str:
    word_safe = escape(word.word)
    pos = escape(word.part_of_speech or "")
    text = ""  # title is set per-callback below
    text += f"📚 <b>{word_safe}</b>"
    if pos:
        text += f" <i>({pos})</i>"
    return text


def format_review_revealed(word, native_lang: str = "uk") -> str:
    word_safe = escape(word.word)
    translation = escape(word.translation or "")
    pos = escape(word.part_of_speech or "")
    memory_tip = escape(word.memory_tip or "")

    text = f"📚 <b>{word_safe}</b>"
    if pos:
        text += f" <i>({pos})</i>"
    text += "\n"
    text += f"{lang_flag(native_lang)} <b>{translation}</b>\n\n"

    if word.examples:
        text += bt("review.examples_label", native_lang) + "\n"
        for i, ex in enumerate(word.examples[:2], 1):
            sentence = escape(ex.get("sentence", "") if isinstance(ex, dict) else "")
            text += f"\n<b>{i}.</b> {sentence}\n"

    if memory_tip:
        text += f"\n💡 <i>{memory_tip}</i>\n"

    text += "\n" + bt("review.how_well", native_lang)
    return text


@router.message(Command("review"))
async def cmd_review(message: Message):
    user = await get_or_create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
    )
    lang = user.native_lang or "uk"

    words = await get_words_due_review(user.id, limit=10)
    if not words:
        await message.answer(bt("review.empty", lang))
        return

    await message.answer(bt("review.ready", lang, n=len(words)))
    await send_review_word(message, words[0], lang=lang)


async def send_review_word(message: Message, word, source: str = "rev", lang: str = "uk") -> None:
    word_safe = escape(word.word)
    pos = escape(word.part_of_speech or "")
    text = f"{bt('review.question_title', lang)}\n\n📚 <b>{word_safe}</b>"
    if pos:
        text += f" <i>({pos})</i>"
    text += "\n\n" + bt("review.guess_hint", lang)

    keyboard = show_translation_keyboard(word.id, source=source, lang=lang)
    await message.answer(text, reply_markup=keyboard)


@router.callback_query(F.data.startswith("reveal:"))
async def show_translation(callback: CallbackQuery):
    parts = callback.data.split(":")
    word_id = int(parts[1])
    source = parts[2] if len(parts) > 2 else "rev"

    user = await get_or_create_user(telegram_id=callback.from_user.id)
    lang = user.native_lang or "uk"

    word = await get_word_by_id(word_id)
    if not word:
        await callback.answer(bt("review.not_found", lang), show_alert=True)
        return

    text = format_review_revealed(word, native_lang=lang)
    keyboard = review_answer_keyboard(word_id, source=source, lang=lang)

    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data.startswith("review:"))
async def handle_review_answer(callback: CallbackQuery):
    user = await get_or_create_user(telegram_id=callback.from_user.id)
    lang = user.native_lang or "uk"

    parts = callback.data.split(":")
    if len(parts) < 3:
        await callback.answer(bt("review.error", lang), show_alert=True)
        return

    _, result, word_id_str = parts[0], parts[1], parts[2]
    source = parts[3] if len(parts) > 3 else "rev"
    word_id = int(word_id_str)

    if result not in ("knew", "struggled", "forgot"):
        await callback.answer(bt("review.error", lang), show_alert=True)
        return

    word, new_interval, tier_up = await process_review(word_id, result)
    if not word:
        await callback.answer(bt("review.not_found", lang), show_alert=True)
        return

    interval_text = format_interval(new_interval)

    if result == "knew":
        emoji, praise = "✅", bt("review.praise.knew", lang)
    elif result == "struggled":
        emoji, praise = "🤔", bt("review.praise.struggled", lang)
    else:
        emoji, praise = "❌", bt("review.praise.forgot", lang)

    text = (
        f"{emoji} <b>{praise}</b>\n\n"
        f"📚 <b>{escape(word.word)}</b> — {escape(word.translation)}\n"
        f"{bt('review.next_in', lang, interval=interval_text)}"
    )

    await callback.message.edit_text(text)
    await callback.answer()

    if tier_up:
        threshold, tier_key, reward_key = tier_up
        await callback.message.answer(
            tier_up_text(lang, threshold, tier_key, reward_key)
        )

    # Auto-chain через всю чергу due-слів — і для /review (source=rev), і для
    # нагадувань (source=rem). Раніше для rem був early return → юзер бачив
    # тільки 1 слово на день навіть якщо в черзі 16. Тепер відповідь на
    # нагадування продовжує сесію і ловить решту прямо в чаті.
    # Зберігаємо `source` у наступному слові щоб PostHog міг атрибутувати
    # довгу сесію до її стартового тригера (push vs /review).
    words = await get_words_due_review(word.user_id, limit=10)
    if words:
        await callback.message.answer(bt("review.left_more", lang, n=len(words)))
        await send_review_word(callback.message, words[0], source=source, lang=lang)
    else:
        await callback.message.answer(bt("review.all_done", lang))

    logger.info(f"User answered '{result}' for word_id={word_id} (source={source})")
