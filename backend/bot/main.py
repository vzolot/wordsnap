"""
WordSnap Bot — Day 7: Recurring payments + webhook server
"""
import asyncio
import logging
import os
from datetime import datetime, timezone

import uvicorn
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo,
    BotCommand, BotCommandScopeDefault, BotCommandScopeChat,
)
from dotenv import load_dotenv

# Sentry init ПЕРШЕ — щоб ловити помилки навіть під час імпортів нижче
load_dotenv()
from core.sentry_init import init_sentry  # noqa: E402
init_sentry()

from bot.handlers.word_handler import router as word_router
from bot.handlers.review_handler import router as review_router
from bot.handlers.setup_handler import router as setup_router, native_lang_keyboard, ask_native_lang_text
from bot.handlers.songs_handler import router as songs_router
from bot.handlers.snap_handler import router as snap_router
from bot.handlers.survey_handler import router as survey_router
from bot.handlers.admin_handler import router as admin_router
from core.bot_i18n import help_text, premium_text, buy_text, t as bt
from core.constants import MINI_APP_URL
from core.languages import lang_flag, lang_name
from core.auto_migrate import run_auto_migrations
from core.bot_registry import tenant_id_for_bot
from scheduler.reminder import reminder_loop
from scheduler.streak_save import streak_save_loop
from scheduler.reengage import reengage_loop
from scheduler.image_backfill import image_backfill_loop
from scheduler.admin_report import admin_report_loop
from webhook.server import app as webhook_app
from core.user_service import (
    get_or_create_user,
    get_user_status,
    cancel_subscription,
)
from core.wayforpay_client import create_payment_link, pay_page_url

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)
logger = logging.getLogger(__name__)

# Bot та Dispatcher живуть у окремому модулі (`bot/instance.py`) щоб FastAPI
# хендлери могли імпортувати `bot` без re-execution цього файлу. Цей файл
# запускається як `__main__` у проді, тож `from bot.main import bot` з боку
# webhook'а раніше викликав повторне імпортування і RuntimeError на
# `dp.include_router(admin_router)` (router уже attached). Див. instance.py.
from bot.instance import bot, dp  # noqa: E402


