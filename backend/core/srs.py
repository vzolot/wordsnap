"""
Spaced Repetition System (SRS) — алгоритм SM-2.
Вирішує коли наступного разу показати слово юзеру.

Принцип:
- Знав легко → інтервал зростає (× ease_factor)
- Згадав з зусиллям → інтервал зростає повільніше (× 1.3)
- Забув → інтервал = 1 день, починаємо спочатку
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Literal

logger = logging.getLogger(__name__)

ReviewResult = Literal["knew", "struggled", "forgot"]

# Константи алгоритму
MIN_EASE_FACTOR = 1.3
MAX_EASE_FACTOR = 3.5
EASE_INCREMENT_KNEW = 0.1
EASE_INCREMENT_FORGOT = -0.2

# Етапи (для display)
LEARNING_THRESHOLD = 21  # після 21 дня інтервалу → mastered


def calculate_next_review(
    result: ReviewResult,
    current_interval: float,
    current_ease: float,
    review_count: int,
) -> tuple[float, float, datetime, str]:
    """
    Обчислює новий інтервал на основі відповіді юзера.
    
    Returns: (new_interval_days, new_ease_factor, next_review_datetime, new_status)
    """
    new_ease = current_ease
    
    if result == "knew":
        # Знав легко
        if review_count == 0:
            new_interval = 3.0  # перший раз правильно → 3 дні
        elif review_count == 1:
            new_interval = 7.0  # другий раз → тиждень
        else:
            new_interval = current_interval * current_ease
        
        new_ease = min(current_ease + EASE_INCREMENT_KNEW, MAX_EASE_FACTOR)
        
    elif result == "struggled":
        # Згадав з зусиллям
        if review_count == 0:
            new_interval = 1.5
        else:
            new_interval = current_interval * 1.3
        # ease не змінюється
        
    elif result == "forgot":
        # Забув — починаємо спочатку
        new_interval = 1.0
        new_ease = max(current_ease + EASE_INCREMENT_FORGOT, MIN_EASE_FACTOR)
    
    else:
        raise ValueError(f"Unknown result: {result}")
    
    # Обмежуємо інтервал розумними межами
    new_interval = min(new_interval, 365.0)  # максимум рік
    
    # Обчислюємо дату наступного повторення
    next_review = datetime.now(timezone.utc) + timedelta(days=new_interval)
    
    # Визначаємо статус
    new_status = "mastered" if new_interval >= LEARNING_THRESHOLD else "learning"
    
    return new_interval, new_ease, next_review, new_status


def format_interval(days: float) -> str:
    """Перетворює інтервал у людську мову"""
    if days < 1:
        hours = int(days * 24)
        return f"{hours} год"
    elif days < 7:
        return f"{int(days)} {'день' if int(days) == 1 else 'дні' if 2 <= int(days) <= 4 else 'днів'}"
    elif days < 30:
        weeks = int(days / 7)
        return f"{weeks} тижд"
    elif days < 365:
        months = int(days / 30)
        return f"{months} міс"
    else:
        return "1+ рік"