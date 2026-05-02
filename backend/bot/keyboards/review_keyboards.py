"""
Inline-клавіатури для повторення слів.
"""
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def review_answer_keyboard(word_id: int, source: str = "rev") -> InlineKeyboardMarkup:
    """3 кнопки оцінки. source='rev' (з /review) або 'rem' (з нагадування)."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="✅ Знав",
            callback_data=f"review:knew:{word_id}:{source}",
        ),
        InlineKeyboardButton(
            text="🤔 Згадав",
            callback_data=f"review:struggled:{word_id}:{source}",
        ),
        InlineKeyboardButton(
            text="❌ Забув",
            callback_data=f"review:forgot:{word_id}:{source}",
        ),
    )
    return builder.as_markup()


def show_translation_keyboard(word_id: int, source: str = "rev") -> InlineKeyboardMarkup:
    """Кнопка 'Показати переклад'. source: 'rev' (сесія) або 'rem' (нагадування)."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="👁 Показати переклад",
            callback_data=f"reveal:{word_id}:{source}",
        )
    )
    return builder.as_markup()
