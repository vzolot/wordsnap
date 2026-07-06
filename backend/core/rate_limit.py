"""Простий in-memory rate limiter (fixed sliding window). Процес один
(Railway), тож пам'яті достатньо. Захищає завантаження колод від випадкового
спаму парсера (напр. цикл на клієнті)."""
from __future__ import annotations

import time
from collections import defaultdict

_hits: dict[str, list[float]] = defaultdict(list)


def allow(key: str, limit: int, window_s: float) -> bool:
    """True якщо дія дозволена; інкрементує лічильник. False коли ліміт
    вичерпано у вікні window_s."""
    now = time.monotonic()
    cutoff = now - window_s
    q = _hits[key]
    q[:] = [t for t in q if t >= cutoff]  # прибираємо застарілі відмітки
    if len(q) >= limit:
        return False
    q.append(now)
    return True