@dp.message(CommandStart())
async def cmd_start(message: Message):
    """Реєстрація юзера в БД при /start"""
    tg_user = message.from_user

    # Парсимо deep-link payload (наприклад: /start ref_ABC123)
    payload = None
    if message.text:
        parts = message.text.split(maxsplit=1)
        if len(parts) > 1:
            payload = parts[1].strip()

    tid = tenant_id_for_bot(message.bot)  # тенант цього бота (мультитенантність)
    user = await get_or_create_user(
        telegram_id=tg_user.id,
        username=tg_user.username,
        first_name=tg_user.first_name,
        last_name=tg_user.last_name,
        language_code=tg_user.language_code,
        tenant_id=tid,
    )

    # Affiliate/influencer flow: payload `aff_<slug>`. First-touch
    # зберігаємо у `users.affiliate_slug` + `affiliate_at`. Подальші
    # платежі цього юзера автоматично генерують revenue-share row
    # у `affiliate_revenue` через `record_payment_share()`.
    #
    # Аудиторія інфлюенсерів — міжнародна (напр. підписники Rue/Sheku в
    # ПАР, англомовні), не українська. Тому онбординг для афіліат-когорти
    # ведемо англійською (вітання + питання рідної мови). Після того як
    # юзер обере рідну мову кнопкою, решта флоу йде вже цією мовою.
    is_affiliate = bool(user.affiliate_slug)  # returning, ще без target_lang
    if payload and payload.startswith("aff_"):
        from core.affiliates import (
            apply_affiliate_to_user,
            get_affiliate,
            parse_affiliate_payload,
        )
        slug = parse_affiliate_payload(payload)
        if slug:
            applied = await apply_affiliate_to_user(user.id, slug)
            is_affiliate = True
            if applied:
                aff = await get_affiliate(slug)
                influencer_name = aff.name if aff else slug
                try:
                    await message.answer(
                        bt("affiliate.welcome", "en", name=influencer_name)
                    )
                except Exception as e:
                    logger.warning(f"affiliate welcome msg failed: {e}")
        # Дальше — нормальний flow (онбординг якщо новий юзер).

    # tApps Center cohort: payload `tapps` або `tapps_<sub>` (`tapps_banner`,
    # `tapps_post_42` тощо). Аудиторія tApps міжнародна (англомовна за
    # замовчуванням), тому форсимо EN-онбординг — той самий шлях, що для
    # афіліат-когорти. Зберігаємо `acquisition_payload` для cohort-аналізу.
    # Не запускаємо ad-survey: tApps — не paid-ad cohort з lang/motivation
    # composite, просто organic channel з власним лендінгом.
    is_international = is_affiliate
    if payload and (payload == "tapps" or payload.startswith("tapps_")):
        is_international = True
        from sqlalchemy import update as sa_update
        from core.db import SessionLocal
        from core.models import User as UserModel
        async with SessionLocal() as session:
            await session.execute(
                sa_update(UserModel).where(UserModel.id == user.id).values(
                    acquisition_payload=payload[:64]
                )
            )
            await session.commit()

    # Ad-cohort flow: payload `<source>_<campaign>[_<lang>[_<mot>]]` від
    # paid ads. Сурси: `igads_`/`ig_` (Meta), `reddit_` (Reddit Ads),
    # потенційно нові. Шлемо в survey-handler — він сам розрулить чи
    # повний composite (lang+mot з survey) пройшов через payload, чи
    # треба показати in-bot Q&A. Атрибуція зберігається у БД через
    # `users.acquisition_payload` незалежно від платформи.
    AD_PREFIXES = ("igads_", "ig_", "reddit_")
    if payload and any(payload.startswith(p) for p in AD_PREFIXES):
        from bot.handlers.survey_handler import start_survey
        await start_survey(message, user, payload)
        return

    # Реферал застосовуємо лише новим юзерам без target_lang
    # (онбординг ще не завершено) і без вже встановленого referrer'а.
    if (
        payload
        and payload.startswith("ref_")
        and user.target_lang is None
        and user.referred_by is None
    ):
        from core.referral import apply_referral, REFERRAL_BONUS_DAYS, TRIAL_DAYS
        result = await apply_referral(invitee_id=user.id, referrer_code=payload[4:])
        if result:
            referrer, invitee = result
            invitee_lang = invitee.native_lang or "en"
            referrer_lang = referrer.native_lang or "en"
            # Invitee: показуємо повну суму (trial 7 + бонус 10 = 17), бо це
            # значно сильніший value-prop ніж "+10". Referrer бачить +10 як
            # бонус до своєї підписки.
            try:
                await message.answer(
                    bt("referral.invitee_welcome", invitee_lang, days=TRIAL_DAYS + REFERRAL_BONUS_DAYS)
                )
            except Exception as e:
                logger.warning(f"referral invitee msg failed: {e}")
            try:
                await bot.send_message(
                    chat_id=referrer.telegram_id,
                    text=bt(
                        "referral.referrer_notify",
                        referrer_lang,
                        name=tg_user.first_name or "friend",
                        days=REFERRAL_BONUS_DAYS,
                        total=referrer.referrals_count,
                    ),
                )
            except Exception as e:
                logger.warning(f"referral notify referrer failed: {e}")
            # Перечитуємо юзера — у нього тепер plan=pro з мерж-баг для шляхів нижче
            user = invitee

    # Новий юзер або ще не обрав мову — запускаємо онбординг
    if not user.target_lang:
        # Афіліат/tApps когорта онбординг англійською (міжнародна аудиторія),
        # решта — збереженою рідною мовою (дефолт uk).
        lang = "en" if is_international else (user.native_lang or "en")
        # Single-message welcome (новий копірайт), потім питаємо рідну мову
        await message.answer(bt("onboard.welcome", lang))
        await message.answer(
            ask_native_lang_text(lang),
            reply_markup=native_lang_keyboard(),
        )
        logger.info(f"New user {tg_user.id} — started language setup")
        return

    lang = user.native_lang or "en"
    status = await get_user_status(user, lang)
    target = user.target_lang or "en"

    # Денний ліміт + копія плану
    if status["plan"] == "pro":
        plan_text = bt("start.plan_pro", lang)
        daily_limit = 100
    elif status["is_trial"]:
        plan_text = bt("start.plan_trial", lang, days=status["trial_days_left"])
        daily_limit = 10
    else:
        plan_text = bt("start.plan_expired", lang)
        daily_limit = 0

    welcome_text = (
        f"{bt('start.hi', lang, name=tg_user.first_name)}\n\n"
        f"{bt('start.learning', lang, flag=lang_flag(target), lang_name=lang_name(target))}\n"
        f"{plan_text}\n"
        f"{bt('start.added_today', lang, used=status['used_today'], limit=daily_limit)}\n\n"
        f"{bt('start.tagline', lang)}\n\n"
        f"{bt('start.change_hint', lang)}"
    )

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=bt("setup.open_app", lang),
            web_app=WebAppInfo(url=MINI_APP_URL),
        )]
    ])
    await message.answer(welcome_text, reply_markup=keyboard)
    logger.info(f"User {tg_user.id} ({tg_user.username}) started the bot")


