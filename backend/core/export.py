"""Експорт словника юзера у CSV або Anki .apkg.

CSV — плоска таблиця, відкривається в Excel/Sheets, безкоштовно для всіх.
Anki .apkg — готовий до імпорту в Anki desktop/mobile, Pro-only.
"""
import csv
import io
import logging
import tempfile

import genanki

logger = logging.getLogger(__name__)

# Стабільні ID для Anki — інакше при кожному експорті буде новий "deck"
# і юзер не зможе оновити існуючу колекцію в Anki.
ANKI_MODEL_ID = 1607392319
ANKI_DECK_ID_BASE = 2059400110  # деки = base + telegram_id (унікально на юзера)

ANKI_MODEL = genanki.Model(
    ANKI_MODEL_ID,
    "WordSnap",
    fields=[
        {"name": "Word"},
        {"name": "Translation"},
        {"name": "Example"},
        {"name": "Explanation"},
        {"name": "MemoryTip"},
        {"name": "Image"},
    ],
    templates=[
        {
            "name": "Word → Translation",
            "qfmt": "{{Image}}<br><b style='font-size:24px'>{{Word}}</b>",
            "afmt": (
                "{{FrontSide}}<hr id=answer>"
                "<div style='font-size:20px;color:#7C3AED'>{{Translation}}</div>"
                "{{#Example}}<br><i>{{Example}}</i>{{/Example}}"
                "{{#Explanation}}<br><small>→ {{Explanation}}</small>{{/Explanation}}"
                "{{#MemoryTip}}<br>💡 {{MemoryTip}}{{/MemoryTip}}"
            ),
        },
    ],
    css=(
        ".card { font-family: -apple-system, sans-serif; "
        "text-align: center; padding: 16px; }"
    ),
)


def _example_pair(examples) -> tuple[str, str]:
    """Дістаємо першу пару (sentence, explanation) з examples — формат
    у БД може бути або список рядків, або список dict-ів."""
    if not isinstance(examples, list) or not examples:
        return ("", "")
    first = examples[0]
    if isinstance(first, str):
        return (first, "")
    if isinstance(first, dict):
        return (str(first.get("sentence", "")), str(first.get("explanation", "")))
    return ("", "")


def to_csv(words) -> bytes:
    """Серіалізує список слів у UTF-8 CSV з BOM (щоб Excel відкривав з правильним
    кодуванням)."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "word", "translation", "target_lang", "part_of_speech", "difficulty",
        "example", "example_explanation", "memory_tip", "image_url",
        "review_count", "status", "created_at",
    ])
    for w in words:
        ex_sentence, ex_explanation = _example_pair(w.examples)
        writer.writerow([
            w.word,
            w.translation or "",
            w.target_lang or "",
            w.part_of_speech or "",
            w.difficulty or "",
            ex_sentence,
            ex_explanation,
            w.memory_tip or "",
            w.image_url or "",
            w.review_count or 0,
            w.status or "",
            w.created_at.isoformat() if w.created_at else "",
        ])
    # BOM щоб Excel правильно розпізнав UTF-8
    return ("﻿" + buf.getvalue()).encode("utf-8")


def to_apkg(words, telegram_id: int, target_lang: str | None) -> bytes:
    """Будує Anki .apkg-пакет. Повертає байти готового файлу."""
    deck_name = f"WordSnap · {(target_lang or '??').upper()}"
    deck = genanki.Deck(ANKI_DECK_ID_BASE + abs(int(telegram_id)) % 1000000, deck_name)

    for w in words:
        ex_sentence, ex_explanation = _example_pair(w.examples)
        image_html = f'<img src="{w.image_url}">' if w.image_url else ""
        note = genanki.Note(
            model=ANKI_MODEL,
            fields=[
                w.word,
                w.translation or "",
                ex_sentence,
                ex_explanation,
                w.memory_tip or "",
                image_html,
            ],
            tags=[t for t in [w.target_lang, w.status] if t],
        )
        deck.add_note(note)

    pkg = genanki.Package(deck)
    with tempfile.NamedTemporaryFile(suffix=".apkg", delete=False) as f:
        pkg.write_to_file(f.name)
        f.seek(0)
        with open(f.name, "rb") as r:
            return r.read()
