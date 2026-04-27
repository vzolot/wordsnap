"""
Тест OpenAI інтеграції.
Запусти: python test_openai.py
"""
import asyncio
import json
from core.openai_client import get_word_data


async def test():
    # Тестове слово
    test_words = [
        ("ephemeral", "en"),
        ("serendipity", "en"),
        ("madrugada", "es"),
    ]
    
    for word, lang in test_words:
        print(f"\n{'='*60}")
        print(f"🔍 Слово: '{word}' (target: {lang})")
        print('='*60)
        
        data = await get_word_data(word, target_lang=lang, native_lang="uk")
        
        if data is None:
            print("❌ OpenAI не зміг обробити слово")
            continue
        
        print(f"📝 Переклад: {data.get('translation')}")
        print(f"📚 Частина мови: {data.get('part_of_speech')}")
        print(f"📊 Рівень: {data.get('difficulty')}")
        print(f"\n📖 Приклади:")
        for i, ex in enumerate(data.get('examples', []), 1):
            print(f"  {i}. {ex.get('sentence')}")
            print(f"     → {ex.get('explanation')}")
        print(f"\n💡 Memory tip: {data.get('memory_tip')}")
        print(f"🖼️  Image keyword: {data.get('image_keyword')}")


if __name__ == "__main__":
    asyncio.run(test())