# ─── Telegram Stars payments (currency=XTR) ──────────────────────────────
# Stars — додатковий (НЕ основний) канал оплати поряд з картою (WayForPay).
# Mini-app викликає `POST /api/buy/stars` → `bot.create_invoice_link(...)` →
# відкриває через `tg.openInvoice(link, cb)`. Stars не мають recurring,
# тому `subscription_status="one_time"`, scheduler цих юзерів не зачіпає.

@dp.pre_checkout_query()
async def on_pre_checkout(query):
    """Останній checkpoint перед списанням. Для Stars (XTR) валідація не
    потрібна — баланс уже в гаманці. Відповідаємо ok=True завжди."""
    try:
        await query.answer(ok=True)
    except Exception as e:
        logger.exception(f"pre_checkout_query answer failed: {e}")
        try:
            await query.answer(ok=False, error_message="Payment processing error, please try again.")
        except Exception:
            pass


@dp.message(F.successful_payment)
async def on_successful_payment(message: Message):
    """Активує Pro після успішної оплати Telegram Stars. Парсимо
    `invoice_payload` (формат `stars_<tg_id>_<period>_<ts>`), пишемо
    `payment_history`, ставимо `subscription_status='one_time'`."""
    sp = message.successful_payment
    if not sp:
        return
    payload = sp.invoice_payload or ""
    if not payload.startswith("stars_"):
        logger.warning(f"successful_payment with unknown payload: {payload!r}")
        return
    parts = payload.split("_", 3)
    if len(parts) < 4:
        logger.warning(f"stars payload malformed: {payload!r}")
        return
    _, tg_id_str, period, _ts = parts
    try:
        tg_id = int(tg_id_str)
    except ValueError:
        logger.warning(f"stars payload bad tg_id: {payload!r}")
        return
    # Безпека: payer == payload tg_id (інакше підміна).
    if tg_id != message.from_user.id:
        logger.warning(
            f"stars payment from {message.from_user.id} but payload tg_id={tg_id}; refuse"
        )
        return
    if period not in ("monthly", "annual"):
        logger.warning(f"stars payload bad period: {period!r}")
        return

    duration_days = 30 if period == "monthly" else 365
    stars_amount = sp.total_amount  # XTR: 1 unit = 1 Star
    order_ref = payload

    # Lazy imports — pattern як решта файлу.
    from core.user_service import activate_pro_subscription
    from core.db import SessionLocal
    from core.models import PaymentHistory, User as UserModel
    from sqlalchemy import select, update as sa_update
    from core import analytics

    # Ідемпотентність: Telegram може повторно доставити той самий
    # successful_payment (retry / рестарт бота до коміту offset). order_ref
    # (== invoice_payload з фіксованим ts) однаковий при повторі, тому якщо
    # рядок уже є — нічого не активуємо вдруге (інакше +30/365 днів безкоштовно).
    async with SessionLocal() as session:
        dup = (await session.execute(
            select(PaymentHistory.id).where(
                PaymentHistory.order_reference == order_ref
            )
        )).scalar_one_or_none()
    if dup:
        logger.info(f"Stars payment: duplicate update for {order_ref}, ignoring")
        return

    user = await activate_pro_subscription(
        telegram_id=tg_id,
        rec_token=None,
        duration_days=duration_days,
        order_ref=order_ref,
    )
    if not user:
        logger.error(f"Stars payment: activate_pro failed for {tg_id}")
        return

    async with SessionLocal() as session:
        # subscription_status="one_time" → recurring_charges scheduler ігнорує
        # цього юзера (інакше він шукав би rec_token якого нема).
        await session.execute(
            sa_update(UserModel).where(UserModel.telegram_id == tg_id).values(
                subscription_status="one_time"
            )
        )
        ph = PaymentHistory(
            user_id=user.id,
            order_reference=order_ref,
            amount=float(stars_amount),
            currency="XTR",
            status="success",
            transaction_status="Approved",
            is_recurring=False,
            raw_payload=sp.model_dump() if hasattr(sp, "model_dump") else None,
        )
        session.add(ph)
        await session.commit()
        await session.refresh(ph)

    # Affiliate revenue share: щоб виплати інфлюенсерам (Rue/Sheku/etc.) не
    # залежали від каналу оплати. Stars → USD-еквівалент за поточним курсом
    # Telegram (~$0.013/Star) для розрахунку відсотка інфлюенсера. Якщо Stars
    # стануть помітною часткою revenue — переглянути курс.
    try:
        from core.affiliates import record_payment_share
        usd_equiv = round(float(stars_amount) * 0.013, 2)
        await record_payment_share(
            user_id=user.id,
            payment_id=ph.id,
            payment_amount=usd_equiv,
            payment_currency="USD",
        )
    except Exception as e:
        logger.warning(f"stars affiliate share record failed (non-fatal): {e}")

    # Дякуємо нативною мовою (en або uk-default fallback).
    lang = user.native_lang or "en"
    days_label = duration_days
    if lang == "uk":
        thank_text = (
            f"⭐ <b>Оплата прийнята!</b>\n\n"
            f"WordSnap Pro активний на {days_label} днів. Гарного навчання 💜"
        )
    else:
        thank_text = (
            f"⭐ <b>Payment received!</b>\n\n"
            f"WordSnap Pro is active for {days_label} days. "
            f"Enjoy unlimited learning 💜"
        )
    try:
        await message.answer(thank_text)
    except Exception as e:
        logger.warning(f"stars thank-you reply failed: {e}")

    try:
        analytics.capture(tg_id, "stars_payment_successful", {
            "period": period,
            "stars_amount": stars_amount,
            "duration_days": duration_days,
        })
    except Exception:
        pass


