"""Тест Unsplash"""
import asyncio
from core.unsplash_client import search_image


async def test():
    keywords = ["sunset", "butterfly", "discovery", "meeting"]
    
    for kw in keywords:
        url = await search_image(kw)
        if url:
            print(f"✅ '{kw}': {url[:80]}...")
        else:
            print(f"❌ '{kw}': not found")


if __name__ == "__main__":
    asyncio.run(test())