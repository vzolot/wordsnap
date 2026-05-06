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


@router.get("/api/referral")
async def get_referral(telegram_id: int = Query(...)):
    """Повертає реферальний код юзера, посилання та лічильник."""
    from core.constants import bot_username
    from core.referral import REFERRAL_BONUS_DAYS, ensure_code

    async with SessionLocal() as session:
        user = await _get_user(session, telegram_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
    code = await ensure_code(user)
    return {
        "code": code,
        "link": f"https://t.me/{bot_username()}?start=ref_{code}",
        "referrals_count": user.referrals_count or 0,
        "bonus_days": REFERRAL_BONUS_DAYS,
    }


@router.post("/api/wayforpay/callback")
async def wayforpay_callback(request: Request):
    """Webhook від WayForPay після платежу. Активує Pro якщо платіж successful.

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

    # Записуємо в історію (одразу, навіть для невдалих платежів)
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
                        session.add(PaymentHistory(
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
                        ))
                        await session.commit()
        except Exception as e:
            logger.error(f"WayForPay: failed to save payment history: {e}", exc_info=True)

    # Активуємо Pro лише при успіху
    if success and telegram_id is not None and not is_recurring:
        duration_days = 365 if period == "annual" else 30
        try:
            await activate_pro_subscription(
                telegram_id=telegram_id,
                rec_token=str(rec_token) if rec_token else None,
                duration_days=duration_days,
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
    telegram_id: int = Query(...),
    period: str = Query("monthly"),
):
    """Створює посилання на оплату Pro. period — 'monthly' (default) | 'annual'.
    Annual = $8.99 за рік (≈50% знижка від $1.49 × 12)."""
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
        analytics.capture(telegram_id, "buy_link_created", {
            "amount": amount, "period": period,
        })
        return {
            "payment_url": payment["payment_url"],
            "order_reference": payment["order_reference"],
            "period": period,
            "amount": amount,
        }
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to create payment link")
