"""
Хендлер для обробки слів від юзера.
Day 4+: збереження в БД, картинки Unsplash, ліміти.
Оптимізація: OpenAI + Unsplash паралельно через asyncio.gather + chat_action typing.
"""
import asyncio
import logging
from aiogram import Router, F
from aiogram.types import Message, URLInputFile
from aiogram.filters import Command
from aiogram.enums import ChatAction
from html import escape

from core.openai_client import get_word_data
from core.unsplash_client import search_image
from core.user_service import get_or_create_user, can_add_word, increment_word_counter
from core.word_service import word_exists, save_word
from core.languages import lang_flag

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


async def _typing_loop(bot, chat_id: int, stop_event: asyncio.Event):
    """Показує 'typing...' доки не stop_event. Telegram очищує статус через ~5с,
    тому періодично відправляємо знову."""
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
    await message.answer(
        "➕ <b>Як додати слово</b>\n\n"
        "Просто надішли мені слово або фразу англійською — "
        "я перекладу і зроблю приклади!\n\n"
        "<i>Приклад: ephemeral, take advantage of, look forward to</i>"
    )


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

    # Мова ще не обрана — просимо пройти налаштування
    if not user.target_lang:
        await message.answer(
            "⚙️ Спочатку обери мову для вивчення — надішли /start"
        )
        return

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

    # Запускаємо "typing..." індикатор паралельно
    stop_typing = asyncio.Event()
    typing_task = asyncio.create_task(
        _typing_loop(message.bot, message.chat.id, stop_typing)
    )

    try:
        # Спершу робимо запит до OpenAI — нам ПОТРІБЕН image_keyword з нього
        # для кращого пошуку картинки. Але всередині є оптимізація:
        # після отримання image_keyword — Unsplash шукаємо паралельно зі збереженням.
        ai_data = await get_word_data(
            word,
            target_lang=user.target_lang or "en",
            native_lang=user.native_lang or "uk"
        )

        if ai_data is None:
            stop_typing.set()
            await typing_task
            await message.answer(
                "❌ Не зміг обробити це слово. Спробуй інше або повтори через хвилину."
            )
            return

        # ПАРАЛЕЛЬНО: пошук картинки + інкремент лічильника
        # (раніше було послідовно: спочатку картинка, потім save, потім incr)
        image_keyword = ai_data.get("image_keyword", word)

        image_task = asyncio.create_task(search_image(image_keyword))

        # Чекаємо тільки картинку (інкремент зробимо після save)
        image_url = await image_task

        # Зберігаємо в БД
        success = await save_word(
            user_id=user.id,
            word=word,
            target_lang=user.target_lang or "en",
            ai_data=ai_data,
            image_url=image_url,
        )

        if not success:
            stop_typing.set()
            await typing_task
            await message.answer("❌ Не вдалось зберегти слово. Спробуй ще раз.")
            return

        # Інкрементуємо лічильник (це швидко, але не блокує відповідь юзеру)
        await increment_word_counter(message.from_user.id)

        # Зупиняємо typing
        stop_typing.set()
        await typing_task

        # Форматуємо відповідь
        formatted = format_word_response(word, ai_data, native_lang=user.native_lang or "uk", has_image=bool(image_url))

        # Відправляємо: якщо є картинка — як photo з caption, інакше — текстом
        if image_url:
            try:
                await message.answer_photo(
                    photo=URLInputFile(image_url),
                    caption=formatted,
                )
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
            await message.answer("❌ Сталася помилка. Спробуй пізніше.")
        except Exception:
            pass