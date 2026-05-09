"""Shared constants."""
import os

MINI_APP_URL = "https://miniapp-omega-three.vercel.app"
REMINDER_COOLDOWN_HOURS = 6


def bot_username() -> str:
    """Username бота без @ — для referral-посилань. На старті резолвиться
    через getMe у bot/main.py і пишеться в os.environ['BOT_USERNAME'],
    тому тут читаємо лазі-функцією, а не модульною константою."""
    return os.getenv("BOT_USERNAME") or "WordSnapBot"


def admin_telegram_id() -> int | None:
    """Telegram ID адміна — кому шлемо щоденні /stats звіти і хто
    може викликати команду /stats у боті. Повертає None якщо не задано."""
    raw = os.getenv("ADMIN_TELEGRAM_ID", "").strip()
    try:
        return int(raw) if raw else None
    except ValueError:
        return None
