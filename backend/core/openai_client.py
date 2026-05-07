"""
OpenAI integration для генерації перекладів і прикладів.
Використовує gpt-4o-mini.
"""
import os
import json
import logging
from typing import TypedDict
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

LANGUAGE_NAMES = {
    "uk": "Ukrainian",
    "en": "English",
    "es": "Spanish",
    "pl": "Polish",
    "de": "German",
}

client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))


class WordExample(TypedDict):
    sentence: str
    explanation: str


class WordData(TypedDict):
    translation: str
    part_of_speech: str
    difficulty: str
    examples: list[WordExample]
    memory_tip: str
    image_keyword: str


SYSTEM_PROMPT = (
    "You are a concise vocabulary tutor. Respond ONLY with valid JSON, "
    "no markdown, no extra text. Be brief: short examples, short explanations."
)


def build_user_prompt(word: str, target_lang: str, native_lang: str = "uk") -> str:
    target_name = LANGUAGE_NAMES.get(target_lang, "English")
    native_name = LANGUAGE_NAMES.get(native_lang, "Ukrainian")

    return (
        f'Word: "{word}". Target: {target_name}. Native: {native_name}.\n\n'
        f'STEP 1 — verify: does "{word}" actually exist in {target_name} (or is it a '
        f'common phrase / multi-word expression in {target_name})? Typos, gibberish, '
        f'words from a different language, and proper-noun-only strings are NOT real '
        f'{target_name} vocabulary. NEVER invent a translation for them.\n\n'
        f'Return ONLY this JSON (no markdown). If the word is NOT a real {target_name} '
        f'word, set is_real=false and leave examples=[], translation="", memory_tip="":\n'
        f'{{\n'
        f'  "is_real": true|false,\n'
        f'  "translation": "<short translation in {native_name}>",\n'
        f'  "part_of_speech": "noun|verb|adjective|adverb|phrase",\n'
        f'  "difficulty": "A1|A2|B1|B2|C1|C2",\n'
        f'  "examples": [\n'
        f'    {{"sentence": "<example sentence in {target_name}>", "explanation": "<6-10 word usage note in {target_name} ONLY — never a translation>"}},\n'
        f'    {{"sentence": "<example sentence in {target_name}>", "explanation": "<usage note in {target_name}>"}},\n'
        f'    {{"sentence": "<example sentence in {target_name}>", "explanation": "<usage note in {target_name}>"}}\n'
        f'  ],\n'
        f'  "memory_tip": "<max 60 chars mnemonic in {native_name}>",\n'
        f'  "image_keyword": "<single English noun for image search>"\n'
        f'}}\n\n'
        f'Rules: examples and their explanations MUST be in {target_name} only — '
        f'explanation is a brief usage note (situation/context), NEVER a translation. '
        f'Memory tip is in {native_name}. Translation is in {native_name}. '
        f'Max 10 words per example, max 10 words per explanation, no quotes inside strings.'
    )


async def _cache_lookup(word: str, target_lang: str, native_lang: str) -> dict | None:
    """Шукає попередньо згенеровану відповідь у кеші."""
    try:
        from sqlalchemy import select
        from .db import SessionLocal
        from .models import AiCache
        async with SessionLocal() as session:
            result = await session.execute(
                select(AiCache.data).where(
                    AiCache.word == word,
                    AiCache.target_lang == target_lang,
                    AiCache.native_lang == native_lang,
                )
            )
            return result.scalar_one_or_none()
    except Exception as e:
        logger.warning(f"Cache lookup failed: {e}")
        return None


async def _cache_store(word: str, target_lang: str, native_lang: str, data: dict) -> None:
    """Зберігає відповідь у кеш. Помилки логуються, не валять флоу."""
    try:
        from sqlalchemy.exc import IntegrityError
        from .db import SessionLocal
        from .models import AiCache
        async with SessionLocal() as session:
            session.add(AiCache(
                word=word, target_lang=target_lang,
                native_lang=native_lang, data=data,
            ))
            try:
                await session.commit()
            except IntegrityError:
                pass  # Паралельний запит уже закешував
    except Exception as e:
        logger.warning(f"Cache store failed: {e}")


async def _ask_openai_once(
    word: str, target_lang: str, native_lang: str
) -> WordData | None:
    """Один сирий виклик OpenAI з валідацією. None при будь-якій помилці."""
    try:
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": build_user_prompt(word, target_lang, native_lang)},
            ],
            response_format={"type": "json_object"},
            temperature=0.5,
            max_tokens=400,
        )

        content = response.choices[0].message.content
        if not content:
            logger.error("OpenAI returned empty content")
            return None

        data = json.loads(content)

        # AI вирішив, що слова не існує у target_lang — повертаємо як є,
        # callers покажуть friendly помилку. Кешуємо, щоб не повторювати call.
        if data.get("is_real") is False:
            logger.info(f"OpenAI flagged '{word}' as not-real in {target_lang}")
            data.setdefault("translation", "")
            data.setdefault("examples", [])
            return data

        if not data.get("translation"):
            logger.error(
                f"OpenAI missing translation for '{word}' ({target_lang}/{native_lang}). "
                f"Raw keys: {list(data.keys())} content[:200]={content[:200]!r}"
            )
            return None

        if not isinstance(data.get("examples"), list):
            logger.warning(f"OpenAI returned non-list examples for '{word}', defaulting to []")
            data["examples"] = []

        if not data.get("image_keyword"):
            data["image_keyword"] = word

        # Коли is_real явно не виставлений, default true — це валідне слово
        data.setdefault("is_real", True)

        if response.usage:
            tokens = response.usage.total_tokens
            cost = (response.usage.prompt_tokens * 0.00015 +
                    response.usage.completion_tokens * 0.0006) / 1000
            logger.info(f"OpenAI: {tokens} tokens, ~${cost:.5f}")

        return data

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON for '{word}': {e}")
        return None
    except Exception as e:
        logger.error(f"OpenAI error for '{word}': {e}")
        return None


async def get_word_data(word: str, target_lang: str, native_lang: str = "uk") -> WordData | None:
    """Запитує OpenAI про слово, кешує. До 2 спроб для усунення транзиентних
    збоїв (timeout / порожній content / occasional invalid JSON)."""
    import asyncio as _aio

    word = word.strip().lower()

    if not word:
        return None
    if len(word) > 100:
        logger.warning(f"Word too long: {len(word)} chars")
        return None

    # ⚡ Cache hit — повертаємо за ~50 мс замість 3 сек OpenAI
    cached = await _cache_lookup(word, target_lang, native_lang)
    if cached:
        logger.info(f"AI cache HIT: '{word}' ({target_lang}/{native_lang})")
        return cached

    data = await _ask_openai_once(word, target_lang, native_lang)
    if data is None:
        logger.info(f"OpenAI retry for '{word}' ({target_lang}/{native_lang})")
        await _aio.sleep(0.4)
        data = await _ask_openai_once(word, target_lang, native_lang)
    if data is None:
        return None

    _aio.create_task(_cache_store(word, target_lang, native_lang, data))
    return data
