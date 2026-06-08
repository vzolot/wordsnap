"""
REST API для miniapp.
"""
import logging
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Query, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import delete, select, func

from sqlalchemy import or_

from core import analytics
from core.db import SessionLocal
from core.models import PaymentHistory, Review, User, Word
from core.rewards import TIERS, current_tier, next_tier, xp_for_result
from core.streaks import calculate_streak as _calculate_streak, reviewed_today as _reviewed_today

logger = logging.getLogger(__name__)

router = APIRouter()


class WordRequest(BaseModel):
    word: str


class WordsBulkRequest(BaseModel):
    words: list[str]


class ReviewRequest(BaseModel):
    word_id: int
    quality: int = 3
    mode: str | None = None  # cards | quiz | spelling — для аналітики


class WordUpdateRequest(BaseModel):
    translation: str


def _serialize_word(w: Word) -> dict:
    return {
        "id": w.id,
        "word": w.word,
        "translation": w.translation,
        "part_of_speech": w.part_of_speech,
        "difficulty": w.difficulty,
        "examples": w.examples or [],
        "image_url": w.image_url,
        "memory_tip": w.memory_tip,
        "review_count": w.review_count,
        "status": w.status,
        "target_lang": w.target_lang,
    }


async def _get_user(session, telegram_id: int) -> User | None:
    return (await session.execute(
        select(User).where(User.telegram_id == telegram_id)
    )).scalar_one_or_none()


@router.get("/api/words")
async def get_words(telegram_id: int = Query(...)):
    async with SessionLocal() as session:
        user = await _get_user(session, telegram_id)
        if not user:
            return []
        result = await session.execute(
            select(Word).where(Word.user_id == user.id).order_by(Word.created_at.desc())
        )
        return [_serialize_word(w) for w in result.scalars().all()]


