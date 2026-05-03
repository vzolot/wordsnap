"""
Inline-клавіатури для повторення слів. Локалізовано через bot_i18n.
"""
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder

from core.bot_i18n import t as bt
from core.constants import MINI_APP_URL


def review_answer_keyboard(word_id: int, source: str = "rev", lang: str = "uk") -> InlineKeyboardMarkup:
    """3 кнопки оцінки: знав / згадав / забув."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=bt("rev.btn.knew", lang),
            callback_data=f"review:knew:{word_id}:{source}",
        ),
        InlineKeyboardButton(
            text=bt("rev.btn.struggled", lang),
            callback_data=f"review:struggled:{word_id}:{source}",
        ),
        InlineKeyboardButton(
            text=bt("rev.btn.forgot", lang),
            callback_data=f"review:forgot:{word_id}:{source}",
        ),
    )
    return builder.as_markup()


def show_translation_keyboard(word_id: int, source: str = "rev", lang: str = "uk") -> InlineKeyboardMarkup:
    """Кнопка 'Показати переклад'. Для нагадувань додаємо ще 'Open App'."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=bt("rev.btn.reveal", lang),
            callback_data=f"reveal:{word_id}:{source}",
        )
    )
    if source == "rem":
        builder.row(
            InlineKeyboardButton(
                text=bt("rev.btn.open_app", lang),
                web_app=WebAppInfo(url=MINI_APP_URL),
            )
        )
    return builder.as_markup()
