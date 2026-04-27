"""
Хендлер для обробки слів від юзера.
Day 4: збереження в БД, картинки Unsplash, ліміти.
"""
import logging
from aiogram import Router, F
from aiogram.types import Message, URLInputFile
from aiogram.filters import Command
from html import escape

from core.openai_client import get_word_data
from core.unsplash_client import search_image
from core.user_service import get_or_create_user, can_add_word, increment_word_counter
from core.word_service import word_exists, save_word

logger = logging.getLogger(__name__)

router = Router()


def format_word_response(word: str, data: dict, has_image: bool = False) -> str:
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
    
    text += f"🇺🇦 <b>{translation}</b>\n\n"
    
    text += "📖 <b>Examples:</b>\n"
    for i, ex in enumerate(data.get('examples', []), 1):
        sentence = escape(ex.get('sentence', ''))
        explanation = escape(ex.get('explanation', ''))
        text += f"\n<b>{i}.</b> {sentence}\n"
        if explanation:
            text += f"   <i>→ {explanation}</i>\n"
    
    if memory_tip:
        text += f"\n💡 <b>Memory tip:</b> <i>{memory_tip}</i>\n"
    
    text += "\n🔔 <i>I'll remind you about this word in 1 day</i>"
    
    return text


@router.message(Command("add"))
async def cmd_add(message: Message):
    await message.answer(
        "➕ <b>Як додати слово</b>\n\n"
        "Просто надішли мені слово або фразу англійською — "
        "я перекладу і зроблю приклади!\n\n"
        "<i>Приклад: ephemeral, take advantage of, look forward to</i>"
    )


# F.text — фільтр з aiogram, ловимо тільки текстові повідомлення без команд
@router.message(F.text & ~F.text.startswith('/'))
async def handle_word(message: Message):
    """Обробка тексту як слова для вивчення"""
    word = message.text.strip()
    
    # Базова валідація
    if len(word) > 100:
        await message.answer("⚠️ Слово або фраза задовге. Максимум 100 символів.")
        return
    
    if len(word) < 2:
        await message.answer("⚠️ Слово закоротке. Спробуй щось довше.")
        return
    
    # Отримуємо/створюємо юзера
    user = await get_or_create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
    )
    
    # Перевірка ліміту
    can_add, reason = await can_add_word(user)
    if not can_add:
        await message.answer(f"⛔️ {reason}")
        return
    
    # Перевірка на дублікат
    if await word_exists(user.id, word, user.target_lang or "en"):
        await message.answer(
            f"♻️ Слово <b>{escape(word)}</b> вже є у твоєму словнику!\n"
            f"<i>Я нагадаю тобі про нього у потрібний час.</i>"
        )
        return
    
    # Показуємо що бот думає
    thinking = await message.answer("🤔 <i>Думаю...</i>")
    
    try:
        # 1. Запит до OpenAI
        ai_data = await get_word_data(
            word, 
            target_lang=user.target_lang or "en", 
            native_lang=user.native_lang or "uk"
        )
        
        if ai_data is None:
            await thinking.edit_text(
                "❌ Не зміг обробити це слово. Спробуй інше або повтори через хвилину."
            )
            return
        
        # 2. Шукаємо картинку (паралельно можна, але поки послідовно)
        image_keyword = ai_data.get("image_keyword", word)
        image_url = await search_image(image_keyword)
        
        # 3. Зберігаємо в БД
        saved = await save_word(
            user_id=user.id,
            word=word,
            target_lang=user.target_lang or "en",
            ai_data=ai_data,
            image_url=image_url,
        )
        
        if saved is None:
            await thinking.edit_text("❌ Не вдалось зберегти слово. Спробуй ще раз.")
            return
        
        # 4. Інкрементуємо лічильник
        await increment_word_counter(message.from_user.id)
        
        # 5. Форматуємо відповідь
        formatted = format_word_response(word, ai_data, has_image=bool(image_url))
        
        # 6. Відправляємо: якщо є картинка — як photo з caption, інакше — текстом
        if image_url:
            try:
                # Видаляємо thinking повідомлення
                await thinking.delete()
                # Відправляємо фото з підписом
                await message.answer_photo(
                    photo=URLInputFile(image_url),
                    caption=formatted,
                )
            except Exception as e:
                logger.warning(f"Failed to send photo, falling back to text: {e}")
                await message.answer(formatted)
        else:
            await thinking.edit_text(formatted)
        
        logger.info(f"User {message.from_user.id} added word: {word}")
        
    except Exception as e:
        logger.error(f"Error processing word '{word}': {e}", exc_info=True)
        try:
            await thinking.edit_text("❌ Сталася помилка. Спробуй пізніше.")
        except Exception:
            pass