@router.patch("/api/words/{word_id}")
async def update_word(
    word_id: int, payload: WordUpdateRequest, telegram_id: int = Query(...),
):
    """Редагування перекладу. Дозволяємо юзеру замінити AI-варіант на свій
    (часто діаспора має родинні/регіональні переклади). SRS-стан не чіпаємо."""
    translation = (payload.translation or "").strip()
    if not translation:
        raise HTTPException(status_code=400, detail="empty_translation")
    if len(translation) > 500:
        raise HTTPException(status_code=400, detail="too_long")

    from sqlalchemy import update as sa_update
    async with SessionLocal() as session:
        user = await _get_user(session, telegram_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        word = (await session.execute(
            select(Word).where(Word.id == word_id, Word.user_id == user.id)
        )).scalar_one_or_none()
        if not word:
            raise HTTPException(status_code=404, detail="Word not found")
        old_translation = word.translation
        await session.execute(
            sa_update(Word).where(Word.id == word_id).values(translation=translation)
        )
        await session.commit()
        # Перетягуємо щоб віддати свіжий обʼєкт назад
        word = (await session.execute(
            select(Word).where(Word.id == word_id)
        )).scalar_one()

    analytics.capture(telegram_id, "word_translation_edited", {
        "target_lang": word.target_lang,
        "old_len": len(old_translation or ""),
        "new_len": len(translation),
        "review_count": word.review_count,
    })
    return {"ok": True, "word": _serialize_word(word)}


@router.delete("/api/words/{word_id}")
async def delete_word(word_id: int, telegram_id: int = Query(...)):
    """Видаляє слово (тільки якщо воно належить юзеру). Reviews видаляються
    каскадом через FK ondelete=CASCADE."""
    async with SessionLocal() as session:
        user = await _get_user(session, telegram_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        word = (await session.execute(
            select(Word).where(Word.id == word_id, Word.user_id == user.id)
        )).scalar_one_or_none()
        if not word:
            raise HTTPException(status_code=404, detail="Word not found")
        await session.execute(delete(Word).where(Word.id == word_id))
        # Декрементуємо лічильник total_words. Денний лічильник не чіпаємо
        # — він прив'язаний до того скільки юзер додав за день, не що залишилось.
        if user.total_words and user.total_words > 0:
            from sqlalchemy import update as sa_update
            await session.execute(
                sa_update(User).where(User.id == user.id).values(
                    total_words=user.total_words - 1
                )
            )
        await session.commit()
    analytics.capture(telegram_id, "word_deleted", {
        "target_lang": word.target_lang,
        "review_count": word.review_count,
        "status": word.status,
    })
    return {"ok": True}


async def _total_spent(session, user_id: int) -> float:
    """Загальна сума успішних платежів юзера (USD)."""
    spent = (await session.execute(
        select(func.coalesce(func.sum(PaymentHistory.amount), 0)).where(
            PaymentHistory.user_id == user_id,
            or_(
                PaymentHistory.status == "success",
                PaymentHistory.transaction_status == "Approved",
            ),
        )
    )).scalar()
    return float(spent or 0)


@router.get("/api/stats")
async def get_stats(telegram_id: int = Query(...)):
    async with SessionLocal() as session:
        user = await _get_user(session, telegram_id)
        if not user:
            beginner = current_tier(0)
            nxt = next_tier(0)
            return {
                "total_words": 0, "learned_words": 0, "streak": 0,
                "reviewed_today": 0, "total_reviews": 0, "total_xp": 0,
                "xp_today": 0,
                "total_spent": 0.0,
                "tier_xp": beginner[0], "tier_key": beginner[1],
                "tier_reward_key": beginner[2],
                "next_tier_xp": nxt[0] if nxt else None,
                "next_tier_key": nxt[1] if nxt else None,
                "next_tier_reward_key": nxt[2] if nxt else None,
                "plan": "free", "plan_expires_at": None,
                "used_today": 0, "daily_limit": 10,
                "native_lang": "uk", "target_lang": None,
                "is_trial": True,
            }

        # 5 запитів — паралельно у власних sessions. Без gather це ~250-500мс
        # послідовно; паралельно — ~50-80мс (RTT до Supabase + max латентність).
        import asyncio as _aio

        today_start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        uid = user.id

        async def q_learned() -> int:
            async with SessionLocal() as s:
                return (await s.execute(
                    select(func.count(Word.id)).where(
                        Word.user_id == uid, Word.status == "mastered"
                    )
                )).scalar() or 0

        async def q_reviewed_today() -> int:
            async with SessionLocal() as s:
                return await _reviewed_today(s, uid)

        async def q_streak() -> int:
            async with SessionLocal() as s:
                return await _calculate_streak(s, uid)

        async def q_total_spent() -> float:
            async with SessionLocal() as s:
                return await _total_spent(s, uid)

        async def q_xp_today() -> int:
            async with SessionLocal() as s:
                rows = (await s.execute(
                    select(Review.result, func.count().label("n")).where(
                        Review.user_id == uid,
                        Review.reviewed_at >= today_start,
                    ).group_by(Review.result)
                )).all()
                return sum(xp_for_result(r.result) * int(r.n) for r in rows)

        learned, reviewed_today, streak, total_spent, xp_today = await _aio.gather(
            q_learned(), q_reviewed_today(), q_streak(), q_total_spent(), q_xp_today()
        )

        now = datetime.now(timezone.utc)
        is_pro = user.plan == "pro" and user.plan_expires_at and user.plan_expires_at > now
        is_trial = (not is_pro) and user.created_at and (now - user.created_at) < timedelta(days=7)
        is_free_post_trial = (not is_pro) and (not is_trial)

        # Free-tier «хвіст»: 3 додавання на rolling 7 днів. Поля daily_limit /
        # used_today перевикористовуються (frontend дивиться на
        # is_free_post_trial щоб знати чи це тижневі цифри).
        from core.user_service import (
            _count_adds_last_7d as _user_count_adds_7d,
            FREE_WEEKLY_LIMIT,
        )

        if is_pro:
            daily_limit = 100
            used_for_limit = user.words_added_today
        elif is_trial:
            daily_limit = 10
            used_for_limit = user.words_added_today
        else:
            daily_limit = FREE_WEEKLY_LIMIT
            async with SessionLocal() as s_week:
                used_for_limit = await _user_count_adds_7d(s_week, user.id)

        xp = user.total_xp or 0
        tier = current_tier(xp)
        nxt = next_tier(xp)
        tiers_payload = [
            {"xp": t[0], "key": t[1], "reward_key": t[2], "achieved": xp >= t[0]}
            for t in TIERS
        ]

        return {
            "total_words": user.total_words,
            "learned_words": learned,
            "streak": streak,
            "reviewed_today": reviewed_today,
            "total_reviews": user.total_reviews,
            "total_xp": xp,
            "xp_today": xp_today,
            "total_spent": total_spent,
            "tier_xp": tier[0],
            "tier_key": tier[1],
            "tier_reward_key": tier[2],
            "next_tier_xp": nxt[0] if nxt else None,
            "next_tier_key": nxt[1] if nxt else None,
            "next_tier_reward_key": nxt[2] if nxt else None,
            "tiers": tiers_payload,
            "plan": "pro" if is_pro else user.plan,
            "plan_expires_at": user.plan_expires_at.isoformat() if user.plan_expires_at else None,
            "auto_renew": user.auto_renew,
            "subscription_status": user.subscription_status,
            "native_lang": user.native_lang,
            "target_lang": user.target_lang,
            "reminders_enabled": user.reminders_enabled,
            "timezone": user.timezone,
            "avatar_emoji": user.avatar_emoji,
            "show_on_leaderboard": user.show_on_leaderboard,
            "used_today": used_for_limit,
            "daily_limit": daily_limit,
            "is_trial": is_trial,
            "is_free_post_trial": is_free_post_trial,
        }


@router.get("/api/review")
async def get_review_words(telegram_id: int = Query(...)):
    async with SessionLocal() as session:
        user = await _get_user(session, telegram_id)
        if not user:
            return []
        now = datetime.now(timezone.utc)
        result = await session.execute(
            select(Word).where(
                Word.user_id == user.id, Word.next_review <= now
            ).order_by(Word.next_review.asc())
        )
        return [_serialize_word(w) for w in result.scalars().all()]


@router.post("/api/review")
async def submit_review(data: ReviewRequest, telegram_id: int = Query(...)):
    from core.word_service import process_review
    from core.bot_i18n import tier_up_text
    from core.telegram_send import send_message

    result_map = {1: "forgot", 3: "struggled", 5: "knew"}
    result = result_map.get(data.quality, "struggled")
    word, new_interval, tier_up = await process_review(data.word_id, result)

    analytics.capture(telegram_id, "review_submitted", {
        "result": result,
        "quality": data.quality,
        "tier_up": bool(tier_up),
        "mode": data.mode or "cards",
        "source": "miniapp",
    })

    # Streak milestone — фіксується тільки коли це перший review за сьогодні
    # (тобто streak саме інкрементнувся), щоб не задвоювати на наступних
    # відповідях того самого дня.
    from core.streaks import calculate_streak, reviewed_today
    MILESTONES = {3, 7, 14, 30, 60, 100}
    async with SessionLocal() as session:
        user_for_streak = await _get_user(session, telegram_id)
        if user_for_streak:
            today_count = await reviewed_today(session, user_for_streak.id)
            if today_count == 1:
                new_streak = await calculate_streak(session, user_for_streak.id)
                if new_streak in MILESTONES:
                    analytics.capture(telegram_id, "streak_milestone", {
                        "days": new_streak,
                    })

    # Якщо переступили tier — надсилаємо сторіс-вітання у бот-чат
    if tier_up:
        analytics.capture(telegram_id, "tier_unlocked", {
            "xp_threshold": tier_up[0],
            "tier_key": tier_up[1],
            "reward_key": tier_up[2],
        })
        async with SessionLocal() as session:
            user = await _get_user(session, telegram_id)
        lang = (user.native_lang if user else None) or "uk"
        threshold, tier_key, reward_key = tier_up
        try:
            await send_message(telegram_id, tier_up_text(lang, threshold, tier_key, reward_key))
        except Exception as e:
            logger.warning(f"tier-up send failed: {e}")

    return {
        "ok": bool(word),
        "interval_days": new_interval,
        "tier_up": (
            {"xp": tier_up[0], "tier_key": tier_up[1], "reward_key": tier_up[2]}
            if tier_up else None
        ),
    }


@router.post("/api/words")
async def add_word_endpoint(data: WordRequest, telegram_id: int = Query(...)):
    """Додає нове слово через міні-апп — той самий флоу, що й у боті."""
    from core.user_service import get_or_create_user, can_add_word, increment_word_counter
    from core.word_service import word_exists, save_word
    from core.openai_client import get_word_data
    from core.unsplash_client import search_image

    word = (data.word or "").strip()
    if not word:
        raise HTTPException(status_code=400, detail="Word is required")
    if len(word) < 2 or len(word) > 100:
        raise HTTPException(status_code=400, detail="Word must be 2–100 characters")

    user = await get_or_create_user(telegram_id=telegram_id)
    if not user.target_lang:
        return {"error": "setup_required"}

    can, reason = await can_add_word(user, user.native_lang)
    if not can:
        # plan="free" + не-trial → це новий weekly «хвіст» (3/7d), а не старий daily-блок.
        is_trial_now = bool(user.created_at and (datetime.now(timezone.utc) - user.created_at) < timedelta(days=7))
        is_pro_now = user.plan == "pro" and user.plan_expires_at and user.plan_expires_at > datetime.now(timezone.utc)
        period = "day" if (is_pro_now or is_trial_now) else "week"
        analytics.capture(telegram_id, "paywall_hit", {
            "reason": f"{period}_limit",
            "period": period,
            "plan": user.plan or "free",
            "used_today": user.words_added_today or 0,
            "source": "miniapp",
        })
        return {"error": "limit_reached", "message": reason}

    if await word_exists(user.id, word, user.target_lang):
        return {"error": "duplicate"}

    # Запускаємо OpenAI та Unsplash паралельно — Unsplash шукаємо за самим
    # словом, бо image_keyword від OpenAI у 95% збігається з ним. Економить
    # ~500мс на кожному новому слові (раніше було послідовно).
    import asyncio as _aio
    ai_task = _aio.create_task(get_word_data(
        word, target_lang=user.target_lang, native_lang=user.native_lang or "uk"
    ))
    image_task = _aio.create_task(search_image(word))

    ai_data = await ai_task
    if not ai_data:
        image_task.cancel()
        raise HTTPException(status_code=502, detail="AI generation failed")

    if ai_data.get("is_real") is False:
        image_task.cancel()
        analytics.capture(telegram_id, "word_rejected", {
            "target_lang": user.target_lang,
            "reason": "not_real",
            "source": "miniapp",
        })
        return {"error": "not_real_word", "word": word}

    image_url = await image_task

    success = await save_word(
        user_id=user.id, word=word, target_lang=user.target_lang,
        ai_data=ai_data, image_url=image_url,
    )
    if not success:
        raise HTTPException(status_code=500, detail="Failed to save word")

    await increment_word_counter(telegram_id)

    async with SessionLocal() as session:
        saved = (await session.execute(
            select(Word).where(
                Word.user_id == user.id,
                Word.word == word,
                Word.target_lang == user.target_lang,
            )
        )).scalar_one_or_none()

    analytics.capture(telegram_id, "word_added", {
        "target_lang": user.target_lang,
        "native_lang": user.native_lang,
        "has_image": bool(image_url),
        "source": "miniapp",
    })

    return {
        "ok": True,
        "word": _serialize_word(saved) if saved else None,
        "ai_data": ai_data,
        "image_url": image_url,
    }


@router.post("/api/words/bulk")
async def add_words_bulk_endpoint(data: WordsBulkRequest, telegram_id: int = Query(...)):
    """Додає одразу пачку слів (з набору пісні/теми) одним кліком.

    Поважає ліміт: рахуємо бюджет (`daily_limit - used`) наперед і беремо лише
    стільки нових слів, скільки дозволено — решта йде у skipped_limit (це і є
    природний paywall-nudge). Дублікати фільтруємо. AI+image генеруємо з
    обмеженою конкурентністю (semaphore=4), щоб 15-словний набір не тягнувся
    хвилину. Лічильник інкрементуємо один раз на фактично додані.
    """
    import asyncio as _aio
    from core.user_service import get_or_create_user, get_user_status
    from core.word_service import word_exists, save_word
    from core.openai_client import get_word_data
    from core.unsplash_client import search_image

    words = [(w or "").strip() for w in (data.words or [])]
    words = [w for w in words if 2 <= len(w) <= 100]
    # дедуп у межах самого запиту, зберігаємо порядок
    seen: set[str] = set()
    words = [w for w in words if not (w.lower() in seen or seen.add(w.lower()))]
    if not words:
        raise HTTPException(status_code=400, detail="No valid words")
    if len(words) > 60:
        words = words[:60]  # safety cap

    user = await get_or_create_user(telegram_id=telegram_id)
    if not user.target_lang:
        return {"error": "setup_required"}

    # Бюджет: скільки ще можна додати (daily_limit вже у тижневих одиницях для free)
    status = await get_user_status(user, user.native_lang)
    budget = max(0, int(status["daily_limit"]) - int(status["used_today"]))

    # Дублікати — паралельні перевірки існування
    exist_flags = await _aio.gather(*[
        word_exists(user.id, w, user.target_lang) for w in words
    ])
    duplicates = [w for w, ex in zip(words, exist_flags) if ex]
    fresh = [w for w, ex in zip(words, exist_flags) if not ex]

    to_add = fresh[:budget]
    skipped_limit = fresh[budget:]

    added: list[str] = []
    failed: list[str] = []

    if to_add:
        sem = _aio.Semaphore(4)

        async def _process(w: str):
            async with sem:
                try:
                    ai_task = _aio.create_task(get_word_data(
                        w, target_lang=user.target_lang, native_lang=user.native_lang or "uk"
                    ))
                    img_task = _aio.create_task(search_image(w))
                    ai_data = await ai_task
                    if not ai_data or ai_data.get("is_real") is False:
                        img_task.cancel()
                        failed.append(w)
                        return
                    image_url = await img_task
                    ok = await save_word(
                        user_id=user.id, word=w, target_lang=user.target_lang,
                        ai_data=ai_data, image_url=image_url,
                    )
                    (added if ok else failed).append(w)
                except Exception as e:
                    logger.warning(f"bulk add failed for {w!r}: {e}")
                    failed.append(w)

        await _aio.gather(*[_process(w) for w in to_add])

    # Інкремент лічильника один раз на фактично додані
    if added:
        async with SessionLocal() as session:
            u = (await session.execute(
                select(User).where(User.id == user.id)
            )).scalar_one_or_none()
            if u:
                u.words_added_today = (u.words_added_today or 0) + len(added)
                u.total_words = (u.total_words or 0) + len(added)
                await session.commit()

    analytics.capture(telegram_id, "words_bulk_added", {
        "target_lang": user.target_lang,
        "requested": len(words),
        "added": len(added),
        "duplicates": len(duplicates),
        "skipped_limit": len(skipped_limit),
        "failed": len(failed),
        "source": "miniapp",
    })

    return {
        "ok": True,
        "added": added,
        "duplicates": duplicates,
        "skipped_limit": skipped_limit,
        "failed": failed,
        "added_count": len(added),
        "limit_hit": len(skipped_limit) > 0,
    }


@router.get("/api/songs")
async def list_song_packs(telegram_id: int = Query(...)):
    """Повертає набори слів з пісень для target_lang юзера."""
    from core.song_packs import get_packs

    async with SessionLocal() as session:
        user = await _get_user(session, telegram_id)
        target = (user.target_lang if user else None) or "en"

    packs = get_packs(target)
    return {"target_lang": target, "packs": packs}


@router.get("/api/themes")
async def list_theme_packs(telegram_id: int = Query(...)):
    """Тематичні набори життєвої лексики для target_lang."""
    from core.theme_packs import get_theme_packs

    async with SessionLocal() as session:
        user = await _get_user(session, telegram_id)
        target = (user.target_lang if user else None) or "en"

    packs = get_theme_packs(target)
    return {"target_lang": target, "packs": packs}


@router.post("/api/export")
async def export_words(
    telegram_id: int = Query(...),
    format: str = Query("csv"),
):
    """Експорт всіх слів юзера. CSV — для всіх, APKG — лише Pro.

    Файл надсилається в бот-чат через Telegram Bot API — це надійний
    шлях у iOS Telegram WebView, де <a download> не працює.
    """
    from datetime import datetime as _dt
    from core.export import to_apkg, to_csv
    from core.telegram_send import send_document

    fmt = format.lower()
    if fmt not in ("csv", "apkg"):
        raise HTTPException(status_code=400, detail="format must be csv or apkg")

    async with SessionLocal() as session:
        user = await _get_user(session, telegram_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        now = datetime.now(timezone.utc)
        is_pro = user.plan == "pro" and user.plan_expires_at and user.plan_expires_at > now
        if fmt == "apkg" and not is_pro:
            raise HTTPException(status_code=402, detail="apkg export requires Pro")

        words = list((await session.execute(
            select(Word).where(Word.user_id == user.id).order_by(Word.created_at.asc())
        )).scalars().all())

    if not words:
        raise HTTPException(status_code=400, detail="No words to export")

    stamp = _dt.now().strftime("%Y%m%d")
    if fmt == "csv":
        file_bytes = to_csv(words)
        filename = f"wordsnap-{stamp}.csv"
        mime = "text/csv"
        caption = f"📥 CSV · {len(words)} words"
    else:
        file_bytes = to_apkg(words, telegram_id, user.target_lang)
        filename = f"wordsnap-{stamp}.apkg"
        mime = "application/octet-stream"
        caption = f"📥 Anki deck · {len(words)} words"

    sent = await send_document(
        chat_id=telegram_id,
        file_bytes=file_bytes,
        filename=filename,
        caption=caption,
        mime_type=mime,
    )
    if not sent:
        raise HTTPException(status_code=502, detail="Failed to send document")

    analytics.capture(telegram_id, "export_completed", {
        "format": fmt,
        "word_count": len(words),
    })
    return {"ok": True, "word_count": len(words), "filename": filename}


class SettingsRequest(BaseModel):
    native_lang: str | None = None
    target_lang: str | None = None
    reminders_enabled: bool | None = None
    timezone: str | None = None
    avatar_emoji: str | None = None
    show_on_leaderboard: bool | None = None


@router.patch("/api/user/settings")
async def update_user_settings(data: SettingsRequest, telegram_id: int = Query(...)):
    """Часткове оновлення налаштувань юзера. Тільки задані поля міняються."""
    from sqlalchemy import update as sa_update

    SUPPORTED_LANGS = {"uk", "en", "es", "pl", "de", "fr"}

    updates: dict = {}
    if data.native_lang is not None:
        if data.native_lang not in SUPPORTED_LANGS:
            raise HTTPException(status_code=400, detail="Unsupported native_lang")
        updates["native_lang"] = data.native_lang
    if data.target_lang is not None:
        if data.target_lang not in SUPPORTED_LANGS:
            raise HTTPException(status_code=400, detail="Unsupported target_lang")
        updates["target_lang"] = data.target_lang
    if data.reminders_enabled is not None:
        updates["reminders_enabled"] = bool(data.reminders_enabled)
    if data.timezone is not None:
        # Базова валідація — зберігаємо як є, у scheduler ZoneInfo() сам впаде
        # на bad value і ми залогуємо.
        if not isinstance(data.timezone, str) or len(data.timezone) > 50:
            raise HTTPException(status_code=400, detail="Bad timezone")
        updates["timezone"] = data.timezone
    if data.avatar_emoji is not None:
        from core.avatars import ALLOWED_AVATARS
        if data.avatar_emoji not in ALLOWED_AVATARS:
            raise HTTPException(status_code=400, detail="Unsupported avatar_emoji")
        updates["avatar_emoji"] = data.avatar_emoji
    if data.show_on_leaderboard is not None:
        updates["show_on_leaderboard"] = bool(data.show_on_leaderboard)

    if not updates:
        raise HTTPException(status_code=400, detail="Nothing to update")

    async with SessionLocal() as session:
        user = await _get_user(session, telegram_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        await session.execute(
            sa_update(User).where(User.id == user.id).values(**updates)
        )
        await session.commit()

    analytics.capture(telegram_id, "settings_updated", {
        "fields": list(updates.keys()),
    })
    return {"ok": True, "updated": list(updates.keys())}


@router.get("/api/referral")
async def get_referral(telegram_id: int = Query(...)):
    """Повертає реферальний код юзера, посилання та лічильник.

    Лінк формату `t.me/<bot>/app?startapp=ref_<code>` — direct mini-app entry
    (1 тап, без проміжного чату). Mini-app сам ловить `start_param` і
    викликає POST /api/apply_referral. Старий формат `?start=ref_<code>`
    також працює: bot/main.py досі обробляє його при /start payload.
    """
    from core.constants import bot_username
    from core.referral import REFERRAL_BONUS_DAYS, ensure_code

    async with SessionLocal() as session:
        user = await _get_user(session, telegram_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
    code = await ensure_code(user)
    return {
        "code": code,
        "link": f"https://t.me/{bot_username()}/app?startapp=ref_{code}",
        "referrals_count": user.referrals_count or 0,
        "bonus_days": REFERRAL_BONUS_DAYS,
    }


class ApplyReferralRequest(BaseModel):
    code: str  # без "ref_" префікса


@router.post("/api/apply_referral")
async def apply_referral_endpoint(
    data: ApplyReferralRequest, telegram_id: int = Query(...),
):
    """Apply a referral when invitee enters via mini-app deeplink.

    Mirror of the /start ref_<code> handler in bot/main.py: validates,
    applies, notifies referrer via Telegram. Idempotent — повторні виклики
    від того ж invitee, який вже має referrer'а, тихо повертають
    `{"applied": False, "reason": "already_referred_or_invalid"}`.
    """
    from core.referral import (
        REFERRAL_BONUS_DAYS,
        TRIAL_DAYS,
        apply_referral,
    )

    async with SessionLocal() as session:
        invitee = await _get_user(session, telegram_id)
        if not invitee:
            raise HTTPException(status_code=404, detail="User not found")

    # apply_referral сам відхилить self-referral, повторне застосування,
    # відсутній код тощо — повертаючи None.
    result = await apply_referral(invitee_id=invitee.id, referrer_code=data.code)
    if not result:
        return {"applied": False, "reason": "already_referred_or_invalid"}
    referrer, invitee = result

    # Сповістити referrer'а через Telegram (точно як bot/main.py:107-119).
    try:
        from bot.instance import bot as tg_bot
        from core.bot_i18n import t as bt
        referrer_lang = referrer.native_lang or "uk"
        await tg_bot.send_message(
            chat_id=referrer.telegram_id,
            text=bt(
                "referral.referrer_notify",
                referrer_lang,
                name=invitee.first_name or "friend",
                days=REFERRAL_BONUS_DAYS,
                total=referrer.referrals_count,
            ),
        )
    except Exception as exc:
        logger.warning(f"apply_referral_endpoint notify failed: {exc}")

    return {
        "applied": True,
        "bonus_days": REFERRAL_BONUS_DAYS,
        "trial_total_days": TRIAL_DAYS + REFERRAL_BONUS_DAYS,
    }


@router.get("/api/leaderboard")
async def leaderboard(telegram_id: int = Query(...)):
    """Топ-50 за total_xp серед тих хто вчить ту саму мову.
    Повертає рядки + ранг самого юзера (якщо поза топом — окремо)."""
    from sqlalchemy import func as sa_func

    async with SessionLocal() as session:
        me = await _get_user(session, telegram_id)
        if not me or not me.target_lang:
            return {"top": [], "self_rank": None, "target_lang": None}

        target = me.target_lang
        rows = (await session.execute(
            select(User).where(
                User.target_lang == target,
                User.total_xp > 0,
                User.show_on_leaderboard == True,  # noqa: E712
            ).order_by(User.total_xp.desc(), User.created_at.asc()).limit(50)
        )).scalars().all()

        # Ранг = кількість юзерів того ж target_lang з більшою кількістю XP + 1.
        # Тільки якщо у юзера є хоч одне XP І він opted-in.
        my_rank = None
        if (me.total_xp or 0) > 0 and me.show_on_leaderboard:
            higher = (await session.execute(
                select(sa_func.count(User.id)).where(
                    User.target_lang == target,
                    User.total_xp > me.total_xp,
                    User.show_on_leaderboard == True,  # noqa: E712
                )
            )).scalar() or 0
            my_rank = higher + 1

        from core.avatars import resolve_avatar

        def _row(u: User, rank: int) -> dict:
            return {
                "rank": rank,
                "first_name": (u.first_name or "Friend")[:14],
                "target_lang": u.target_lang,
                "total_xp": u.total_xp or 0,
                "streak_days": u.streak_days or 0,
                "avatar_emoji": resolve_avatar(u.avatar_emoji, u.telegram_id),
                "is_self": u.telegram_id == telegram_id,
                "is_pro": u.plan == "pro",
            }

        return {
            "top": [_row(u, i + 1) for i, u in enumerate(rows)],
            "self_rank": my_rank,
            "self_xp": me.total_xp or 0,
            "self_streak": me.streak_days or 0,
            "self_first_name": (me.first_name or "Ти")[:14],
            "self_avatar_emoji": resolve_avatar(me.avatar_emoji, me.telegram_id),
            "self_is_pro": me.plan == "pro",
            "target_lang": target,
        }


@router.get("/pay")
async def pay_redirect(telegram_id: int = Query(...), period: str = Query("monthly")):
    """Auto-submit HTML page що POST'ить форму на WayForPay HPP.

    Юзер тапає Get Pro у міні-апі → frontend відкриває цей URL → ця сторінка
    рендериться → JS сабмітить форму → WayForPay показує платіжку.
    Без цього прошарку клієнт відкривав би GET URL і отримував
    "Bad Request — this page requires only POST data".
    """
    from html import escape as html_escape
    from fastapi.responses import HTMLResponse
    from core.wayforpay_client import create_payment_link

    if period not in ("monthly", "annual"):
        raise HTTPException(status_code=400, detail="period must be monthly or annual")
    amount = 8.99 if period == "annual" else 1.49

    try:
        payment = create_payment_link(
            user_telegram_id=telegram_id,
            amount=amount,
            currency="USD",
            period=period,
        )
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e))

    analytics.capture(telegram_id, "buy_link_created", {
        "amount": amount, "period": period,
    })

    fields_html = "".join(
        f'<input type="hidden" name="{html_escape(str(k))}" value="{html_escape(str(v))}">'
        for k, v in payment["form_fields"].items()
    )
    html = (
        '<!doctype html><html><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<title>Redirecting…</title>'
        '<style>body{font-family:-apple-system,sans-serif;background:#FCE7F3;'
        'display:grid;place-items:center;min-height:100vh;margin:0;'
        'color:#0E0B1A}.box{text-align:center;padding:24px}'
        '.s{display:inline-block;width:24px;height:24px;border:3px solid #7C3AED;'
        'border-bottom-color:transparent;border-radius:50%;animation:r 0.8s linear infinite}'
        '@keyframes r{to{transform:rotate(360deg)}}</style></head>'
        '<body><div class="box"><div class="s"></div>'
        '<p style="margin-top:16px;font-weight:600">Opening WayForPay…</p></div>'
        f'<form id="f" method="POST" action="{html_escape(payment["form_url"])}">'
        f'{fields_html}</form>'
        '<script>document.getElementById("f").submit();</script>'
        '</body></html>'
    )
    return HTMLResponse(content=html)


@router.post("/api/wayforpay/callback")
@router.post("/wayforpay/callback")
async def wayforpay_callback(request: Request):
    """Webhook від WayForPay після платежу. Активує Pro якщо платіж successful.

    Зареєстрований на двох шляхах: канонічний `/api/wayforpay/callback` і
    legacy `/wayforpay/callback` (значення WAYFORPAY_WEBHOOK_URL у проді вказує
    на другий — без alias'у callback падав у 404 і Pro не активувався).

    Формат відповіді що очікує WayForPay:
        {
          "orderReference": "...",
          "status": "accept",
          "time": <unix>,
          "signature": "..."
        }
    """
    import time as _time
    from core.user_service import activate_pro_subscription
    from core.wayforpay_client import (
        verify_callback_signature,
        generate_response_signature,
    )

    # WayForPay часом шле application/x-www-form-urlencoded з єдиним полем JSON,
    # часом — справжній JSON. Спробуємо обидва.
    raw_body = (await request.body()).decode("utf-8", errors="ignore")
    data = None
    try:
        data = await request.json()
    except Exception:
        pass
    if not data:
        try:
            import json as _json
            data = _json.loads(raw_body)
        except Exception:
            try:
                form = await request.form()
                if len(form) == 1:
                    only_key = next(iter(form.keys()))
                    import json as _json
                    data = _json.loads(only_key) if only_key.startswith("{") else dict(form)
                else:
                    data = dict(form)
            except Exception:
                logger.error(f"WayForPay callback: cannot parse body: {raw_body[:300]!r}")
                raise HTTPException(status_code=400, detail="Bad payload")

    order_ref = str(data.get("orderReference", ""))
    transaction_status = str(data.get("transactionStatus", ""))
    reason_code = str(data.get("reasonCode", ""))
    amount = float(data.get("amount", 0) or 0)
    rec_token = data.get("recToken")

    logger.info(
        f"WayForPay callback: order={order_ref} status={transaction_status} "
        f"reason={reason_code} amount={amount}"
    )

    # Підпис обов'язковий — без нього не довіряємо
    if not verify_callback_signature(data):
        logger.warning(f"WayForPay: bad signature for {order_ref}")
        raise HTTPException(status_code=403, detail="Bad signature")

    # Парсимо order_reference: WS_<tg_id>_<period[:3]>_<ts> або
    # WS_<tg_id>_<ts> (legacy) або WS_REC_<tg_id>_<ts> (recurring)
    parts = order_ref.split("_")
    telegram_id: int | None = None
    period = "monthly"
    is_recurring = False
    try:
        if len(parts) >= 3 and parts[0] == "WS" and parts[1] == "REC":
            telegram_id = int(parts[2])
            is_recurring = True
        elif len(parts) >= 4 and parts[0] == "WS":
            telegram_id = int(parts[1])
            period_tag = parts[2]
            period = "annual" if period_tag.startswith("ann") else "monthly"
        elif len(parts) >= 3 and parts[0] == "WS":
            telegram_id = int(parts[1])
    except (ValueError, IndexError):
        logger.error(f"WayForPay: cannot parse order_reference {order_ref}")

    success = transaction_status == "Approved" and reason_code == "1100"

    # Записуємо в історію (одразу, навіть для невдалих платежів).
    # is_new_payment гейтить активацію Pro нижче — WayForPay може ретраїти
    # той самий callback, і без цього прапора Pro продовжувався б двічі за
    # одне списання. Кожне регулярне списання приходить з унікальним
    # orderReference, тому новий рядок == нове реальне списання.
    is_new_payment = False
    if telegram_id is not None:
        try:
            async with SessionLocal() as session:
                user = await _get_user(session, telegram_id)
                if user:
                    # Уникаємо дублікатів — order_reference унікальний
                    existing = (await session.execute(
                        select(PaymentHistory).where(
                            PaymentHistory.order_reference == order_ref
                        )
                    )).scalar_one_or_none()
                    if not existing:
                        is_new_payment = True
                        payment_row = PaymentHistory(
                            user_id=user.id,
                            order_reference=order_ref,
                            amount=amount,
                            currency=str(data.get("currency", "USD")),
                            status="success" if success else "failed",
                            transaction_status=transaction_status,
                            reason_code=reason_code,
                            reason=str(data.get("reason", "")),
                            is_recurring=is_recurring,
                            rec_token=str(rec_token) if rec_token else None,
                            raw_payload=data,
                        )
                        session.add(payment_row)
                        await session.commit()
                        await session.refresh(payment_row)
                        # Affiliate revenue-share: якщо у юзера активний
                        # affiliate_slug і успішний платіж - фіксуємо share.
                        # Невдалі платежі ігноруємо (не платимо інфлюенсеру
                        # за failed transaction'и).
                        if success:
                            try:
                                from core.affiliates import record_payment_share
                                await record_payment_share(
                                    user_id=user.id,
                                    payment_id=payment_row.id,
                                    payment_amount=float(amount),
                                    payment_currency=str(data.get("currency", "USD")),
                                )
                            except Exception as e:
                                logger.warning(
                                    f"WayForPay: affiliate share record failed: {e}"
                                )
        except Exception as e:
            logger.error(f"WayForPay: failed to save payment history: {e}", exc_info=True)

    # Активуємо/продовжуємо Pro лише на новий успішний платіж. Покриває і
    # перший платіж, і WayForPay-managed регулярні списання (вони теж летять
    # на цей serviceUrl з унікальним orderReference, is_recurring=False).
    # is_new_payment гарантує ідемпотентність проти повторних callback'ів.
    if success and telegram_id is not None and is_new_payment:
        duration_days = 365 if period == "annual" else 30
        try:
            await activate_pro_subscription(
                telegram_id=telegram_id,
                rec_token=str(rec_token) if rec_token else None,
                duration_days=duration_days,
                order_ref=order_ref,
            )
            # Сповіщаємо у бот-чат
            try:
                from core.telegram_send import send_message
                await send_message(
                    telegram_id,
                    f"🎉 <b>Pro активовано на {duration_days} днів!</b>\n\nДякую — без обмежень снапай скільки хочеш.",
                )
            except Exception as e:
                logger.warning(f"WayForPay: notify user failed: {e}")
        except Exception as e:
            logger.error(f"WayForPay: activate_pro failed for {telegram_id}: {e}", exc_info=True)

    # Відповідь WayForPay у правильному форматі
    now = int(_time.time())
    return {
        "orderReference": order_ref,
        "status": "accept",
        "time": now,
        "signature": generate_response_signature(order_ref, "accept", now),
    }


@router.post("/api/buy")
async def create_buy_link(
    request: Request,
    telegram_id: int = Query(...),
    period: str = Query("monthly"),
):
    """Створює URL що веде на /pay-сторінку нашого бекенду. /pay рендерить
    auto-submit POST форму, бо WayForPay HPP вимагає POST а не GET.
    period — 'monthly' (default) | 'annual'."""

    if period not in ("monthly", "annual"):
        raise HTTPException(status_code=400, detail="period must be monthly or annual")
    amount = 8.99 if period == "annual" else 1.49

    # Будуємо URL поточного хоста: схема + хост + /pay?…
    # За Railway-проксі request.url.scheme = http (TLS термінується на проксі),
    # тому форсимо https — інакше деякі in-app браузери ламають redirect.
    scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
    if scheme == "http":
        scheme = "https"
    base = f"{scheme}://{request.url.netloc}"
    payment_url = f"{base}/pay?telegram_id={telegram_id}&period={period}"

    return {
        "payment_url": payment_url,
        "period": period,
        "amount": amount,
    }


@router.post("/api/buy/stars")
async def create_stars_invoice(
    telegram_id: int = Query(...),
    period: str = Query("monthly"),
):
    """Створює Telegram Stars (XTR) invoice link для оплати Pro.

    Mini-app потім відкриває цей link через `tg.openInvoice(link, cb)` —
    native flow без виходу з мініапки. Successful_payment ловить
    `backend/bot/main.py` (handler нижче) і активує Pro через
    `activate_pro_subscription`.

    Тарифи в Stars обрано на ~30% вище за USD-номінал картки — Telegram
    бере ~30% при конвертації Stars → fiat (≈$0.013/Star при withdraw),
    тому щоб бот по чистому отримував стільки ж, скільки з картки, ціна
    в Stars має бути піднята на цей коефіцієнт:
      monthly: 129 ★ (~$1.68 → ~$1.18 net after TG conversion)
      annual:  799 ★ (~$10.39 → ~$10.39 net)

    Stars НЕ підтримують auto-renew нативно — це разова оплата. Recurring
    залишається на карті (WayForPay).

    NB про `provider_token=""`: Telegram Bot API явно вимагає **порожній
    рядок** для currency='XTR' (а не None / відсутній). aiogram 3.13.1 з
    default `provider_token=None` падає на стороні Telegram → ось чому без
    цього параметра ендпойнт повертав 500.
    """
    if period not in ("monthly", "annual"):
        raise HTTPException(status_code=400, detail="period must be monthly or annual")

    stars_price = 129 if period == "monthly" else 799
    duration_days = 30 if period == "monthly" else 365

    # payload кодує юзера+період+ts для ідентифікації в successful_payment.
    # 64-байт ліміт Telegram для invoice payload — наш формат вкладається.
    ts = int(datetime.now(timezone.utc).timestamp())
    invoice_payload = f"stars_{telegram_id}_{period}_{ts}"

    from bot.instance import bot as tg_bot
    from aiogram.types import LabeledPrice

    try:
        link = await tg_bot.create_invoice_link(
            title="WordSnap Pro",
            description=(
                f"WordSnap Pro — {duration_days} days of unlimited "
                f"learning (one-time payment, no auto-renew)"
            ),
            payload=invoice_payload,
            provider_token="",   # MUST be empty string for XTR (see docstring)
            currency="XTR",
            prices=[LabeledPrice(label=f"Pro {period}", amount=stars_price)],
        )
    except Exception as e:
        # Включаємо текст помилки у відповідь — у проді stack trace йде у logger,
        # а юзеру повертаємо короткий рядок щоб у devtools було видно реальну причину
        # (інакше Railway віддає bland "Internal Server Error" без деталей).
        logger.exception(f"create_invoice_link failed for {telegram_id}: {e}")
        raise HTTPException(status_code=500, detail=f"invoice creation failed: {type(e).__name__}: {e}")

    analytics.capture(telegram_id, "stars_invoice_created", {
        "period": period,
        "stars_amount": stars_price,
    })

    return {
        "invoice_link": link,
        "period": period,
        "stars_amount": stars_price,
        "duration_days": duration_days,
    }


@router.post("/api/cancel_subscription")
async def cancel_subscription_endpoint(telegram_id: int = Query(...)):
    """Скасовує авто-продовження підписки. Pro лишається активним до кінця
    оплаченого періоду (`plan_expires_at`), нових списань не буде.

    Спершу прибираємо WayForPay-managed регулярку через regularApi REMOVE
    (щоб WayForPay перестав списувати), потім ставимо локальний стан
    cancelled. Локальний стан міняємо завжди — навіть якщо WayForPay-виклик
    не вдався, щоб поважати намір юзера (а збій логуємо й повертаємо у
    відповіді, щоб фронт міг показати «зверніться в підтримку»)."""
    from core.user_service import cancel_subscription as _cancel_db
    from core.wayforpay_client import cancel_regular_payment

    async with SessionLocal() as session:
        user = await _get_user(session, telegram_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        order_ref = user.subscription_order_ref
        plan_expires_at = user.plan_expires_at

    wayforpay_removed = True
    wfp_reason = None
    if order_ref:
        result = await cancel_regular_payment(order_ref)
        wayforpay_removed = result["success"]
        wfp_reason = result.get("reason")
        if not wayforpay_removed:
            logger.warning(
                f"cancel_subscription: WayForPay REMOVE failed for {telegram_id} "
                f"order={order_ref}: {result.get('reason_code')} {wfp_reason}"
            )

    await _cancel_db(telegram_id)

    analytics.capture(telegram_id, "subscription_cancelled", {
        "wayforpay_removed": wayforpay_removed,
        "reason": wfp_reason,
        "had_order_ref": bool(order_ref),
    })

    return {
        "cancelled": True,
        "wayforpay_removed": wayforpay_removed,
        "pro_until": plan_expires_at.isoformat() if plan_expires_at else None,
    }


class SaveSurveyRequest(BaseModel):
    payload: str  # composite `/start` payload (igads_<camp>_<lang>_<mot>)


@router.post("/api/onboarding/save_survey")
async def save_survey_endpoint(
    data: SaveSurveyRequest, telegram_id: int = Query(...),
):
    """Persist on-landing survey results when ad-cohort entered the mini-app
    directly (without going through bot /start). Parses composite payload via
    the same `parse_ad_payload` helper as the bot survey_handler, applies
    target_lang/motivation/acquisition_payload to the user. Idempotent.
    """
    from bot.handlers.survey_handler import parse_ad_payload
    from core.affiliates import apply_affiliate_to_user, parse_affiliate_payload
    from sqlalchemy import update as sa_update

    # Affiliate flow: payload `aff_<slug>` приймаємо тут теж - якщо юзер
    # відкрив mini-app напряму через universal link (а не /start у боті).
    aff_slug = parse_affiliate_payload(data.payload)

    parsed = parse_ad_payload(data.payload)
    payload_lang = parsed["lang"]
    payload_mot = parsed["motivation"]

    async with SessionLocal() as session:
        user = await _get_user(session, telegram_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        updates: dict = {"acquisition_payload": data.payload}
        applied: dict = {}
        if payload_lang and not user.target_lang:
            updates["target_lang"] = payload_lang
            applied["target_lang"] = payload_lang
        if payload_mot and not user.motivation:
            updates["motivation"] = payload_mot
            applied["motivation"] = payload_mot

        await session.execute(
            sa_update(User).where(User.id == user.id).values(**updates)
        )
        await session.commit()

    # Affiliate first-touch (через mini-app direct universal link).
    affiliate_applied = False
    if aff_slug:
        affiliate_applied = await apply_affiliate_to_user(user.id, aff_slug)
        if affiliate_applied:
            applied["affiliate_slug"] = aff_slug

    analytics.capture(telegram_id, "onboarding_survey_saved", {
        "payload": data.payload,
        "campaign": parsed["campaign"],
        "lang_from_payload": payload_lang,
        "motivation_from_payload": payload_mot,
        "affiliate_slug": aff_slug,
        "affiliate_applied": affiliate_applied,
        "applied": applied,
        "source": "miniapp_direct",
    })
    if payload_lang:
        analytics.identify(telegram_id, {"target_lang": payload_lang})
    if payload_mot:
        analytics.identify(telegram_id, {"motivation": payload_mot})

    return {
        "applied": applied,
        "campaign": parsed["campaign"],
        "target_lang": payload_lang,
        "motivation": payload_mot,
    }


# ── Demo lander (/demo) — email capture endpoint ────────────────────────────
# Public endpoint, no auth. Захищаємо мінімально: email-regex + rate-limit
# через IP+email композитного unique key (немає race на duplicate insert).
import re as _re

_EMAIL_RE = _re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


class CaptureLeadRequest(BaseModel):
    email: str
    source: str | None = None
    campaign: str | None = None
    ui_lang: str | None = None
    target_lang: str | None = None
    distinct_id: str | None = None


@router.post("/api/lead/capture")
async def capture_lead(data: CaptureLeadRequest, request: Request):
    """Зберігає email-lead з демо-лендера. Idempotent через UNIQUE(email, source).
    Анонімний endpoint — не вимагає telegram_id.
    """
    from core.models import Lead
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    email = (data.email or "").strip().lower()
    if not email or len(email) > 320 or not _EMAIL_RE.match(email):
        raise HTTPException(status_code=400, detail="invalid_email")

    ip = (request.client.host if request.client else None) or "?"
    ua = (request.headers.get("user-agent") or "")[:1000]

    async with SessionLocal() as session:
        stmt = pg_insert(Lead).values(
            email=email,
            source=(data.source or "")[:60] or None,
            campaign=(data.campaign or "")[:120] or None,
            ui_lang=(data.ui_lang or "")[:8] or None,
            target_lang=(data.target_lang or "")[:8] or None,
            distinct_id=(data.distinct_id or "")[:80] or None,
            ip=ip[:64],
            user_agent=ua,
        ).on_conflict_do_nothing(index_elements=["email", "source"])
        await session.execute(stmt)
        await session.commit()

    analytics.capture(
        distinct_id=data.distinct_id or email,
        event="lead_captured",
        properties={
            "email_hash": email[:3] + "***@" + email.split("@")[-1] if "@" in email else "?",
            "source": data.source,
            "campaign": data.campaign,
            "ui_lang": data.ui_lang,
            "target_lang": data.target_lang,
        },
    )
    return {"ok": True}
