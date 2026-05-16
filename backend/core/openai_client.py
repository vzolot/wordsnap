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
    "fr": "French",
}

# Lazily-created OpenAI client. This used to be a module-level
# `AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))` — but the OpenAI SDK raises
# if the key is missing, so an unset OPENAI_API_KEY crashed the *whole* backend
# on import (bot + API + schedulers), not just word resolution. Creating it on
# first use means a missing key now only disables word resolution (the error
# bubbles into `_ask_openai_once`'s existing try/except → None → callers show a
# friendly message) while everything else keeps running.
_openai_client: AsyncOpenAI | None = None


def _get_openai_client() -> AsyncOpenAI:
    global _openai_client
    if _openai_client is None:
        key = os.getenv("OPENAI_API_KEY")
        if not key:
            raise RuntimeError("OPENAI_API_KEY is not set — word resolution unavailable")
        _openai_client = AsyncOpenAI(api_key=key)
    return _openai_client


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
        response = await _get_openai_client().chat.completions.create(
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


# ── Snap from screenshot / voice ─────────────────────────────────────────
#
# Дві нові точки входу для додавання слів: фото переписки і голосова. Логіка
# та сама: витягаємо КАНДИДАТІВ (слова/короткі фрази у `target_lang`) → у
# хендлері показуємо їх кнопками → юзер тапає → нормальний `get_word_data` +
# save_word pipeline (з кешем, лімітом, картинкою). Тобто це лише ETL над
# вхідним джерелом — продуктовий funnel не дублюється.

_EXTRACT_SYSTEM = (
    "You help language learners add real-life vocabulary. The user is "
    "learning a specific target language and just shared content (a chat "
    "screenshot or a voice transcript) where this language appears. Your "
    "job: extract up to 8 standalone words or short fixed phrases (1-3 "
    "words) in that target language that a learner would actually want "
    "to add to flashcards. Hard rules:\n"
    "  - Only words that appear in the target language (skip the learner's "
    "native language even if it's present).\n"
    "  - Skip proper names, place names, numbers, dates, URLs, emoji, "
    "Telegram-UI clutter (timestamps, reply-to badges, ✓ marks).\n"
    "  - Skip extremely common particles/articles unless they appear as a "
    "tricky form ('haben gehabt', 'było by').\n"
    "  - Prefer 'tricky for a foreigner': false friends, idioms, region "
    "vocabulary, register-specific words. Avoid overlap with the user's "
    "native language obvious cognates.\n"
    "  - Return BASE form when reasonable (infinitive verbs, nominative "
    "nouns), unless the inflected form itself is the learning point.\n"
    "  - Output JSON only: {\"words\": [\"word1\", \"word2\", ...]}. If the "
    "source has no extractable vocab in the target language, return "
    "{\"words\": []}."
)


async def extract_words_from_image(
    image_b64: str,
    target_lang: str,
    native_lang: str = "uk",
    image_mime: str = "image/jpeg",
) -> list[str]:
    """Vision-екстракт: дивиться на скрін, повертає до 8 слів у target_lang.

    `image_b64` — base64-кодоване зображення без data-URL префіксу.
    Повертає список нормалізованих рядків (нижній регістр, тримером).
    """
    try:
        response = await _get_openai_client().chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": _EXTRACT_SYSTEM},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                f"Target language: {target_lang}. "
                                f"Native language: {native_lang}. "
                                f"Extract from this screenshot."
                            ),
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{image_mime};base64,{image_b64}",
                                "detail": "low",
                            },
                        },
                    ],
                },
            ],
            response_format={"type": "json_object"},
            temperature=0.3,
            max_tokens=300,
        )
        content = response.choices[0].message.content or "{}"
        data = json.loads(content)
    except Exception as e:
        logger.warning("vision extract failed: %s", e)
        return []

    raw = data.get("words") or []
    out: list[str] = []
    seen: set[str] = set()
    for w in raw:
        if not isinstance(w, str):
            continue
        w = w.strip().strip("«».,!?;:\"'`").lower()
        if not (2 <= len(w) <= 60):
            continue
        if w in seen:
            continue
        seen.add(w)
        out.append(w)
        if len(out) >= 8:
            break
    return out


# Відомі Whisper-галюцинації для коротких/тихих аудіо — модель вкидає
# music/intro/outro маркери замість «це тиша». Якщо transcript збігається з
# одним з них, вважаємо аудіо нерозшифрованим.
_WHISPER_HALLUCINATIONS = (
    "music outro",
    "music intro",
    "outro music",
    "intro music",
    "[music]",
    "♪",
    "🎵",
    "🎶",
    "thanks for watching",
    "thank you for watching",
    "subscribe",
    "like and subscribe",
    "see you next time",
    "[applause]",
    "[laughter]",
)


def _looks_like_whisper_hallucination(text: str) -> bool:
    t = (text or "").strip().lower()
    if not t:
        return True
    if len(t) < 4:
        return True
    # Точне виключення — короткий текст, що цілком вкладається в один маркер
    if len(t) < 40:
        for m in _WHISPER_HALLUCINATIONS:
            if m in t:
                return True
    return False


async def transcribe_voice(
    audio_bytes: bytes, filename: str = "voice.ogg"
) -> tuple[str, str | None]:
    """Whisper-транскрипт. Auto-detect мови. Повертає (text, lang_iso639_1).

    Якщо Whisper повернув одну з відомих галюцинацій (Music Outro / Thanks
    for watching і подібне — поведінка коли аудіо коротке/тихе), повертаємо
    порожній text, щоб handler показав friendly «спробуйте ще раз».

    Передаємо `prompt` — bias-нагадування що це людська мова з реальними
    словами, не музика чи фоновий шум. Помітно скорочує hallucinate-rate
    на коротких записах.
    """
    try:
        resp = await _get_openai_client().audio.transcriptions.create(
            model="whisper-1",
            file=(filename, audio_bytes),
            response_format="verbose_json",
            prompt=(
                "Real human speech: vocabulary words, phrases, or sentences "
                "in a foreign language being learned by the speaker. "
                "Not music, not silence, not background noise."
            ),
        )
    except Exception as e:
        logger.warning("whisper transcribe failed: %s", e)
        return "", None
    text = (getattr(resp, "text", "") or "").strip()
    detected = getattr(resp, "language", None)
    if _looks_like_whisper_hallucination(text):
        logger.info("whisper output flagged as hallucination: %r", text[:80])
        return "", detected
    return text, detected


async def extract_words_from_transcript(
    transcript: str, target_lang: str, native_lang: str = "uk"
) -> list[str]:
    """Той самий екстракт, але з voice-транскрипту (без зображення)."""
    if not transcript or not transcript.strip():
        return []
    try:
        response = await _get_openai_client().chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": _EXTRACT_SYSTEM},
                {
                    "role": "user",
                    "content": (
                        f"Target language: {target_lang}. "
                        f"Native language: {native_lang}. "
                        f"Voice transcript:\n\n{transcript[:3000]}"
                    ),
                },
            ],
            response_format={"type": "json_object"},
            temperature=0.3,
            max_tokens=300,
        )
        content = response.choices[0].message.content or "{}"
        data = json.loads(content)
    except Exception as e:
        logger.warning("transcript extract failed: %s", e)
        return []

    raw = data.get("words") or []
    out: list[str] = []
    seen: set[str] = set()
    for w in raw:
        if not isinstance(w, str):
            continue
        w = w.strip().strip("«».,!?;:\"'`").lower()
        if not (2 <= len(w) <= 60):
            continue
        if w in seen:
            continue
        seen.add(w)
        out.append(w)
        if len(out) >= 8:
            break
    return out
