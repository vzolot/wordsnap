"""
Unsplash integration для пошуку картинок до слів.
Безкоштовно: 50 запитів/годину.
"""
import os
import logging
import httpx
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

UNSPLASH_ACCESS_KEY = os.getenv("UNSPLASH_ACCESS_KEY")
UNSPLASH_API_URL = "https://api.unsplash.com"


async def search_image(keyword: str) -> str | None:
    """
    Шукає картинку на Unsplash за ключовим словом.
    Повертає URL картинки або None.
    """
    if not UNSPLASH_ACCESS_KEY:
        logger.warning("UNSPLASH_ACCESS_KEY не встановлений")
        return None
    
    if not keyword or not keyword.strip():
        return None
    
    keyword = keyword.strip().lower()
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{UNSPLASH_API_URL}/search/photos",
                params={
                    "query": keyword,
                    "per_page": 1,
                    "orientation": "landscape",
                    "content_filter": "high",  # Фільтр контенту
                },
                headers={
                    "Authorization": f"Client-ID {UNSPLASH_ACCESS_KEY}",
                    "Accept-Version": "v1",
                }
            )
            
            if response.status_code != 200:
                logger.error(f"Unsplash API error: {response.status_code} {response.text[:200]}")
                return None
            
            data = response.json()
            results = data.get("results", [])
            
            if not results:
                logger.info(f"No Unsplash results for: {keyword}")
                return None

            # Зразу беремо raw і додаємо контрольовані параметри:
            # - w=600 (точно під розмір картки в мобілі) — у 2-4 рази менше
            #   байтів ніж 'regular' (1080px)
            # - q=75 (sweet-spot якості/розміру)
            # - auto=format → WebP/AVIF на сучасних браузерах (-25% bytes)
            # - fit=crop → uniform aspect ratio
            photo = results[0]
            urls = photo.get("urls", {}) or {}
            raw = urls.get("raw")
            if raw:
                image_url = f"{raw}&w=600&h=400&fit=crop&auto=format&q=75"
            else:
                # Fallback якщо raw нема — стара поведінка
                image_url = urls.get("regular")

            logger.info(f"Unsplash image found for '{keyword}'")
            return image_url
            
    except httpx.TimeoutException:
        logger.error(f"Unsplash timeout for: {keyword}")
        return None
    except Exception as e:
        logger.error(f"Unsplash error: {e}")
        return None