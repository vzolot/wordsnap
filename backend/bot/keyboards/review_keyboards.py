"""
Inline-клавіатури для повторення слів.
"""
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def review_answer_keyboard(word_id: int) -> InlineKeyboardMarkup:
    """3 кнопки оцінки: знав / згадав / забув"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="✅ Знав",
            callback_data=f"review:knew:{word_id}",
        ),
        InlineKeyboardButton(
            text="🤔 Згадав",
            callback_data=f"review:struggled:{word_id}",
        ),
        InlineKeyboardButton(
            text="❌ Забув",
            callback_data=f"review:forgot:{word_id}",
        ),
    )
    return builder.as_markup()


def show_translation_keyboard(word_id: int) -> InlineKeyboardMarkup:
    """Кнопка 'Показати переклад' (приховуємо спочатку для test recall)"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="👁 Показати переклад",
            callback_data=f"reveal:{word_id}",
        )
    )
    return builder.as_markup()