"""Admin-only команди для @WordSnapBot.

/stats_admin           — live-зріз поточного дня (з 00:00 Kyiv до зараз)
/stats_admin_day       — повна вчорашня доба (той самий зріз що в 09:00 push)
/stats_admin_month     — за останні 30 днів (включно з сьогодні-live)
/stats_admin_ads       — платна реклама (Meta) за сьогодні
/stats_admin_ads_day   — платна реклама за вчора
/stats_admin_ads_month — платна реклама за останні 30 днів

Доступні лише користувачу із telegram_id == ADMIN_TELEGRAM_ID. Для всіх
інших — тиха відмова, щоб не палити існування команди.
"""
import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from core.admin_report import PeriodKind, build_report
from core.constants import admin_telegram_id
from core.meta_ads import AdsPeriod, build_ads_report

logger = logging.getLogger(__name__)
router = Router()


def _is_admin(message: Message) -> bool:
    aid = admin_telegram_id()
    return aid is not None and message.from_user.id == aid


async def _send_report(message: Message, period: PeriodKind, command_name: str) -> None:
    if not _is_admin(message):
        return  # тиха відмова
    try:
        text = await build_report(period)
        await message.answer(text, parse_mode="HTML")
    except Exception as e:
        logger.error(f"/{command_name} failed: {e}", exc_info=True)
        await message.answer("⚠️ Звіт не вдалось зібрати — глянь логи.")


@router.message(Command("stats_admin"))
async def cmd_stats_admin(message: Message) -> None:
    await _send_report(message, "today_live", "stats_admin")


@router.message(Command("stats_admin_day"))
async def cmd_stats_admin_day(message: Message) -> None:
    await _send_report(message, "yesterday_full", "stats_admin_day")


@router.message(Command("stats_admin_month"))
async def cmd_stats_admin_month(message: Message) -> None:
    await _send_report(message, "month_30d", "stats_admin_month")


async def _send_ads_report(message: Message, period: AdsPeriod, command_name: str) -> None:
    if not _is_admin(message):
        return  # тиха відмова
    try:
        text = await build_ads_report(period)
        await message.answer(text, parse_mode="HTML", disable_web_page_preview=True)
    except Exception as e:
        logger.error(f"/{command_name} failed: {e}", exc_info=True)
        await message.answer("⚠️ Звіт по рекламі не вдалось зібрати — глянь логи.")


@router.message(Command("stats_admin_ads"))
async def cmd_stats_admin_ads(message: Message) -> None:
    await _send_ads_report(message, "today", "stats_admin_ads")


@router.message(Command("stats_admin_ads_day"))
async def cmd_stats_admin_ads_day(message: Message) -> None:
    await _send_ads_report(message, "yesterday", "stats_admin_ads_day")


@router.message(Command("stats_admin_ads_month"))
async def cmd_stats_admin_ads_month(message: Message) -> None:
    await _send_ads_report(message, "last_30d", "stats_admin_ads_month")


@router.message(Command("admin_aff"))
async def cmd_admin_affiliates(message: Message) -> None:
    """Адмін-зріз по всіх інфлюенсерах: за останні 30 днів + lifetime."""
    if not _is_admin(message):
        return
    from core.affiliates import affiliate_deeplink, get_affiliate_stats, list_affiliates

    affs = await list_affiliates()
    if not affs:
        await message.answer(
            "🪙 <b>Платні реферали</b> — жодного інфлюенсера ще не створено.\n\n"
            "Створи: <code>/admin_aff_create rue Rue 20 180</code>\n"
            "(slug, name, % share, duration days)",
            parse_mode="HTML",
        )
        return

    lines = ["🪙 <b>Платні реферали</b>\n"]
    for aff in affs:
        s30 = await get_affiliate_stats(aff.slug, days=30)
        s_all = await get_affiliate_stats(aff.slug, days=None)
        link = affiliate_deeplink(aff.slug)
        lines.append(
            f"<b>{aff.name}</b> · <code>{aff.slug}</code> · "
            f"{aff.rev_share_pct}% × {aff.duration_days}d\n"
            f"<a href=\"{link}\">{link}</a>\n"
            f"  <b>30d:</b> users={s30['users_acquired']} · "
            f"paying={s30['paying_users']} · "
            f"gross=${s30['gross_amount']:.2f} · "
            f"owed=${s30['share_owed']:.2f}\n"
            f"  <b>all:</b> users={s_all['users_acquired']} · "
            f"paying={s_all['paying_users']} · "
            f"gross=${s_all['gross_amount']:.2f} · "
            f"owed=${s_all['share_owed']:.2f}"
        )
    await message.answer(
        "\n\n".join(lines), parse_mode="HTML", disable_web_page_preview=True,
    )


