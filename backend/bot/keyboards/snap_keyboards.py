"""Inline keyboards для extract-snap (фото/voice → список слів-кандидатів)."""
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def snap_extract_keyboard(words: list[str], source: str) -> InlineKeyboardMarkup:
    """Кнопка на кожне витягнуте слово: тап → один add.

    callback_data: `snap_add:<source>:<word>` — `<word>` не утікаємо, бо
    Telegram дозволяє до 64 байт у callback_data. Слова з vision/voice вже
    нормалізовані до lower-case без лапок (див. extract_words_*).
    `source` — `photo` або `voice` (для analytics).
    """
    rows: list[list[InlineKeyboardButton]] = []
    for w in words:
        # 64-byte hard limit на callback_data у Telegram — обрізаємо щоб не
        # вилетіти. Реально слова <= 60 chars після нормалізації, але про
        # всяк випадок.
        data = f"snap_add:{source}:{w}"[:64]
        rows.append([InlineKeyboardButton(text=f"➕ {w}", callback_data=data)])
    return InlineKeyboardMarkup(inline_keyboard=rows)
