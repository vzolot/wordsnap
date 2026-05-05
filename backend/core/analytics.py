"""PostHog event tracking з graceful fallback.

Якщо POSTHOG_API_KEY не встановлений — всі capture/identify стають no-op,
без помилок. Це дозволяє локально/у dev запускати без аналітики.

Важливо: ВСІ події що записуються тут — серверні. Враховуй що тут немає
автоматичного device/browser трекінгу — для UI-подій використовуй
miniapp/src/utils/analytics.js.
"""
import logging
import os
from typing import Any

from posthog import Posthog

logger = logging.getLogger(__name__)

_API_KEY = os.getenv("POSTHOG_API_KEY")
_HOST = os.getenv("POSTHOG_HOST", "https://eu.posthog.com")

_client: Posthog | None = None
if _API_KEY:
    try:
        _client = Posthog(project_api_key=_API_KEY, host=_HOST)
        # Без цього бекенд може блокуватись при шатдауні — async flush лише
        _client.disabled = False
        logger.info(f"📊 PostHog initialized (host={_HOST})")
    except Exception as e:
        logger.warning(f"PostHog init failed: {e}")
        _client = None
else:
    logger.info("📊 PostHog disabled (no POSTHOG_API_KEY set)")


def capture(
    distinct_id: int | str,
    event: str,
    properties: dict[str, Any] | None = None,
) -> None:
    """Записує подію. Тихо ігнорується якщо PostHog не налаштований."""
    if not _client:
        return
    try:
        _client.capture(
            distinct_id=str(distinct_id),
            event=event,
            properties=properties or {},
        )
    except Exception as e:
        logger.warning(f"PostHog capture failed ({event}): {e}")


def identify(
    distinct_id: int | str,
    properties: dict[str, Any] | None = None,
) -> None:
    """Оновлює властивості юзера (мова, план тощо)."""
    if not _client:
        return
    try:
        _client.identify(
            distinct_id=str(distinct_id),
            properties=properties or {},
        )
    except Exception as e:
        logger.warning(f"PostHog identify failed: {e}")


def shutdown() -> None:
    if _client:
        try:
            _client.shutdown()
        except Exception:
            pass