@dp.message(Command("help"))
async def cmd_help(message: Message):
    tid = tenant_id_for_bot(message.bot)  # тенант цього бота (мультитенантність)
    user = await get_or_create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        tenant_id=tid,
    )
    lang = user.native_lang or "en"
    await message.answer(help_text(lang))


@dp.message(Command("app"))
async def cmd_app(message: Message):
    tid = tenant_id_for_bot(message.bot)  # тенант цього бота (мультитенантність)
    user = await get_or_create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        tenant_id=tid,
    )
    lang = user.native_lang or "en"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text=bt("setup.open_app", lang),
            web_app=WebAppInfo(url=MINI_APP_URL),
        )
    ]])
    await message.answer(bt("app.intro", lang), reply_markup=keyboard)


@dp.message(Command("settings"))
async def cmd_settings(message: Message):
    tid = tenant_id_for_bot(message.bot)  # тенант цього бота (мультитенантність)
    user = await get_or_create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        tenant_id=tid,
    )
    lang = user.native_lang or "en"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=bt("settings.lang_btn", lang),
            callback_data="settings:language",
        )],
        [InlineKeyboardButton(
            text=bt("settings.app_btn", lang),
            web_app=WebAppInfo(url=MINI_APP_URL),
        )],
    ])
    await message.answer(bt("settings.title", lang), reply_markup=keyboard)


@dp.callback_query(F.data == "settings:language")
async def settings_language(callback: CallbackQuery):
    tid = tenant_id_for_bot(callback.bot)  # тенант цього бота (мультитенантність)
    user = await get_or_create_user(telegram_id=callback.from_user.id, tenant_id=tid)
    lang = user.native_lang or "en"
    await callback.message.edit_text(
        ask_native_lang_text(lang),
        reply_markup=native_lang_keyboard(),
    )
    await callback.answer()


