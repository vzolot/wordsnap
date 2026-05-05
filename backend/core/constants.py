"""Shared constants."""
import os

MINI_APP_URL = "https://miniapp-omega-three.vercel.app"
REMINDER_COOLDOWN_HOURS = 6
# Username бота для генерування referral-посилань (без @, наприклад "wordsnap_bot")
BOT_USERNAME = os.getenv("BOT_USERNAME", "WordSnap_bot")