@router.message(Command("admin_aff_create"))
async def cmd_admin_aff_create(message: Message) -> None:
    """Створити новий affiliate.

    Usage: <code>/admin_aff_create slug name [rev_share_pct] [duration_days]</code>
    Default: 20% × 180 днів (6 місяців).
    Приклад: <code>/admin_aff_create rue Rue 20 180</code>
    """
    if not _is_admin(message):
        return
    from core.affiliates import affiliate_deeplink, create_affiliate, is_valid_slug

    parts = (message.text or "").split(maxsplit=4)
    if len(parts) < 3:
        await message.answer(
            "Usage: <code>/admin_aff_create slug name [rev_share_pct] [duration_days]</code>\n"
            "Default: 20% × 180 днів.\n"
            "Приклад: <code>/admin_aff_create rue Rue 20 180</code>",
            parse_mode="HTML",
        )
        return
    slug = parts[1].lower()
    if not is_valid_slug(slug):
        await message.answer(f"❌ Invalid slug `{slug}` (a-z0-9_- , 2-40 chars)")
        return
    name = parts[2]
    try:
        rev_share = float(parts[3]) if len(parts) > 3 else 20.0
        duration_days = int(parts[4]) if len(parts) > 4 else 180
    except (ValueError, IndexError):
        await message.answer("❌ rev_share_pct must be float, duration_days int")
        return
    try:
        aff = await create_affiliate(slug, name, rev_share_pct=rev_share, duration_days=duration_days)
    except Exception as e:
        await message.answer(f"❌ {e}")
        return
    link = affiliate_deeplink(aff.slug)
    await message.answer(
        f"✅ <b>{aff.name}</b> · <code>{aff.slug}</code> · "
        f"{aff.rev_share_pct}% × {aff.duration_days}d\n\n"
        f"Посилання для інфлюенсера:\n<a href=\"{link}\">{link}</a>\n\n"
        f"Кожна оплата підписки юзером, який прийшов за цим лінком, "
        f"протягом {aff.duration_days} днів - буде давати <b>{aff.rev_share_pct}%</b> "
        f"інфлюенсеру. Статистика: /admin_aff",
        parse_mode="HTML",
        disable_web_page_preview=True,
    )


@router.message(Command("test_remind"))
async def cmd_test_remind(message: Message) -> None:
    """Force-надсилає денний пуш зараз, ігноруючи час/дату/cooldown.
    Корисно для дебагу: чи працює сама send-логіка, чи проблема у scheduler-таймері."""
    if not _is_admin(message):
        return

    from sqlalchemy import select
    from core.db import SessionLocal
    from core.models import User
    from scheduler.reminder import send_daily_push_for_user

    async with SessionLocal() as s:
        user = (await s.execute(
            select(User).where(User.telegram_id == message.from_user.id)
        )).scalar_one_or_none()

    if not user:
        await message.answer("⚠️ Не знайшов твій user-row у БД.")
        return

    status = await send_daily_push_for_user(message.bot, user, force=True)
    if status == "sent":
        # Окреме повідомлення не шлемо — пуш сам прийшов як окрема нотифікація.
        return

    explanations = {
        "no_due_word": (
            "🤷 Нема learning-слів зі статусом due (next_review ≤ now).\n"
            "→ Перевір у мініапі вкладку \"Повторення\" — якщо там empty, "
            "то й бот не має що нагадати."
        ),
        "send_failed": "⚠️ bot.send_message впав — глянь логи Railway.",
    }
    await message.answer(explanations.get(status, f"⚠️ status={status}"))
