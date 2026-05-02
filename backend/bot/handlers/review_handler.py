"""
Хендлер повторення слів.
- /review — почати сесію повторення зараз
- callback на 3 кнопки оцінки
"""
import logging
from html import escape
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery

from core.user_service import get_or_create_user
from core.word_service import get_words_due_review, get_word_by_id, process_review
from core.srs import format_interval
from core.languages import lang_flag
from bot.keyboards.review_keyboards import review_answer_keyboard, show_translation_keyboard

logger = logging.getLogger(__name__)

router = Router()


def format_review_question(word) -> str:
    """Питання для повторення — слово без перекладу"""
    word_safe = escape(word.word)
    pos = escape(word.part_of_speech or "")
    
    text = f"🔄 <b>Час повторити!</b>\n\n"
    text += f"📚 <b>{word_safe}</b>"
    if pos:
        text += f" <i>({pos})</i>"
    text += "\n\n"
    text += "<i>Згадай переклад, потім натисни кнопку 👇</i>"
    
    return text


def format_review_revealed(word, native_lang: str = "uk") -> str:
    """Повна інформація про слово (після натискання 'показати')"""
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
        text += "📖 <b>Examples:</b>\n"
        for i, ex in enumerate(word.examples[:2], 1):  # тільки 2 приклади на повторенні
            sentence = escape(ex.get('sentence', '') if isinstance(ex, dict) else '')
            text += f"\n<b>{i}.</b> {sentence}\n"
    
    if memory_tip:
        text += f"\n💡 <i>{memory_tip}</i>\n"
    
    text += "\n<b>Як добре ти пам'ятаєш?</b>"
    
    return text


@router.message(Command("review"))
async def cmd_review(message: Message):
    """Показати слова для повторення"""
    user = await get_or_create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
    )
    
    words = await get_words_due_review(user.id, limit=10)
    
    if not words:
        await message.answer(
            "🌱 <b>Немає слів для повторення зараз!</b>\n\n"
            "Додай нові слова, або зачекай поки прийде час повторити вже додані.\n\n"
            "<i>Я нагадаю, коли буде час 🔔</i>"
        )
        return
    
    await message.answer(
        f"🎯 <b>{len(words)} слів готові для повторення</b>\n"
        f"<i>Поїхали!</i>"
    )
    
    # Показуємо перше слово
    await send_review_word(message, words[0])


async def send_review_word(message: Message, word) -> None:
    """Відправити слово для повторення"""
    text = format_review_question(word)
    keyboard = show_translation_keyboard(word.id)
    await message.answer(text, reply_markup=keyboard)


@router.callback_query(F.data.startswith("reveal:"))
async def show_translation(callback: CallbackQuery):
    """Юзер натиснув 'Показати переклад'"""
    word_id = int(callback.data.split(":")[1])
    
    word = await get_word_by_id(word_id)
    if not word:
        await callback.answer("Слово не знайдено", show_alert=True)
        return

    user = await get_or_create_user(telegram_id=callback.from_user.id)
    text = format_review_revealed(word, native_lang=user.native_lang or "uk")
    keyboard = review_answer_keyboard(word_id)
    
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data.startswith("review:"))
async def handle_review_answer(callback: CallbackQuery):
    """Юзер натиснув знав/згадав/забув"""
    parts = callback.data.split(":")
    if len(parts) != 3:
        await callback.answer("Помилка", show_alert=True)
        return
    
    _, result, word_id_str = parts
    word_id = int(word_id_str)
    
    if result not in ("knew", "struggled", "forgot"):
        await callback.answer("Помилка", show_alert=True)
        return
    
    # Обробляємо відповідь
    word, new_interval = await process_review(word_id, result)
    
    if not word:
        await callback.answer("Слово не знайдено", show_alert=True)
        return
    
    # Формуємо повідомлення-підтвердження
    interval_text = format_interval(new_interval)
    
    if result == "knew":
        emoji = "✅"
        praise = "Чудово!"
    elif result == "struggled":
        emoji = "🤔"
        praise = "Молодець!"
    else:
        emoji = "❌"
        praise = "Нічого, повторимо!"
    
    text = (
        f"{emoji} <b>{praise}</b>\n\n"
        f"📚 <b>{escape(word.word)}</b> — {escape(word.translation)}\n"
        f"🔔 <i>Наступне повторення через {interval_text}</i>"
    )
    
    await callback.message.edit_text(text)
    await callback.answer()
    
    # Перевіряємо чи є ще слова для повторення
    words = await get_words_due_review(word.user_id, limit=10)
    
    if words:
        # Невелика пауза, потім наступне слово
        await callback.message.answer(
            f"<i>Залишилось ще {len(words)} слів для повторення</i>"
        )
        await send_review_word(callback.message, words[0])
    else:
        await callback.message.answer(
            "🎉 <b>Всі слова повторені!</b>\n"
            "<i>Чудова робота. Я нагадаю коли буде час знову 🔔</i>"
        )
    
    logger.info(f"User answered '{result}' for word_id={word_id}")