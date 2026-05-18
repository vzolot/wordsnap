"""One-time broadcast: «WordSnap навчився читати скріни і голосові».

Шле теплий продакт-апдейт активним юзерам (тим хто хоч раз пройшов
review_submitted) про новий photo/voice-snap flow. Throttling 20 msg/sec
безпечно під Telegram 30/sec global cap. Респектує заблокованих юзерів
і ChatNotFound. Кожне відправлення → analytics event `broadcast_received`
з `broadcast_id=snap_feature_2026_05_17` (anti-double-send + retention-
сегмент пізніше).

Usage:
  python -m scripts.broadcast_snap_feature --dry-run       # тільки лічильник
  python -m scripts.broadcast_snap_feature --test 469478065 # один юзер
  python -m scripts.broadcast_snap_feature --send           # реальний пуш
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
from sqlalchemy import select

# Дозволяємо запускати з кореня проекту як `python -m scripts.broadcast_snap_feature`
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import analytics  # noqa: E402
from core.db import SessionLocal  # noqa: E402
from core.models import User  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")
logger = logging.getLogger("broadcast_snap")

BROADCAST_ID_ACTIVE = "snap_feature_2026_05_17"
BROADCAST_ID_CATCHUP = "snap_feature_catchup_2026_05_18"
RATE_LIMIT_DELAY_SEC = 0.05   # ~20 msg/sec, safe headroom під Telegram 30/sec
MAX_USERS_PER_RUN = 10000     # safety cap

# Per-language copy. Тон - дружній продакт-апдейт. Без агресивного CTA.
COPY: dict[str, str] = {
    "uk": (
        "✨ <b>WordSnap навчився читати скріни і голосові</b>\n\n"
        "Тепер не треба вводити слово вручну: надішліть мені:\n"
        "📸 скрін переписки чи статті\n"
        "🎙 голосове повідомлення фразою мовою, яку вчите\n\n"
        "Я витягну іноземні слова варті додавання у словник - "
        "по тапу на кожне додасться з прикладами і картинкою.\n\n"
        "Спробуйте просто зараз - надішліть мені скрін або голосову."
    ),
    "en": (
        "✨ <b>WordSnap can now read screenshots and voice messages</b>\n\n"
        "No more typing words by hand. Send me:\n"
        "📸 a screenshot of a chat or article\n"
        "🎙 a voice message with a phrase in the language you're learning\n\n"
        "I'll extract the foreign-language words worth adding - one tap "
        "per word and it lands in your dictionary with examples and an image.\n\n"
        "Try it right now - send me a screenshot or a voice message."
    ),
    "es": (
        "✨ <b>WordSnap ahora lee capturas y mensajes de voz</b>\n\n"
        "Ya no necesitas escribir palabras a mano. Envíame:\n"
        "📸 una captura de un chat o artículo\n"
        "🎙 un mensaje de voz con una frase en el idioma que aprendes\n\n"
        "Extraeré las palabras del idioma objetivo que vale la pena agregar - "
        "un toque por palabra y se guarda con ejemplos e imagen.\n\n"
        "Pruébalo ahora - envíame una captura o mensaje de voz."
    ),
    "pl": (
        "✨ <b>WordSnap potrafi już czytać zrzuty i wiadomości głosowe</b>\n\n"
        "Nie musisz już wpisywać słów ręcznie. Wyślij mi:\n"
        "📸 zrzut ekranu z czatu lub artykułu\n"
        "🎙 wiadomość głosową w języku, którego się uczysz\n\n"
        "Wyciągnę słowa warte dodania w języku docelowym - jedno stuknięcie "
        "i słowo trafia do słownika z przykładami i obrazkiem.\n\n"
        "Spróbuj teraz - wyślij mi zrzut albo nagranie głosowe."
    ),
    "de": (
        "✨ <b>WordSnap kann jetzt Screenshots und Sprachnachrichten lesen</b>\n\n"
        "Keine Wörter mehr manuell tippen. Schick mir:\n"
        "📸 einen Screenshot eines Chats oder Artikels\n"
        "🎙 eine Sprachnachricht in deiner Lernsprache\n\n"
        "Ich hole die Wörter aus deiner Zielsprache heraus, die es zu speichern "
        "lohnt - ein Tap pro Wort und es landet im Wörterbuch mit Beispielen "
        "und Bild.\n\n"
        "Probier es jetzt - schick mir einen Screenshot oder eine Sprachnachricht."
    ),
    "fr": (
        "✨ <b>WordSnap sait maintenant lire les captures et les messages vocaux</b>\n\n"
        "Plus besoin de taper les mots à la main. Envoyez-moi :\n"
        "📸 une capture d'un chat ou d'un article\n"
        "🎙 un message vocal avec une phrase dans la langue que vous apprenez\n\n"
        "Je vais extraire les mots de la langue cible qui valent la peine d'être "
        "ajoutés - un tap par mot et il atterrit dans votre dictionnaire avec "
        "des exemples et une image.\n\n"
        "Essayez maintenant - envoyez-moi une capture ou un message vocal."
    ),
}


async def _eligible_users(mode: str = "active") -> list[User]:
    """active   — користувалися продуктом (review >0). Default з першого launch.
    catchup  — лишилися «застряглі» (review=0): не зробили жодного review,
               але є у БД (зайшли через /start). Шлемо feature-апдейт як
               м'який re-engagement.
    all      — усі (захист на випадок треба зробити масштабну сесію)."""
    async with SessionLocal() as session:
        if mode == "active":
            q = select(User).where(User.total_reviews > 0)
        elif mode == "catchup":
            q = select(User).where(User.total_reviews == 0)
        elif mode == "all":
            q = select(User)
        else:
            raise ValueError(f"unknown mode: {mode}")
        rows = (await session.execute(q)).scalars().all()
        return list(rows)


async def _send_one(bot: Bot, user: User, broadcast_id: str) -> str:
    lang = user.native_lang or "uk"
    text = COPY.get(lang) or COPY["en"]
    try:
        await bot.send_message(chat_id=user.telegram_id, text=text)
        analytics.capture(user.telegram_id, "broadcast_received", {
            "broadcast_id": broadcast_id,
            "native_lang": lang,
        })
        return "sent"
    except TelegramForbiddenError:
        return "blocked"
    except TelegramRetryAfter as e:
        wait = int(e.retry_after) + 1
        logger.warning("RetryAfter %ds for %s", wait, user.telegram_id)
        await asyncio.sleep(wait)
        try:
            await bot.send_message(chat_id=user.telegram_id, text=text)
            analytics.capture(user.telegram_id, "broadcast_received", {
                "broadcast_id": broadcast_id,
                "native_lang": lang,
                "retry_after_s": wait,
            })
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
    parser.add_argument("--dry-run", action="store_true", help="count only, do not send")
    parser.add_argument("--test", type=int, metavar="TG_ID", help="send only to this telegram_id (override DB filter)")
    parser.add_argument("--send", action="store_true", help="actually broadcast to all eligible users")
    parser.add_argument(
        "--mode", choices=("active", "catchup", "all"), default="active",
        help="active=reviews>0 (default), catchup=reviews=0 (re-engage), all=everyone",
    )
    args = parser.parse_args()
    broadcast_id = BROADCAST_ID_CATCHUP if args.mode == "catchup" else BROADCAST_ID_ACTIVE

    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        print("ERROR: TELEGRAM_BOT_TOKEN env var missing", file=sys.stderr)
        sys.exit(2)

    bot = Bot(token=token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))

    if args.test:
        # Test-режим: шлемо ОДНІЙ конкретній людині (зазвичай адмінy для preview).
        async with SessionLocal() as session:
            user = (await session.execute(
                select(User).where(User.telegram_id == args.test)
            )).scalar_one_or_none()
        if not user:
            # Fallback - синтезуємо мінімальний User-об'єкт щоб все одно надіслати.
            class _Stub:
                telegram_id = args.test
                native_lang = "uk"
            user = _Stub()  # type: ignore
            print(f"User {args.test} not in DB, sending with native_lang=uk")
        else:
            print(f"User {args.test}: native_lang={user.native_lang}, plan={user.plan}")
        status = await _send_one(bot, user, broadcast_id)
        print(f"Test send: {status}")
        await bot.session.close()
        return

    users = await _eligible_users(mode=args.mode)
    counts = Counter([(u.native_lang or "uk") for u in users])
    print(f"Eligible users: {len(users)}")
    for lang, n in sorted(counts.items()):
        print(f"  {lang}: {n}")

    if args.dry_run or not args.send:
        if not args.dry_run:
            print("\nPass --send to actually broadcast, --test <tg_id> for preview.")
        await bot.session.close()
        return

    if len(users) > MAX_USERS_PER_RUN:
        print(f"ABORT: too many users ({len(users)} > {MAX_USERS_PER_RUN}). Raise cap if intentional.")
        await bot.session.close()
        return

    started = datetime.now(timezone.utc)
    stats: Counter = Counter()
    total = len(users)
    print(f"\nStarting broadcast: {total} users, ~{int(total * (RATE_LIMIT_DELAY_SEC + 0.05))}s ETA")

    for i, u in enumerate(users, 1):
        status = await _send_one(bot, u, broadcast_id)
        stats[status] += 1
        if i % 25 == 0 or i == total:
            elapsed = (datetime.now(timezone.utc) - started).total_seconds()
            print(f"  {i}/{total} ({elapsed:.0f}s) — {dict(stats)}")
        await asyncio.sleep(RATE_LIMIT_DELAY_SEC)

    print(f"\nDONE: {dict(stats)}")
    await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