@dp.message(Command("stats"))
async def cmd_stats(message: Message):
    tid = tenant_id_for_bot(message.bot)  # тенант цього бота (мультитенантність)
    user = await get_or_create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        tenant_id=tid,
    )
    lang = user.native_lang or "en"
    status = await get_user_status(user, lang)

    text = (
        f"{bt('stats.title', lang)}\n\n"
        f"{bt('stats.today', lang, used=status['used_today'], limit=status['daily_limit'])}\n"
        f"{bt('stats.total', lang, n=user.total_words)}\n"
        f"{bt('stats.reviews', lang, n=user.total_reviews)}\n"
        f"{bt('stats.plan_label', lang, label=status['plan_label'])}"
    )
    if status["is_trial"]:
        text += "\n\n" + bt("stats.trial_left", lang, days=status["trial_days_left"])
    elif status["plan"] != "pro":
        text += "\n\n" + bt("stats.want_more", lang)

    await message.answer(text)


@dp.message(Command("premium"))
async def cmd_premium(message: Message):
    tid = tenant_id_for_bot(message.bot)  # тенант цього бота (мультитенантність)
    user = await get_or_create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        tenant_id=tid,
    )
    lang = user.native_lang or "en"
    await message.answer(premium_text(lang))


@dp.message(Command("buy"))
async def cmd_buy(message: Message):
    tid = tenant_id_for_bot(message.bot)  # тенант цього бота (мультитенантність)
    user = await get_or_create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        tenant_id=tid,
    )
    lang = user.native_lang or "en"

    try:
        # Кнопка веде на наш /pay endpoint (рендерить auto-submit POST форму),
        # а НЕ на прямий WayForPay GET-лінк — той дає "Bad Request, requires
        # only POST data". /pay сам викликає create_payment_link при відкритті.
        url = pay_page_url(user.telegram_id, "monthly")
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=bt("buy.btn", lang), url=url)]
        ])
        await message.answer(buy_text(lang), reply_markup=keyboard)
        logger.info(f"Sent /pay link to user {user.telegram_id}")
    except Exception as e:
        logger.error(f"Error creating payment button: {e}", exc_info=True)
        await message.answer(bt("buy.error", lang))


@dp.message(Command("subscription"))
async def cmd_subscription(message: Message):
    tid = tenant_id_for_bot(message.bot)  # тенант цього бота (мультитенантність)
    user = await get_or_create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        tenant_id=tid,
    )
    lang = user.native_lang or "en"

    if user.plan == "pro" and user.plan_expires_at:
        is_active = user.plan_expires_at > datetime.now(timezone.utc)
        if is_active:
            renew_state = bt("sub.autorenew.on" if user.auto_renew else "sub.autorenew.off", lang)
            text = (
                f"{bt('sub.pro_title', lang)}\n\n"
                f"{bt('sub.valid_until', lang, date=user.plan_expires_at.strftime('%d.%m.%Y'))}\n"
                f"{bt('sub.autorenew_state', lang, state=renew_state)}\n"
            )
            if user.auto_renew:
                text += "\n" + bt("sub.will_renew", lang)
                text += "\n\n" + bt("sub.cancel_hint", lang)
            else:
                text += "\n" + bt("sub.wont_renew", lang)
                text += "\n\n" + bt("sub.renew_hint", lang)
        else:
            text = bt("sub.expired_title", lang) + "\n\n" + bt("sub.buy_again", lang)
    else:
        text = bt("sub.no_pro", lang)

    await message.answer(text)


@dp.message(Command("unsubscribe"))
async def cmd_unsubscribe(message: Message):
    tid = tenant_id_for_bot(message.bot)  # тенант цього бота (мультитенантність)
    user = await get_or_create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        tenant_id=tid,
    )
    lang = user.native_lang or "en"

    if user.plan != "pro":
        await message.answer(bt("unsub.no_active", lang))
        return

    if not user.auto_renew:
        date_str = user.plan_expires_at.strftime('%d.%m.%Y') if user.plan_expires_at else "—"
        await message.answer(bt("unsub.already_off", lang, date=date_str))
        return

    cancelled = await cancel_subscription(user.telegram_id)
    if cancelled:
        date_str = cancelled.plan_expires_at.strftime('%d.%m.%Y') if cancelled.plan_expires_at else "—"
        await message.answer(bt("unsub.cancelled", lang, date=date_str))
    else:
        await message.answer(bt("unsub.error", lang))


