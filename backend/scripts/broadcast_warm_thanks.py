"""One-time broadcast: тепле «дякую» користувачам.

Шле душевне повідомлення-вдячність без CTA і продажу. Throttling 20 msg/sec
безпечно під Telegram 30/sec global cap. Респектує заблокованих юзерів
і ChatNotFound. Кожне відправлення → analytics event `broadcast_received`
з `broadcast_id=warm_thanks_2026_05_29` (anti-double-send + сегмент пізніше).

Usage:
  python -m scripts.broadcast_warm_thanks --dry-run        # тільки лічильник
  python -m scripts.broadcast_warm_thanks --test 469478065 # один юзер (preview)
  python -m scripts.broadcast_warm_thanks --send           # реальний пуш
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

# Дозволяємо запускати з кореня проекту як `python -m scripts.broadcast_warm_thanks`
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import analytics  # noqa: E402
from core.db import SessionLocal  # noqa: E402
from core.models import User  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")
logger = logging.getLogger("broadcast_warm_thanks")

BROADCAST_ID = "warm_thanks_2026_05_29"
RATE_LIMIT_DELAY_SEC = 0.05   # ~20 msg/sec, safe headroom під Telegram 30/sec
MAX_USERS_PER_RUN = 10000     # safety cap

# Per-language copy. Тон — тепле «дякую», без CTA і продажу.
COPY: dict[str, str] = {
    "uk": (
        "✨ <b>Просто хотіли сказати дякую</b>\n\n"
        "Ви вчите нову мову разом із WordSnap — і це справді круто. "
        "Кожне додане слово, кожне повторення наближає вас до моменту, "
        "коли іноземна мова стане своєю.\n\n"
        "Дякуємо, що ви з нами. Ми робимо WordSnap саме для вас 💛\n\n"
        "Гарного дня — і нехай сьогодні додасться ще одне нове слово 😉"
    ),
    "en": (
        "✨ <b>We just wanted to say thank you</b>\n\n"
        "You're learning a new language with WordSnap — and that's genuinely awesome. "
        "Every word you add, every review brings you closer to the moment a foreign "
        "language becomes your own.\n\n"
        "Thank you for being here. We build WordSnap for you 💛\n\n"
        "Have a great day — and may one more new word join your collection today 😉"
    ),
    "es": (
        "✨ <b>Solo queríamos darte las gracias</b>\n\n"
        "Estás aprendiendo un idioma nuevo con WordSnap, y eso es genial de verdad. "
        "Cada palabra que agregas, cada repaso te acerca al momento en que el idioma "
        "extranjero se vuelve tuyo.\n\n"
        "Gracias por estar aquí. Hacemos WordSnap para ti 💛\n\n"
        "Que tengas un gran día — y que hoy se sume una palabra nueva más 😉"
    ),
    "pl": (
        "✨ <b>Chcieliśmy po prostu powiedzieć dziękujemy</b>\n\n"
        "Uczysz się nowego języka z WordSnap — i to jest naprawdę super. "
        "Każde dodane słowo, każda powtórka przybliża cię do chwili, gdy obcy "
        "język stanie się twój.\n\n"
        "Dziękujemy, że jesteś z nami. Tworzymy WordSnap właśnie dla ciebie 💛\n\n"
        "Miłego dnia — i niech dziś dojdzie jeszcze jedno nowe słowo 😉"
    ),
    "de": (
        "✨ <b>Wir wollten einfach Danke sagen</b>\n\n"
        "Du lernst eine neue Sprache mit WordSnap — und das ist wirklich großartig. "
        "Jedes Wort, das du hinzufügst, jede Wiederholung bringt dich dem Moment näher, "
        "in dem die fremde Sprache deine eigene wird.\n\n"
        "Danke, dass du dabei bist. Wir machen WordSnap für dich 💛\n\n"
        "Hab einen schönen Tag — und möge heute ein weiteres neues Wort dazukommen 😉"
    ),
    "fr": (
        "✨ <b>On voulait juste dire merci</b>\n\n"
        "Vous apprenez une nouvelle langue avec WordSnap — et c'est vraiment génial. "
        "Chaque mot ajouté, chaque révision vous rapproche du moment où la langue "
        "étrangère devient la vôtre.\n\n"
        "Merci d'être là. On construit WordSnap pour vous 💛\n\n"
        "Belle journée — et qu'un nouveau mot de plus s'ajoute aujourd'hui 😉"
    ),
}


async def _eligible_users(mode: str = "all") -> list[User]:
    """all      — усі (default для теплого «дякую»).
    active   — користувалися продуктом (review >0).
    catchup  — лишилися «застряглі» (review=0)."""
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
        "--mode", choices=("active", "catchup", "all"), default="all",
        help="all=everyone (default), active=reviews>0, catchup=reviews=0",
    )
    args = parser.parse_args()

    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        print("ERROR: TELEGRAM_BOT_TOKEN env var missing", file=sys.stderr)
        sys.exit(2)

    bot = Bot(token=token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))

    if args.test:
        # Test-режим: шлемо ОДНІЙ конкретній людині (зазвичай адміну для preview).
        async with SessionLocal() as session:
            user = (await session.execute(
                select(User).where(User.telegram_id == args.test)
            )).scalar_one_or_none()
        if not user:
            class _Stub:
                telegram_id = args.test
                native_lang = "uk"
            user = _Stub()  # type: ignore
            print(f"User {args.test} not in DB, sending with native_lang=uk")
        else:
            print(f"User {args.test}: native_lang={user.native_lang}, plan={user.plan}")
        status = await _send_one(bot, user, BROADCAST_ID)
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
        status = await _send_one(bot, u, BROADCAST_ID)
        stats[status] += 1
        if i % 25 == 0 or i == total:
            elapsed = (datetime.now(timezone.utc) - started).total_seconds()
            print(f"  {i}/{total} ({elapsed:.0f}s) — {dict(stats)}")
        await asyncio.sleep(RATE_LIMIT_DELAY_SEC)

    print(f"\nDONE: {dict(stats)}")
    await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
