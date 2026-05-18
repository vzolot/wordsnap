"""Ad-cohort survey: 2 короткі питання у боті перед запуском Mini App.

Реклама приземляє в `t.me/<bot>?start=igads_<campaign>`. `/start` handler
у bot/main.py детектить `igads_*` payload і викликає `start_survey()` звідси.
Юзер відповідає на Q1 (target_lang) і Q2 (motivation), після чого отримує
`web_app`-кнопку «Launch WordSnap» — Mini App вже знає target_lang з БД
і пропускає welcome-stories.

Чому через бота а не /open bridge:
  - Атрибуція зберігається у БД (`acquisition_payload`) на момент `/start`,
    а не через `start_param` у WebApp SDK (який у Meta IAB губиться).
  - Intent filter: тільки ті хто пройшов 2 кнопки потрапляють у SPA.
  - Motivation = новий segment для themes-recommendations.
"""
from __future__ import annotations

import logging
from typing import Optional

from aiogram import F, Router
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    WebAppInfo,
)
from sqlalchemy import select, update as sa_update

from core import analytics
from core.bot_i18n import t as bt
from core.constants import MINI_APP_URL
from core.db import SessionLocal
from core.models import User

logger = logging.getLogger(__name__)
router = Router()


SUPPORTED_LANGS: tuple[tuple[str, str, str], ...] = (
    ("en", "🇬🇧", "English"),
    ("fr", "🇫🇷", "Français"),
    ("es", "🇪🇸", "Español"),
    ("pl", "🇵🇱", "Polski"),
    ("de", "🇩🇪", "Deutsch"),
    ("uk", "🇺🇦", "Українська"),
)
_LANG_CODES = frozenset(c for c, _, _ in SUPPORTED_LANGS)

# Motivation enum — мусить бути узгоджено з validator/themes-personalization.
MOTIVATIONS: tuple[tuple[str, str, str], ...] = (
    ("living", "🏠", "motivation.living"),
    ("work", "💼", "motivation.work"),
    ("studying", "📚", "motivation.studying"),
    ("family", "👨‍👩‍👧", "motivation.family"),
    ("travel", "✈️", "motivation.travel"),
    ("self", "🧠", "motivation.self"),
)
_MOT_CODES = frozenset(c for c, _, _ in MOTIVATIONS)


def parse_ad_payload(payload: str) -> dict[str, Optional[str]]:
    """Парс `/start <source>_<camp>[_<lang>[_<mot>]]` payload.

    Підтримує три формати, source-agnostic (igads_, ig_, reddit_, ...):
      - `igads_val_2605_v2_en_work` → lang + mot з survey (Meta IG flow)
      - `reddit_val_pl_v1_pl`       → тільки lang (Reddit flow, lander
                                       пер-мовний, motivation запитаємо
                                       у in-app survey пізніше)
      - `igads_val_2605_v2`         → тільки кампанія (legacy / organic)

    Telegram `/start` payload allows [A-Za-z0-9_-]{,64} - використовуємо
    нижнє підкреслення. Кампанія сама може містити підкреслення
    («val_2605_v2», «val_pl_v1»), тому трейлінг lang/mot детектимо за
    належністю до відомих enum'ів `_LANG_CODES` / `_MOT_CODES`.
    """
    parts = payload.split("_")
    if len(parts) < 2:
        return {"campaign": payload, "lang": None, "motivation": None}
    # Variant A: останні 2 - (lang, mot)
    if len(parts) >= 4 and parts[-2] in _LANG_CODES and parts[-1] in _MOT_CODES:
        return {
            "campaign": "_".join(parts[1:-2]),
            "lang": parts[-2],
            "motivation": parts[-1],
        }
    # Variant B: тільки останній - lang (Reddit-flow без motivation)
    if len(parts) >= 3 and parts[-1] in _LANG_CODES:
        return {
            "campaign": "_".join(parts[1:-1]),
            "lang": parts[-1],
            "motivation": None,
        }
    # Variant C: чиста кампанія
    return {
        "campaign": "_".join(parts[1:]),
        "lang": None,
        "motivation": None,
    }


def _q1_keyboard() -> InlineKeyboardMarkup:
    """Q1 — вибір target_lang. 6 кнопок у 2 ряди по 3."""
    buttons = [
        InlineKeyboardButton(text=f"{flag} {name}", callback_data=f"survey_lang:{code}")
        for code, flag, name in SUPPORTED_LANGS
    ]
    rows = [buttons[i:i + 3] for i in range(0, len(buttons), 3)]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _q2_keyboard(lang: str) -> InlineKeyboardMarkup:
    """Q2 — motivation. 6 кнопок у 2 ряди по 3, лейбли локалізовані."""
    buttons = [
        InlineKeyboardButton(
            text=f"{emoji} {bt(key, lang)}",
            callback_data=f"survey_mot:{code}",
        )
        for code, emoji, key in MOTIVATIONS
    ]
    rows = [buttons[i:i + 3] for i in range(0, len(buttons), 3)]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _launch_keyboard(lang: str, start_param: Optional[str]) -> InlineKeyboardMarkup:
    """Web-app кнопка «Launch WordSnap».

    КРИТИЧНО: для `web_app` button URL ОБОВ'ЯЗКОВО має бути hosted URL
    мінi-апи (https://miniapp-omega-three.vercel.app), НЕ `t.me/<bot>/app`.
    Telegram API мовчки відхиляє відправку кнопки якщо URL це t.me-лінк —
    звідси баг «нічого не відбувається» після Q2.

    `start_param` як query-string у URL — резерв, але формально Telegram
    web_app не пропихає startapp у `tg.initDataUnsafe.start_param` через
    web_app button (тільки через direct deep-link). Тому атрибуція тепер
    тече через БД: SPA читає `user.acquisition_payload` з /api/stats і
    піднімає її як PostHog super-prop.
    """
    url = MINI_APP_URL
    if start_param:
        url += f"?startapp={start_param}"
    btn = InlineKeyboardButton(
        text=bt("survey.cta_launch", lang),
        web_app=WebAppInfo(url=url),
    )
    return InlineKeyboardMarkup(inline_keyboard=[[btn]])


