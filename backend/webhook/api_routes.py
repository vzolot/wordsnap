"""
REST API для miniapp.
"""
from datetime import datetime, timezone
from fastapi import APIRouter, Query, HTTPException
from sqlalchemy import select, func

from core.db import SessionLocal
from core.models import User, Word

router = APIRouter()


def _serialize_word(w: Word) -> dict:
    return {
        "id": w.id,
        "word": w.word,
        "translation": w.translation,
        "part_of_speech": w.part_of_speech,
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
    async with SessionLocal() as session:
        user = await _get_user(session, telegram_id)
        if not user:
            return {
                "total_words": 0, "learned_words": 0, "streak": 0,
                "plan": "free", "plan_expires_at": None,
            }

        learned = (await session.execute(
            select(func.count(Word.id)).where(
                Word.user_id == user.id, Word.status == "mastered"
            )
        )).scalar() or 0

        now = datetime.now(timezone.utc)
        is_pro = user.plan == "pro" and user.plan_expires_at and user.plan_expires_at > now

        return {
            "total_words": user.total_words,
            "learned_words": learned,
            "streak": user.streak_days,
            "plan": "pro" if is_pro else user.plan,
            "plan_expires_at": user.plan_expires_at.isoformat() if user.plan_expires_at else None,
            "auto_renew": user.auto_renew,
            "native_lang": user.native_lang,
            "target_lang": user.target_lang,
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
async def submit_review(data: dict, telegram_id: int = Query(...)):
    from core.word_service import process_review

    word_id = data.get("word_id")
    quality = data.get("quality", 3)
    if not word_id:
        raise HTTPException(status_code=400, detail="word_id is required")

    result_map = {1: "forgot", 3: "struggled", 5: "knew"}
    result = result_map.get(quality, "struggled")

    word, new_interval = await process_review(word_id, result)
    return {"ok": bool(word), "interval_days": new_interval}


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
