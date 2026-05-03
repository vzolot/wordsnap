"""
REST API для miniapp.
"""
from datetime import datetime, timezone
from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, func

from core.db import SessionLocal
from core.models import User, Word

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


@router.get("/api/stats")
async def get_stats(telegram_id: int = Query(...)):
    from datetime import timedelta
    async with SessionLocal() as session:
        user = await _get_user(session, telegram_id)
        if not user:
            return {
                "total_words": 0, "learned_words": 0, "streak": 0,
                "plan": "free", "plan_expires_at": None,
                "used_today": 0, "daily_limit": 10,
                "native_lang": "uk", "target_lang": None,
            }

        learned = (await session.execute(
            select(func.count(Word.id)).where(
                Word.user_id == user.id, Word.status == "mastered"
            )
        )).scalar() or 0

        now = datetime.now(timezone.utc)
        is_pro = user.plan == "pro" and user.plan_expires_at and user.plan_expires_at > now
        is_trial = (not is_pro) and user.created_at and (now - user.created_at) < timedelta(days=7)
        daily_limit = 100 if (is_pro or is_trial) else 10

        return {
            "total_words": user.total_words,
            "learned_words": learned,
            "streak": user.streak_days,
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
    result_map = {1: "forgot", 3: "struggled", 5: "knew"}
    result = result_map.get(data.quality, "struggled")
    word, new_interval = await process_review(data.word_id, result)
    return {"ok": bool(word), "interval_days": new_interval}


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

    image_url = await search_image(ai_data.get("image_keyword", word))

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
        return {
            "payment_url": payment["payment_url"],
            "order_reference": payment["order_reference"],
        }
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to create payment link")