async def start_survey(
    message: Message,
    user: User,
    payload: str,
) -> None:
    """Точка входу: викликається з /start handler для igads_/ig_-ad payloads.

    Якщо payload містить survey-суфікс (`_<lang>_<motivation>`, заповнюється
    на лендингу перед редіректом у бот) — зберігаємо все одразу і шлемо
    тільки Launch button, без in-bot Q&A. Інакше fallback на 2-питальний
    in-bot survey (backward compat).
    """
    lang = user.native_lang or "uk"
    parsed = parse_ad_payload(payload)
    payload_lang = parsed["lang"]
    payload_mot = parsed["motivation"]

    # Persist payload + (опційно) survey-результати з лендинг-етапу.
    updates: dict[str, str] = {"acquisition_payload": payload}
    if payload_lang and not user.target_lang:
        updates["target_lang"] = payload_lang
        user.target_lang = payload_lang
    if payload_mot and not user.motivation:
        updates["motivation"] = payload_mot
        user.motivation = payload_mot
    async with SessionLocal() as session:
        await session.execute(sa_update(User).where(User.id == user.id).values(**updates))
        await session.commit()

    analytics.capture(user.telegram_id, "ad_survey_started", {
        "payload": payload,
        "campaign": parsed["campaign"],
        "lang_from_payload": payload_lang,
        "motivation_from_payload": payload_mot,
        "skip_in_bot_survey": bool(payload_lang and payload_mot),
    })
    if payload_lang:
        analytics.identify(user.telegram_id, {"target_lang": payload_lang})
    if payload_mot:
        analytics.identify(user.telegram_id, {"motivation": payload_mot})

    # Якщо у нас уже є lang + motivation (з лендингу або з попередніх візитів) —
    # одразу Launch, без зайвих кроків.
    if user.target_lang and user.motivation:
        await message.answer(
            bt("survey.welcome_back", lang),
            reply_markup=_launch_keyboard(lang, payload),
        )
        return

    # Fallback: in-bot Q&A для legacy payloads / organic ad-clicks.
    await message.answer(
        bt("survey.q1_intro", lang),
        reply_markup=_q1_keyboard(),
    )


@router.callback_query(F.data.startswith("survey_lang:"))
async def cb_survey_lang(callback: CallbackQuery) -> None:
    """Q1 answer: пишемо target_lang, шлемо Q2."""
    tg_user = callback.from_user
    code = (callback.data or "").split(":", 1)[1]
    if not any(code == c for c, _, _ in SUPPORTED_LANGS):
        await callback.answer()
        return

    async with SessionLocal() as session:
        user = (await session.execute(
            select(User).where(User.telegram_id == tg_user.id)
        )).scalar_one_or_none()
        if not user:
            await callback.answer()
            return
        await session.execute(
            sa_update(User).where(User.id == user.id).values(target_lang=code)
        )
        await session.commit()

    msg_lang = user.native_lang or "uk"
    flag = next((f for c, f, _ in SUPPORTED_LANGS if c == code), "🌐")
    name = next((n for c, _, n in SUPPORTED_LANGS if c == code), code)

    analytics.capture(tg_user.id, "ad_survey_lang_picked", {
        "target_lang": code,
        "payload": user.acquisition_payload,
    })
    analytics.identify(tg_user.id, {"target_lang": code})

    try:
        await callback.message.edit_text(
            bt("survey.q1_done", msg_lang, flag=flag, name=name),
        )
    except Exception:
        pass
    await callback.message.answer(
        bt("survey.q2_intro", msg_lang),
        reply_markup=_q2_keyboard(msg_lang),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("survey_mot:"))
async def cb_survey_motivation(callback: CallbackQuery) -> None:
    """Q2 answer: пишемо motivation, шлемо Launch button."""
    tg_user = callback.from_user
    code = (callback.data or "").split(":", 1)[1]
    if not any(code == c for c, _, _ in MOTIVATIONS):
        await callback.answer()
        return

    async with SessionLocal() as session:
        user = (await session.execute(
            select(User).where(User.telegram_id == tg_user.id)
        )).scalar_one_or_none()
        if not user:
            await callback.answer()
            return
        await session.execute(
            sa_update(User).where(User.id == user.id).values(motivation=code)
        )
        await session.commit()

    msg_lang = user.native_lang or "uk"
    motivation_label = bt(
        next(k for c, _, k in MOTIVATIONS if c == code), msg_lang
    )

    analytics.capture(tg_user.id, "ad_survey_motivation_picked", {
        "motivation": code,
        "target_lang": user.target_lang,
        "payload": user.acquisition_payload,
    })
    analytics.identify(tg_user.id, {"motivation": code})

    try:
        await callback.message.edit_text(
            bt("survey.q2_done", msg_lang, motivation=motivation_label),
        )
    except Exception:
        pass
    await callback.message.answer(
        bt("survey.welcome_done", msg_lang, motivation=motivation_label),
        reply_markup=_launch_keyboard(msg_lang, user.acquisition_payload),
    )
    await callback.answer()
