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
            
            # Беремо середній розмір (1080px), щоб не вантажити велике
            photo = results[0]
            image_url = photo.get("urls", {}).get("regular")
            
            logger.info(f"Unsplash image found for '{keyword}'")
            return image_url
            
    except httpx.TimeoutException:
        logger.error(f"Unsplash timeout for: {keyword}")
        return None
    except Exception as e:
        logger.error(f"Unsplash error: {e}")
        return None