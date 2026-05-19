"""
Планувальник автоматичних recurring charges.
Кожну годину перевіряє кому час продовжувати підписку.
"""
import logging
import asyncio
from datetime import datetime, timezone
from sqlalchemy import select, and_

from core.db import SessionLocal
from core.models import User, PaymentHistory
from core.wayforpay_client import charge_recurring
from core.user_service import activate_pro_subscription, expire_subscription

logger = logging.getLogger(__name__)

# Перевіряємо кожну годину
CHECK_INTERVAL_SECONDS = 3600


async def process_renewals(bot):
    """Шукає юзерів яких час продовжувати і списує з картки"""
    try:
        now = datetime.now(timezone.utc)
        
        async with SessionLocal() as session:
            # Знаходимо юзерів: Pro + auto_renew + час списувати
            result = await session.execute(
                select(User).where(
                    and_(
                        User.plan == "pro",
                        User.auto_renew == True,
                        User.payment_rec_token.is_not(None),
                        User.next_charge_date.is_not(None),
                        User.next_charge_date <= now,
                    )
                )
            )
            users_to_charge = list(result.scalars().all())
        
        if not users_to_charge:
            return
        
        logger.info(f"💳 Processing {len(users_to_charge)} recurring charges")
        
        for user in users_to_charge:
            await _charge_user(user, bot)
            await asyncio.sleep(0.5)  # Не задовбуємо WayForPay API
        
    except Exception as e:
        logger.error(f"Recurring charges error: {e}", exc_info=True)


async def _charge_user(user: User, bot) -> None:
    """Списує з одного юзера"""
    try:
        result = await charge_recurring(
            rec_token=user.payment_rec_token,
            user_telegram_id=user.telegram_id,
        )
        
        # Логуємо платіж
        await _log_recurring_payment(user, result)
        
        if result["success"]:
            # Успіх → продовжуємо Pro
            await activate_pro_subscription(
                telegram_id=user.telegram_id,
                rec_token=user.payment_rec_token,  # той самий токен
                duration_days=30,
            )
            
            # Юзера сповіщає activate_pro_subscription через webhook
            # Але webhook не приходить для recurring — тож сповіщаємо тут
            try:
                from datetime import timedelta
                new_expires = (user.plan_expires_at or datetime.now(timezone.utc)) + timedelta(days=30)
                await bot.send_message(
                    chat_id=user.telegram_id,
                    text=(
                        "🔄 <b>Pro підписка автоматично продовжена!</b>\n\n"
                        f"💳 Списано $1.49 з картки\n"
                        f"📅 Дійсна до: <b>{new_expires.strftime('%d.%m.%Y')}</b>\n\n"
                        "<i>Дякуємо що з нами! 🚀</i>"
                    ),
                )
            except Exception as e:
                logger.warning(f"Failed to notify {user.telegram_id}: {e}")
            
            logger.info(f"✅ Renewed Pro for user {user.telegram_id}")
        
        else:
            # Помилка → деактивуємо і шлемо повідомлення
            logger.warning(
                f"❌ Failed to charge user {user.telegram_id}: "
                f"{result['reason_code']} {result['reason']}"
            )
            
            await expire_subscription(user.telegram_id)
            
            try:
                await bot.send_message(
                    chat_id=user.telegram_id,
                    text=(
                        "⚠️ <b>Не вдалось продовжити Pro підписку</b>\n\n"
                        "Не вийшло списати кошти з картки. Можливі причини:\n"
                        "• Недостатньо коштів\n"
                        "• Картка заблокована або прострочена\n"
                        "• Банк відхилив транзакцію\n\n"
                        "Твоя підписка переведена на FREE план.\n"
                        "Щоб поновити — натисни /buy і онови картку."
                    ),
                )
            except Exception as e:
                logger.warning(f"Failed to notify {user.telegram_id} about failed charge: {e}")
                
    except Exception as e:
        logger.error(f"Error charging user {user.telegram_id}: {e}", exc_info=True)


async def _log_recurring_payment(user: User, result: dict) -> None:
    """Записує recurring payment в історію + affiliate revenue-share."""
    try:
        async with SessionLocal() as session:
            payment = PaymentHistory(
                user_id=user.id,
                order_reference=result["order_reference"],
                amount=1.49,
                currency="USD",
                status="Approved" if result["success"] else "Declined",
                transaction_status=result.get("transaction_status", ""),
                reason_code=result.get("reason_code", ""),
                reason=result.get("reason", ""),
                is_recurring=True,
                rec_token=user.payment_rec_token,
                raw_payload=result.get("raw", {}),
            )
            session.add(payment)
            await session.commit()
            await session.refresh(payment)
            # Affiliate share для recurring-charges теж — інфлюенсер отримує
            # 20% з кожного повторного списання (поки юзер у window'і
            # `affiliate_at + duration_days`).
            if result.get("success"):
                try:
                    from core.affiliates import record_payment_share
                    await record_payment_share(
                        user_id=user.id,
                        payment_id=payment.id,
                        payment_amount=1.49,
                        payment_currency="USD",
                    )
                except Exception as e:
                    logger.warning(f"recurring: affiliate share failed: {e}")
    except Exception as e:
        logger.error(f"Failed to log recurring payment: {e}")


async def recurring_charges_loop(bot):
    """Головний цикл. Запускається з bot/main.py"""
    logger.info("💳 Recurring charges scheduler started")
    
    # Чекаємо хвилину перед першим запуском
    await asyncio.sleep(60)
    
    while True:
        try:
            await process_renewals(bot)
        except Exception as e:
            logger.error(f"Recurring loop error: {e}")
        
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)