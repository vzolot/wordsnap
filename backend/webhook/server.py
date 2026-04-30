"""
FastAPI webhook server для прийому callback від WayForPay.
"""
import logging
import time
from datetime import datetime, timezone
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select

from core.wayforpay_client import (
    verify_callback_signature,
    generate_response_signature,
)
from core.user_service import activate_pro_subscription
from core.db import SessionLocal
from core.models import PaymentHistory, User

logger = logging.getLogger(__name__)

app = FastAPI(title="WordSnap Webhooks")


@app.get("/")
async def root():
    return {"status": "ok", "service": "WordSnap Webhooks"}


@app.get("/health")
async def health():
    return {"status": "healthy", "timestamp": datetime.now(timezone.utc).isoformat()}


@app.post("/wayforpay/callback")
async def wayforpay_callback(request: Request):
    try:
        content_type = request.headers.get("content-type", "")
        if "application/json" in content_type:
            data = await request.json()
        else:
            form = await request.form()
            data = dict(form)
        
        order_reference = data.get("orderReference", "")
        logger.info(f"WayForPay callback: order={order_reference}, status={data.get('transactionStatus')}")
        
        if not verify_callback_signature(data):
            logger.error(f"Invalid signature for order {order_reference}")
            return _build_response(order_reference, "accept")
        
        await _log_payment(data)
        
        transaction_status = data.get("transactionStatus", "")
        if transaction_status != "Approved":
            logger.info(f"Transaction not approved: {transaction_status} for {order_reference}")
            return _build_response(order_reference, "accept")
        
        try:
            parts = order_reference.split("_")
            if parts[1] == "REC":
                telegram_id = int(parts[2])
                is_recurring = True
            else:
                telegram_id = int(parts[1])
                is_recurring = False
        except (IndexError, ValueError):
            logger.error(f"Cannot parse telegram_id from {order_reference}")
            return _build_response(order_reference, "accept")
        
        rec_token = data.get("recToken")
        if rec_token:
            logger.info(f"Got recToken for user {telegram_id}")
        
        user = await activate_pro_subscription(
            telegram_id=telegram_id,
            rec_token=rec_token,
            duration_days=30,
        )
        
        if not user:
            logger.error(f"Failed to activate Pro for {telegram_id}")
            return _build_response(order_reference, "accept")
        
        await _notify_user(telegram_id, user, is_recurring)
        
        return _build_response(order_reference, "accept")
        
    except Exception as e:
        logger.error(f"Webhook error: {e}", exc_info=True)
        return _build_response("unknown", "accept")


async def _log_payment(data: dict) -> None:
    try:
        order_reference = data.get("orderReference", "")
        try:
            parts = order_reference.split("_")
            telegram_id = int(parts[2]) if parts[1] == "REC" else int(parts[1])
        except (IndexError, ValueError):
            telegram_id = None
        
        async with SessionLocal() as session:
            user_id = None
            if telegram_id:
                result = await session.execute(
                    select(User).where(User.telegram_id == telegram_id)
                )
                user = result.scalar_one_or_none()
                if user:
                    user_id = user.id
            
            if not user_id:
                return
            
            existing = await session.execute(
                select(PaymentHistory).where(PaymentHistory.order_reference == order_reference)
            )
            if existing.scalar_one_or_none():
                return
            
            payment = PaymentHistory(
                user_id=user_id,
                order_reference=order_reference,
                amount=float(data.get("amount", 0)),
                currency=data.get("currency", "USD"),
                status=data.get("transactionStatus", "Unknown"),
                transaction_status=data.get("transactionStatus"),
                reason_code=str(data.get("reasonCode", "")),
                reason=data.get("reason"),
                is_recurring="REC" in order_reference,
                rec_token=data.get("recToken"),
                raw_payload=data,
            )
            session.add(payment)
            await session.commit()
            
    except Exception as e:
        logger.error(f"Failed to log payment: {e}")


async def _notify_user(telegram_id: int, user, is_recurring: bool) -> None:
    try:
        from bot.main import bot
        
        if is_recurring:
            text = (
                "🔄 <b>Pro підписка автоматично продовжена!</b>\n\n"
                f"💳 Списано $1.49 з твоєї картки\n"
                f"📅 Дійсна до: <b>{user.plan_expires_at.strftime('%d.%m.%Y')}</b>\n\n"
                "<i>Дякуємо що з нами! 🚀</i>\n\n"
                "/subscription — інфо про підписку"
            )
        else:
            text = (
                "💎 <b>Pro підписка активована!</b>\n\n"
                "Дякуємо за покупку! Тепер тобі доступно:\n"
                "✅ <b>100 слів на день</b>\n"
                "✅ Розширена статистика\n"
                "✅ Тематичні набори (скоро)\n\n"
                f"📅 Дійсна до: <b>{user.plan_expires_at.strftime('%d.%m.%Y')}</b>\n"
                f"🔄 Автопродовження: <b>{'ввімкнено' if user.auto_renew else 'вимкнено'}</b>\n\n"
                "/subscription — інфо\n"
                "/unsubscribe — скасувати автопродовження"
            )
        
        await bot.send_message(chat_id=telegram_id, text=text)
    except Exception as e:
        logger.warning(f"Failed to notify user {telegram_id}: {e}")


def _build_response(order_reference: str, status: str) -> JSONResponse:
    response_time = int(time.time())
    signature = generate_response_signature(order_reference, status, response_time)
    return JSONResponse({
        "orderReference": order_reference,
        "status": status,
        "time": response_time,
        "signature": signature,
    })
