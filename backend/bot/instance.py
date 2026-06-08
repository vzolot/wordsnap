"""Standalone Bot + Dispatcher instances.

Lives separately from `bot/main.py` so that other modules can import the
`bot` instance without triggering re-execution of `main.py`.

The bug this prevents: in production we launch the bot as `python -m bot.main`
(or equivalent), which registers the module under `sys.modules['__main__']`,
NOT `sys.modules['bot.main']`. Any later `from bot.main import bot` (e.g.
inside a FastAPI endpoint that needs to call `create_invoice_link`) is then
seen by Python as a cache miss → it imports `bot/main.py` a SECOND time →
the module body runs again, including `dp.include_router(admin_router)`, and
aiogram raises `RuntimeError: Router is already attached to ...`.

Moving the `Bot` and `Dispatcher` constructors here means both `main.py` and
the FastAPI handlers share the same instance through a normal, idempotent
import — no module-level side effects to re-run.
"""

from __future__ import annotations

import os

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from dotenv import load_dotenv

# Idempotent: harmless if main.py already called it; ensures env is loaded
# when this module is imported first (e.g. from a webhook handler).
load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не знайдено в .env файлі!")

bot = Bot(
    token=TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)
dp = Dispatcher()