# Підключаємо роутери (setup першим — має пріоритет над word_router).
# admin_router до word_router — щоб /stats не зловив word-handler як просто
# текст слова.
dp.include_router(admin_router)
dp.include_router(setup_router)
dp.include_router(songs_router)
dp.include_router(review_router)
dp.include_router(snap_router)
dp.include_router(survey_router)
dp.include_router(word_router)


async def setup_bot_commands():
    """Оновлює меню команд та опис бота. Викликається на старті."""
    commands = [
        BotCommand(command="start", description="Почати або змінити налаштування"),
        BotCommand(command="songs", description="🎵 Слова з популярних пісень"),
        BotCommand(command="review", description="Повторити слова"),
        BotCommand(command="app", description="📱 Відкрити додаток"),
        BotCommand(command="stats", description="Моя статистика"),
        BotCommand(command="language", description="Змінити мову навчання"),
        BotCommand(command="premium", description="Pro-підписка"),
        BotCommand(command="help", description="Як користуватись"),
    ]
    await bot.set_my_commands(commands, scope=BotCommandScopeDefault())

    # Admin scope: для chat_id=ADMIN_TELEGRAM_ID показуємо ВСІ user-команди +
    # 3 admin-команди для звітів. Telegram chat-scope перебиває default,
    # тому без додавання default-команд адмін втратив би їх у меню.
    from core.constants import admin_telegram_id
    admin_id = admin_telegram_id()
    if admin_id is not None:
        admin_commands = commands + [
            BotCommand(command="stats_admin", description="📊 Live-зріз сьогодні"),
            BotCommand(command="stats_admin_day", description="📊 За вчорашню добу"),
            BotCommand(command="stats_admin_month", description="📊 За останні 30 днів"),
            BotCommand(command="stats_admin_ads", description="📣 Реклама — сьогодні"),
            BotCommand(command="stats_admin_ads_day", description="📣 Реклама — вчора"),
            BotCommand(command="stats_admin_ads_month", description="📣 Реклама — 30 днів"),
            BotCommand(command="admin_aff", description="🪙 Платні реферали — стата"),
            BotCommand(command="admin_aff_create", description="🪙 Створити affiliate-посилання"),
            BotCommand(command="test_remind", description="🧪 Force-надіслати denний пуш (debug)"),
        ]
        try:
            await bot.set_my_commands(
                admin_commands,
                scope=BotCommandScopeChat(chat_id=admin_id),
            )
            logger.info(f"📊 Admin commands set for chat {admin_id}")
        except Exception as e:
            logger.warning(f"Failed to set admin commands: {e}")

    # Опис у профілі бота (видно при пошуку та коли користувач натискає на ім'я)
    description_uk = (
        "WordSnap — слова, які ти зустрічаєш у житті за кордоном.\n\n"
        "Не вчу мову з нуля. Просто не даю забути слова, які ти вже чуєш на вулиці чи бачиш у листах.\n\n"
        "✅ 5 мов: 🇬🇧 🇪🇸 🇵🇱 🇩🇪 🇺🇦\n"
        "✅ Інтервальне повторення (нагадаю через 1, 3, 7, 14 днів)\n"
        "✅ Набори слів з пісень\n"
        "✅ XP-система і нагороди\n\n"
        "Натисни START — далі за 60 секунд."
    )
    description_en = (
        "WordSnap — for words you meet in real life abroad.\n\n"
        "I don't teach you a language from scratch. I just stop you from forgetting words "
        "you already hear on the street or read in messages.\n\n"
        "✅ 5 languages: 🇬🇧 🇪🇸 🇵🇱 🇩🇪 🇺🇦\n"
        "✅ Spaced repetition (1, 3, 7, 14 days)\n"
        "✅ Word packs from popular songs\n"
        "✅ XP system & rewards\n\n"
        "Tap START — done in 60 seconds."
    )
    short_uk = "Слова, що ти чуєш за кордоном. 5 мов. Інтервальне повторення. Набори з пісень."
    short_en = "Words you meet abroad. 5 languages. Spaced repetition. Songs vocab."

    try:
        await bot.set_my_description(description=description_uk, language_code="uk")
        await bot.set_my_description(description=description_en, language_code="en")
        await bot.set_my_description(description=description_en)  # default
        await bot.set_my_short_description(short_description=short_uk, language_code="uk")
        await bot.set_my_short_description(short_description=short_en, language_code="en")
        await bot.set_my_short_description(short_description=short_en)  # default
    except Exception as e:
        logger.warning(f"Failed to set bot description: {e}")


