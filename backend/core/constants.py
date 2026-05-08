"""Shared constants."""
import os

MINI_APP_URL = "https://miniapp-omega-three.vercel.app"
REMINDER_COOLDOWN_HOURS = 6


def bot_username() -> str:
    """Username бота без @ — для referral-посилань. На старті резолвиться
    через getMe у bot/main.py і пишеться в os.environ['BOT_USERNAME'],
    тому тут читаємо лазі-функцією, а не модульною константою."""
    return os.getenv("BOT_USERNAME") or "WordSnapBot"
