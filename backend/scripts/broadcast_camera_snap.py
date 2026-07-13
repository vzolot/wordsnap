"""One-time broadcast: «Тепер можна фотографувати слова прямо в застосунку».

Продакт-апдейт про НОВУ фічу — жива камера в Mini App: відкрий застосунок,
натисни 📷, наведи на книжку/меню/вивіску/статтю → WordSnap витягує іноземні
слова → тап і вони у словнику з перекладом, прикладами й картинкою. (На відміну
від старого флоу «надішли скрін/голосове в чат» — тут камера прямо в додатку.)

Кожне повідомлення має inline web_app кнопку, що відкриває Mini App одразу.
Throttling ~20 msg/sec (безпечно під Telegram 30/sec). Респектує блокування/
ChatNotFound. analytics `broadcast_received` з broadcast_id (anti-double-send).

Usage:
  python -m scripts.broadcast_camera_snap --dry-run          # тільки лічильник
  python -m scripts.broadcast_camera_snap --test 469478065   # прев'ю одному
  python -m scripts.broadcast_camera_snap --mode all --send  # реальний пуш
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from collections import Counter
from datetime import datetime, timezone

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramRetryAfter,
)
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from sqlalchemy import select

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import analytics  # noqa: E402
from core.constants import MINI_APP_URL  # noqa: E402
from core.db import SessionLocal  # noqa: E402
from core.models import User  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")
logger = logging.getLogger("broadcast_camera")

BROADCAST_ID = "camera_snap_2026_07_13"
RATE_LIMIT_DELAY_SEC = 0.05   # ~20 msg/sec
MAX_USERS_PER_RUN = 10000

# CTA на кнопці (web_app) — по мові.
CTA: dict[str, str] = {
    "uk": "📸 Відкрити WordSnap",
    "en": "📸 Open WordSnap",
    "es": "📸 Abrir WordSnap",
    "pl": "📸 Otwórz WordSnap",
    "de": "📸 WordSnap öffnen",
    "fr": "📸 Ouvrir WordSnap",
}

COPY: dict[str, str] = {
    "uk": (
        "📸 <b>Тепер можна фотографувати слова прямо в застосунку</b>\n\n"
        "Відкрий WordSnap і натисни 📷 — наведи камеру на книжку, меню, "
        "вивіску чи статтю, і я сам витягну іноземні слова.\n\n"
        "Обери потрібні — і вони додадуться з перекладом, прикладами й "
        "картинкою. Живе фото прямо в додатку, без скрінів.\n\n"
        "Спробуй зараз 👇"
    ),
    "en": (
        "📸 <b>You can now snap words with your camera — right inside the app</b>\n\n"
        "Open WordSnap and tap 📷 — point your camera at a book, menu, sign or "
        "article, and I'll pull out the foreign-language words.\n\n"
        "Pick the ones you want and they're saved with translation, examples and "
        "an image. A live photo right in the app — no screenshots needed.\n\n"
        "Try it now 👇"
    ),
    "es": (
        "📸 <b>Ahora puedes capturar palabras con tu cámara, dentro de la app</b>\n\n"
        "Abre WordSnap y toca 📷 — apunta la cámara a un libro, menú, cartel o "
        "artículo, y extraeré las palabras del idioma que aprendes.\n\n"
        "Elige las que quieras y se guardan con traducción, ejemplos e imagen. "
        "Foto en vivo dentro de la app, sin capturas.\n\n"
        "Pruébalo ahora 👇"
    ),
    "pl": (
        "📸 <b>Możesz już fotografować słowa prosto w aplikacji</b>\n\n"
        "Otwórz WordSnap i stuknij 📷 — skieruj aparat na książkę, menu, szyld "
        "lub artykuł, a wyciągnę słowa w języku, którego się uczysz.\n\n"
        "Wybierz te, które chcesz — zapiszą się z tłumaczeniem, przykładami i "
        "obrazkiem. Zdjęcie na żywo w aplikacji, bez zrzutów ekranu.\n\n"
        "Spróbuj teraz 👇"
    ),
    "de": (
        "📸 <b>Du kannst Wörter jetzt mit der Kamera aufnehmen — direkt in der App</b>\n\n"
        "Öffne WordSnap und tippe auf 📷 — richte die Kamera auf ein Buch, eine "
        "Speisekarte, ein Schild oder einen Artikel, und ich hole die Wörter "
        "deiner Lernsprache heraus.\n\n"
        "Wähle die gewünschten aus — sie werden mit Übersetzung, Beispielen und "
        "Bild gespeichert. Live-Foto direkt in der App, ohne Screenshots.\n\n"
        "Probier es jetzt 👇"
    ),
    "fr": (
        "📸 <b>Vous pouvez maintenant photographier des mots directement dans l'app</b>\n\n"
        "Ouvrez WordSnap et touchez 📷 — pointez la caméra sur un livre, un menu, "
        "une enseigne ou un article, et j'extrais les mots de la langue apprise.\n\n"
        "Choisissez ceux que vous voulez — ils sont enregistrés avec traduction, "
        "exemples et image. Photo en direct dans l'app, sans captures.\n\n"
        "Essayez maintenant 👇"
    ),
}


def _kb(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=CTA.get(lang) or CTA["en"], web_app=WebAppInfo(url=MINI_APP_URL)),
    ]])


async def _eligible_users(mode: str) -> list[User]:
    """active — reviews>0; catchup — reviews=0; all — усі, окрім тестових.
    ЛИШЕ тенант 1 (WordSnap): бот @WordSnapBot; учні white-label тенантів
    спілкуються зі СВОЇМИ ботами, тож їм цю розсилку слати не можна."""
    async with SessionLocal() as session:
        q = select(User).where(
            User.tenant_id == 1,
            User.is_test_account.is_(False),
        )
        if mode == "active":
            q = q.where(User.total_reviews > 0)
        elif mode == "catchup":
            q = q.where(User.total_reviews == 0)
        elif mode != "all":
            raise ValueError(f"unknown mode: {mode}")
        return list((await session.execute(q)).scalars().all())


async def _send_one(bot: Bot, user: User) -> str:
    lang = user.native_lang or "uk"
    text = COPY.get(lang) or COPY["en"]
    try:
        await bot.send_message(chat_id=user.telegram_id, text=text, reply_markup=_kb(lang))
        analytics.capture(user.telegram_id, "broadcast_received", {
            "broadcast_id": BROADCAST_ID, "native_lang": lang,
        })
        return "sent"
    except TelegramForbiddenError:
        return "blocked"
    except TelegramRetryAfter as e:
        wait = int(e.retry_after) + 1
        logger.warning("RetryAfter %ds for %s", wait, user.telegram_id)
        await asyncio.sleep(wait)
        try:
            await bot.send_message(chat_id=user.telegram_id, text=text, reply_markup=_kb(lang))
            return "sent_after_retry"
        except Exception as exc:
            logger.warning("retry failed %s: %s", user.telegram_id, exc)
            return "retry_failed"
    except TelegramBadRequest as e:
        msg = str(e).lower()
        if "chat not found" in msg or "bot was blocked" in msg or "user is deactivated" in msg:
            return "unreachable"
        logger.warning("bad_request %s: %s", user.telegram_id, e)
        return "bad_request"
    except Exception as exc:
        logger.warning("unexpected %s: %s", user.telegram_id, exc)
        return "error"


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--test", type=int, metavar="TG_ID", help="preview to one telegram_id")
    parser.add_argument("--send", action="store_true", help="actually broadcast")
    parser.add_argument("--mode", choices=("active", "catchup", "all"), default="all")
    args = parser.parse_args()

    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        print("ERROR: TELEGRAM_BOT_TOKEN env var missing", file=sys.stderr)
        sys.exit(2)
    bot = Bot(token=token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))

    if args.test:
        async with SessionLocal() as session:
            user = (await session.execute(
                select(User).where(User.telegram_id == args.test).limit(1)
            )).scalars().first()
        if not user:
            class _Stub:
                telegram_id = args.test
                native_lang = "uk"
            user = _Stub()  # type: ignore
            print(f"User {args.test} not in DB, sending with native_lang=uk")
        else:
            print(f"User {args.test}: native_lang={user.native_lang}")
        print(f"Test send: {await _send_one(bot, user)}")
        await bot.session.close()
        return

    users = await _eligible_users(args.mode)
    counts = Counter([(u.native_lang or "uk") for u in users])
    print(f"Eligible users (mode={args.mode}): {len(users)}")
    for lang, n in sorted(counts.items()):
        print(f"  {lang}: {n}")

    if args.dry_run or not args.send:
        if not args.dry_run:
            print("\nPass --send to broadcast, --test <tg_id> for preview.")
        await bot.session.close()
        return

    if len(users) > MAX_USERS_PER_RUN:
        print(f"ABORT: too many users ({len(users)} > {MAX_USERS_PER_RUN}).")
        await bot.session.close()
        return

    started = datetime.now(timezone.utc)
    stats: Counter = Counter()
    total = len(users)
    print(f"\nStarting broadcast: {total} users, ~{int(total * (RATE_LIMIT_DELAY_SEC + 0.05))}s ETA")
    for i, u in enumerate(users, 1):
        stats[await _send_one(bot, u)] += 1
        if i % 25 == 0 or i == total:
            elapsed = (datetime.now(timezone.utc) - started).total_seconds()
            print(f"  {i}/{total} ({elapsed:.0f}s) — {dict(stats)}")
        await asyncio.sleep(RATE_LIMIT_DELAY_SEC)
    print(f"\nDONE: {dict(stats)}")
    await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