async def main():
    logger.info("🚀 WordSnap Bot starting...")

    # Schema sync — гарантує що БД відповідає поточному коду перед стартом
    try:
        await run_auto_migrations()
    except Exception as e:
        logger.error(f"Auto-migrations failed: {e}", exc_info=True)
        # Не валимо процес — частина міграцій могла пройти
        from core.sentry_init import capture_exception
        capture_exception(e, {"phase": "startup_migrations"})

    # ── Мультибот (white-label): головний бот = тенант 1, плюс боти тенантів ──
    from core.bot_registry import register as register_bot, make_bot
    from core.tenant_service import (
        sync_default_tenant, get_active_tenants, DEFAULT_TENANT_ID,
    )

    # Тенант 1 має отримати bot_token/bot_id з env — потрібно для резолву
    # initData головного бота (M3) і для того, щоб полінг підхопив і його.
    try:
        await sync_default_tenant()
    except Exception as e:
        logger.warning(f"sync_default_tenant failed: {e}")

    # Головний бот (той самий токен/сесія — НЕ створюємо другу сесію на нього).
    register_bot(DEFAULT_TENANT_ID, bot)
    tenant_bots = [bot]
    try:
        for tenant in await get_active_tenants():
            if tenant.id == DEFAULT_TENANT_ID or not tenant.bot_token:
                continue
            tbot = make_bot(tenant.bot_token)
            register_bot(tenant.id, tbot)
            tenant_bots.append(tbot)
            logger.info(
                f"🤖 Tenant bot up: {tenant.slug} (id={tenant.id}, bot_id={tenant.bot_id})"
            )
    except Exception as e:
        logger.error(f"Failed loading tenant bots: {e}", exc_info=True)

    # Telegram забороняє getUpdates при активному вебхуку — знімаємо на кожному.
    for b in tenant_bots:
        try:
            await b.delete_webhook(drop_pending_updates=True)
        except Exception as e:
            logger.warning(f"delete_webhook failed for bot {b.id}: {e}")

    try:
        # Наразі бренд-команди/опис ставимо лише головному боту. Команди й
        # брендинг ботів тенантів — окремо (M5/M7), бо мова/бренд відрізняються.
        await setup_bot_commands()
    except Exception as e:
        logger.warning(f"Failed to set bot commands: {e}")

    # Резолвимо username бота через getMe — для коректних реферальних посилань
    # незалежно від того, чи виставлено BOT_USERNAME у env.
    try:
        me = await bot.get_me()
        if me and me.username:
            os.environ["BOT_USERNAME"] = me.username
            logger.info(f"🤖 Bot username resolved: @{me.username}")
    except Exception as e:
        logger.warning(f"Failed to resolve bot username via getMe: {e}")
    
    # Конфігурація FastAPI server
    port = int(os.getenv("PORT", "8000"))
    config = uvicorn.Config(
        webhook_app,
        host="0.0.0.0",
        port=port,
        log_level="info",
    )
    server = uvicorn.Server(config)
    
    logger.info(f"📡 Webhook server starting on port {port}")
    
    # Запускаємо паралельно: bot polling + reminder + streak-save + re-engage
    # + image-backfill + admin-report + webhook.
    #
    # recurring_charges_loop НАВМИСНО вимкнено (2026-05-20): перейшли на
    # WayForPay-managed регулярні платежі (regularOn=1 у purchase-формі) —
    # WayForPay сам списує щомісяця і шле callback на /wayforpay/callback.
    # Якщо лишити наш крон активним, він списував би ВДРУГЕ за збереженим
    # recToken'ом → подвійне списання. Код крона лишається у репі на випадок
    # повернення до self-managed моделі.
    await asyncio.gather(
        dp.start_polling(*tenant_bots),
        reminder_loop(bot),
        streak_save_loop(bot),
        reengage_loop(bot),
        image_backfill_loop(bot),
        admin_report_loop(bot),
        server.serve(),
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped")