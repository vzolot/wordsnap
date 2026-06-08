"""
Inline-клавіатури для повторення слів. Локалізовано через bot_i18n.
"""
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder

from core.bot_i18n import t as bt
from core.constants import MINI_APP_URL


def review_answer_keyboard(word_id: int, source: str = "rev", lang: str = "en") -> InlineKeyboardMarkup:
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


def show_translation_keyboard(
    word_id: int,
    source: str = "rev",
    lang: str = "en",
    due_total: int = 0,
) -> InlineKeyboardMarkup:
    """Кнопка 'Показати переклад'. Для нагадувань додаємо ще 'Open App'.

    Якщо `due_total > 1` — окрема кнопка "Повторити всі (N) у додатку",
    що веде на /review мініапи (батч-повторення для черги). Інакше —
    звичайний 'Open App' на головну.
    """
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=bt("rev.btn.reveal", lang),
            callback_data=f"reveal:{word_id}:{source}",
        )
    )
    if source == "rem":
        if due_total > 1:
            builder.row(
                InlineKeyboardButton(
                    text=bt("rev.btn.review_all_in_app", lang, n=due_total),
                    web_app=WebAppInfo(url=f"{MINI_APP_URL}/review"),
                )
            )
        else:
            builder.row(
                InlineKeyboardButton(
                    text=bt("rev.btn.open_app", lang),
                    web_app=WebAppInfo(url=MINI_APP_URL),
                )
            )
    return builder.as_markup()
