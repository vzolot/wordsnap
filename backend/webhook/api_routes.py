"""
REST API для miniapp.
"""
import logging
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Query, HTTPException
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


class ReviewRequest(BaseModel):
    word_id: int
    quality: int = 3


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

        learned = (await session.execute(
            select(func.count(Word.id)).where(
                Word.user_id == user.id, Word.status == "mastered"
            )
        )).scalar() or 0

        reviewed_today = await _reviewed_today(session, user.id)
        streak = await _calculate_streak(session, user.id)
        total_spent = await _total_spent(session, user.id)

        # XP за сьогодні: сума по reviews сьогодні. Окремо від total_xp щоб
        # на Home показувати динаміку дня, а не накопичення за весь час.
        today_start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        today_review_rows = (await session.execute(
            select(Review.result, func.count().label("n")).where(
                Review.user_id == user.id,
                Review.reviewed_at >= today_start,
            ).group_by(Review.result)
        )).all()
        xp_today = sum(xp_for_result(r.result) * int(r.n) for r in today_review_rows)

        now = datetime.now(timezone.utc)
        is_pro = user.plan == "pro" and user.plan_expires_at and user.plan_expires_at > now
        is_trial = (not is_pro) and user.created_at and (now - user.created_at) < timedelta(days=7)
        if is_pro:
            daily_limit = 100
        elif is_trial:
            daily_limit = 10
        else:
            daily_limit = 0  # post-trial — заблоковано, лише Pro

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
            "native_lang": user.native_lang,
            "target_lang": user.target_lang,
            "used_today": user.words_added_today,
            "daily_limit": daily_limit,
            "is_trial": is_trial,
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
        "source": "miniapp",
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
        return {"error": "limit_reached", "message": reason}

    if await word_exists(user.id, word, user.target_lang):
        return {"error": "duplicate"}

    ai_data = await get_word_data(
        word, target_lang=user.target_lang, native_lang=user.native_lang or "uk"
    )
    if not ai_data:
        raise HTTPException(status_code=502, detail="AI generation failed")

    # Чекаємо Unsplash так само як це робить бот (~500 мс): asyncio.create_task
    # у FastAPI request не гарантує що фоновий task завершиться, бо Uvicorn
    # може закрити scope раніше. Тому йдемо синхронним шляхом для надійності.
    image_keyword = ai_data.get("image_keyword", word)
    image_url = await search_image(image_keyword)

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


@router.get("/api/songs")
async def list_song_packs(telegram_id: int = Query(...)):
    """Повертає набори слів з пісень для target_lang юзера."""
    from core.song_packs import get_packs

    async with SessionLocal() as session:
        user = await _get_user(session, telegram_id)
        target = (user.target_lang if user else None) or "en"

    packs = get_packs(target)
    return {"target_lang": target, "packs": packs}


@router.post("/api/buy")
async def create_buy_link(telegram_id: int = Query(...)):
    """Створює посилання на оплату Pro для конкретного юзера."""
    from core.wayforpay_client import create_payment_link
    try:
        payment = create_payment_link(
            user_telegram_id=telegram_id,
            amount=1.49,
            currency="USD",
        )
        analytics.capture(telegram_id, "buy_link_created", {"amount": 1.49})
        return {
            "payment_url": payment["payment_url"],
            "order_reference": payment["order_reference"],
        }
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to create payment link")
