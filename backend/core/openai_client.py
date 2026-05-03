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
        f'Return ONLY this JSON (no markdown):\n'
        f'{{\n'
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


async def get_word_data(word: str, target_lang: str, native_lang: str = "uk") -> WordData | None:
    """Запитує OpenAI про слово і повертає структуровані дані."""
    word = word.strip().lower()

    if not word:
        return None

    if len(word) > 100:
        logger.warning(f"Word too long: {len(word)} chars")
        return None

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

        required = ["translation", "examples", "image_keyword"]
        if not all(key in data for key in required):
            logger.error(f"Missing required fields in response: {data}")
            return None

        if not isinstance(data["examples"], list) or len(data["examples"]) < 1:
            logger.error("Invalid examples in response")
            return None

        if response.usage:
            tokens = response.usage.total_tokens
            cost = (response.usage.prompt_tokens * 0.00015 +
                    response.usage.completion_tokens * 0.0006) / 1000
            logger.info(f"OpenAI: {tokens} tokens, ~${cost:.5f}")

        return data

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON: {e}")
        return None
    except Exception as e:
        logger.error(f"OpenAI error: {e}")
        return None
