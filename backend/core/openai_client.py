"""
OpenAI integration для генерації перекладів і прикладів.
Використовує gpt-4o-mini — найдешевший і досить розумний модель.
"""
import os
import json
import logging
from typing import TypedDict
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Назви мов для промпту
LANGUAGE_NAMES = {
    "uk": "Ukrainian",
    "en": "English",
    "es": "Spanish",
    "pl": "Polish",
}

# Ініціалізація клієнта
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


SYSTEM_PROMPT = """You are a language learning assistant for the WordSnap app.
You help users learn vocabulary through context-rich examples.
Always respond with valid JSON only, no markdown, no extra text."""


def build_user_prompt(word: str, target_lang: str, native_lang: str = "uk") -> str:
    """Будує промпт для OpenAI"""
    target_name = LANGUAGE_NAMES.get(target_lang, "English")
    native_name = LANGUAGE_NAMES.get(native_lang, "Ukrainian")
    
    return f"""Word/phrase to learn: "{word}"
Target language: {target_name}
User's native language: {native_name}

Return ONLY valid JSON in this exact format:
{{
  "translation": "translation in {native_name}",
  "part_of_speech": "noun|verb|adjective|adverb|phrase",
  "difficulty": "A1|A2|B1|B2|C1|C2",
  "examples": [
    {{
      "sentence": "Example sentence in {target_name}",
      "explanation": "Brief context in {target_name}"
    }},
    {{
      "sentence": "Second example in {target_name}",
      "explanation": "Explanation in {target_name}"
    }},
    {{
      "sentence": "Third example in {target_name}",
      "explanation": "Explanation in {target_name}"
    }}
  ],
  "memory_tip": "Mnemonic or association in {target_name}, max 100 chars",
  "image_keyword": "single concrete English noun for image search"
}}

Rules:
- Examples must be everyday B1-B2 level sentences
- 3 examples with varied contexts (work, daily life, conversations)
- Memory tip: word association, etymology, or visual hint
- image_keyword: concrete depictable thing (object, scene, action)
- If the word has multiple meanings, focus on the most common one"""


async def get_word_data(word: str, target_lang: str, native_lang: str = "uk") -> WordData | None:
    """
    Запитує OpenAI про слово і повертає структуровані дані.
    Повертає None якщо щось пішло не так.
    """
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
            response_format={"type": "json_object"},  # Гарантує валідний JSON
            temperature=0.7,
            max_tokens=800,
        )
        
        content = response.choices[0].message.content
        if not content:
            logger.error("OpenAI returned empty content")
            return None
        
        data = json.loads(content)
        
        # Валідація ключових полів
        required = ["translation", "examples", "image_keyword"]
        if not all(key in data for key in required):
            logger.error(f"Missing required fields in response: {data}")
            return None
        
        if not isinstance(data["examples"], list) or len(data["examples"]) < 1:
            logger.error("Invalid examples in response")
            return None
        
        # Логуємо вартість
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