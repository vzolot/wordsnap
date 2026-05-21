"""
WayForPay integration з підтримкою Regular (Recurring) Payments.

Документація: 
- Purchase API: https://wiki.wayforpay.com/uk/view/852102
- Regular Payments: https://wiki.wayforpay.com/uk/view/8783175
"""
import os
import time
import hmac
import hashlib
import logging
import httpx
from typing import TypedDict
from urllib.parse import urlencode, urlparse
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

MERCHANT_LOGIN = os.getenv("WAYFORPAY_MERCHANT_LOGIN", "")
MERCHANT_SECRET = os.getenv("WAYFORPAY_MERCHANT_SECRET", "")
MERCHANT_PASSWORD = os.getenv("WAYFORPAY_MERCHANT_PASSWORD", "")
MERCHANT_DOMAIN = os.getenv("WAYFORPAY_MERCHANT_DOMAIN", "t.me/WordSnapBot")
RETURN_URL = os.getenv("WAYFORPAY_RETURN_URL", "https://t.me/WordSnapBot")
WEBHOOK_URL = os.getenv("WAYFORPAY_WEBHOOK_URL", "")

# URLs
WAYFORPAY_PURCHASE_URL = "https://secure.wayforpay.com/pay"
WAYFORPAY_API_URL = "https://api.wayforpay.com/api"
WAYFORPAY_REGULAR_API_URL = "https://api.wayforpay.com/regularApi"


def _public_base() -> str:
    """Origin нашого бекенду — для self-hosted /pay auto-submit сторінки."""
    if WEBHOOK_URL:
        p = urlparse(WEBHOOK_URL)
        if p.scheme and p.netloc:
            return f"{p.scheme}://{p.netloc}"
    return os.getenv("PUBLIC_BASE_URL", "https://worker-production-abd5.up.railway.app")


def pay_page_url(telegram_id: int, period: str = "monthly") -> str:
    """URL нашої /pay сторінки (рендерить POST-форму). НЕ прямий WayForPay GET —
    той дає 'Bad Request, this page requires only POST data'."""
    return f"{_public_base()}/pay?telegram_id={telegram_id}&period={period}"

# Параметри підписки
SUBSCRIPTION_AMOUNT = 1.49
SUBSCRIPTION_CURRENCY = "USD"
SUBSCRIPTION_DAYS = 30


class PaymentLink(TypedDict):
    payment_url: str
    order_reference: str


def _hmac_md5(message: str, secret: str) -> str:
    """HMAC-MD5 підпис для WayForPay"""
    return hmac.new(
        secret.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.md5,
    ).hexdigest()


# === ПЕРШИЙ ПЛАТІЖ (Purchase API) ===

def generate_purchase_signature(
    merchant_account: str,
    merchant_domain: str,
    order_reference: str,
    order_date: int,
    amount: float,
    currency: str,
    product_names: list[str],
    product_counts: list[int],
    product_prices: list[float],
) -> str:
    """Генерує signature для запиту на оплату."""
    parts = [
        merchant_account,
        merchant_domain,
        order_reference,
        str(order_date),
        str(amount),
        currency,
        *product_names,
        *[str(c) for c in product_counts],
        *[str(p) for p in product_prices],
    ]
    message = ";".join(parts)
    return _hmac_md5(message, MERCHANT_SECRET)


def create_payment_link(
    user_telegram_id: int,
    amount: float = SUBSCRIPTION_AMOUNT,
    currency: str = SUBSCRIPTION_CURRENCY,
    period: str = "monthly",
) -> PaymentLink:
    """
    Створює посилання на ПЕРШИЙ платіж.
    WayForPay автоматично запам'ятає картку якщо в кабінеті увімкнено
    'Збереження карток' (за замовчуванням так).

    period — 'monthly' | 'annual'. Впливає на product_name та order_reference,
    щоб у webhook'у можна було відрізнити підписки і нарахувати правильну
    тривалість Pro.
    """
    if not MERCHANT_LOGIN or not MERCHANT_SECRET:
        raise ValueError("WayForPay credentials not configured")

    order_reference = f"WS_{user_telegram_id}_{period[:3]}_{int(time.time())}"
    order_date = int(time.time())

    if period == "annual":
        product_names = ["WordSnap Pro - 365 days"]
    else:
        product_names = ["WordSnap Pro - 30 days"]
    product_counts = [1]
    product_prices = [amount]
    
    signature = generate_purchase_signature(
        merchant_account=MERCHANT_LOGIN,
        merchant_domain=MERCHANT_DOMAIN,
        order_reference=order_reference,
        order_date=order_date,
        amount=amount,
        currency=currency,
        product_names=product_names,
        product_counts=product_counts,
        product_prices=product_prices,
    )
    
    params = {
        "merchantAccount": MERCHANT_LOGIN,
        "merchantDomainName": MERCHANT_DOMAIN,
        "merchantSignature": signature,
        "orderReference": order_reference,
        "orderDate": order_date,
        "amount": amount,
        "currency": currency,
        "productName[]": product_names[0],
        "productCount[]": product_counts[0],
        "productPrice[]": product_prices[0],
        "clientFirstName": f"User{user_telegram_id}",
        "clientEmail": f"user{user_telegram_id}@wordsnap.app",
        "language": "UA",
        "returnUrl": RETURN_URL,
    }

    # --- Регулярні платежі (WayForPay-managed subscription) ---
    # WayForPay сам списує щомісяця/щороку і шле callback на serviceUrl за
    # кожне списання. Ці поля НЕ входять у purchase-signature (підпис покриває
    # лише account;domain;orderRef;date;amount;currency;names;counts;prices),
    # тому додавання їх не ламає підпис. Перше списання — зараз, наступне —
    # через period. dateEnd не ставимо → підписка бесстрокова поки юзер не
    # скасує (REMOVE токена через remove_recurring_token).
    from datetime import datetime as _dt, timedelta as _td
    if period == "annual":
        regular_mode = "yearly"
        next_charge = _dt.now() + _td(days=365)
    else:
        regular_mode = "monthly"
        next_charge = _dt.now() + _td(days=30)
    params["regularMode"] = regular_mode
    params["regularOn"] = "1"
    params["regularAmount"] = amount
    params["dateNext"] = next_charge.strftime("%d.%m.%Y")

    if WEBHOOK_URL:
        params["serviceUrl"] = WEBHOOK_URL

    # WayForPay HPP вимагає POST-форму. payment_url як GET давав "Bad Request,
    # this page requires only POST data". Тому повертаємо params як dict —
    # /pay endpoint рендеритиме HTML auto-submit форму.
    payment_url = f"{WAYFORPAY_PURCHASE_URL}?{urlencode(params)}"

    logger.info(f"Created payment link for user {user_telegram_id}, order {order_reference}")

    return {
        "payment_url": payment_url,
        "order_reference": order_reference,
        "form_url": WAYFORPAY_PURCHASE_URL,
        "form_fields": params,
    }


# === ПЕРЕВІРКА CALLBACK ===

def verify_callback_signature(data: dict) -> bool:
    """
    Перевіряє підпис callback від WayForPay.
    Формат: merchantAccount;orderReference;amount;currency;authCode;cardPan;transactionStatus;reasonCode
    """
    received_signature = data.get("merchantSignature", "")
    
    parts = [
        str(data.get("merchantAccount", "")),
        str(data.get("orderReference", "")),
        str(data.get("amount", "")),
        str(data.get("currency", "")),
        str(data.get("authCode", "")),
        str(data.get("cardPan", "")),
        str(data.get("transactionStatus", "")),
        str(data.get("reasonCode", "")),
    ]
    message = ";".join(parts)
    expected_signature = _hmac_md5(message, MERCHANT_SECRET)
    
    is_valid = received_signature == expected_signature
    if not is_valid:
        logger.warning(f"Invalid WayForPay signature for order {data.get('orderReference')}")
    
    return is_valid


def generate_response_signature(
    order_reference: str,
    status: str,
    time_value: int,
) -> str:
    """Signature для відповіді WayForPay."""
    message = f"{order_reference};{status};{time_value}"
    return _hmac_md5(message, MERCHANT_SECRET)


# === RECURRING / REGULAR PAYMENTS ===

def generate_charge_signature(
    merchant_account: str,
    order_reference: str,
    amount: float,
    currency: str,
) -> str:
    """
    Signature для CHARGE запиту (recurring списання).
    Формат: merchantAccount;orderReference;amount;currency
    """
    message = f"{merchant_account};{order_reference};{amount};{currency}"
    return _hmac_md5(message, MERCHANT_SECRET)


async def charge_recurring(
    rec_token: str,
    user_telegram_id: int,
    amount: float = SUBSCRIPTION_AMOUNT,
    currency: str = SUBSCRIPTION_CURRENCY,
) -> dict:
    """
    Виконує АВТОМАТИЧНЕ списання за збереженим токеном картки.
    Викликається з cron-задачі коли підходить час продовження.
    
    Returns: dict з відповіддю WayForPay
        - reasonCode == "1100" → успіх
        - reasonCode != "1100" → помилка (брак коштів, заблокована картка тощо)
    """
    order_reference = f"WS_REC_{user_telegram_id}_{int(time.time())}"
    
    signature = generate_charge_signature(
        merchant_account=MERCHANT_LOGIN,
        order_reference=order_reference,
        amount=amount,
        currency=currency,
    )
    
    payload = {
        "transactionType": "CHARGE",
        "merchantAccount": MERCHANT_LOGIN,
        "merchantAuthType": "SimpleSignature",
        "merchantSignature": signature,
        "apiVersion": 1,
        "orderReference": order_reference,
        "amount": amount,
        "currency": currency,
        "recToken": rec_token,
        "productName": ["WordSnap Pro - 30 days (renewal)"],
        "productCount": [1],
        "productPrice": [amount],
    }
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                WAYFORPAY_API_URL,
                json=payload,
            )
            data = response.json()
            
            logger.info(
                f"Recurring charge for user {user_telegram_id}: "
                f"reasonCode={data.get('reasonCode')} reason={data.get('reason')}"
            )
            
            return {
                "success": str(data.get("reasonCode")) == "1100",
                "order_reference": order_reference,
                "reason_code": str(data.get("reasonCode", "")),
                "reason": data.get("reason", ""),
                "transaction_status": data.get("transactionStatus", ""),
                "raw": data,
            }
            
    except httpx.TimeoutException:
        logger.error(f"WayForPay timeout for user {user_telegram_id}")
        return {
            "success": False,
            "order_reference": order_reference,
            "reason_code": "TIMEOUT",
            "reason": "Request timeout",
            "raw": {},
        }
    except Exception as e:
        logger.error(f"WayForPay charge error: {e}", exc_info=True)
        return {
            "success": False,
            "order_reference": order_reference,
            "reason_code": "ERROR",
            "reason": str(e),
            "raw": {},
        }


async def cancel_regular_payment(order_reference: str) -> dict:
    """Скасовує WayForPay-managed регулярну підписку через regularApi REMOVE.

    На відміну від Purchase/Charge (підпис secret key), regularApi
    автентифікується merchantPassword (значення «Merchant password» з кабінету,
    воно вже у форматі готового хешу). orderReference — це ref першого платежу
    що створив регулярку (зберігаємо у users.subscription_order_ref).

    Returns dict: success (reasonCode 4100 = Ok), reason_code, reason, raw.
    """
    if not MERCHANT_PASSWORD:
        return {"success": False, "reason_code": "NO_PASSWORD",
                "reason": "WAYFORPAY_MERCHANT_PASSWORD not configured", "raw": {}}

    payload = {
        "requestType": "REMOVE",
        "merchantAccount": MERCHANT_LOGIN,
        "merchantPassword": MERCHANT_PASSWORD,
        "orderReference": order_reference,
    }
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(WAYFORPAY_REGULAR_API_URL, json=payload)
            data = response.json()
            code = str(data.get("reasonCode", ""))
            logger.info(
                f"WayForPay regularApi REMOVE order={order_reference}: "
                f"reasonCode={code} reason={data.get('reason')}"
            )
            # 4100 = removed; 4102 = "Rule is not found" → регулярки вже нема,
            # що і є бажаним кінцевим станом (майбутніх списань не буде). Обидва
            # трактуємо як успіх скасування.
            return {
                "success": code in ("4100", "4102"),
                "reason_code": code,
                "reason": data.get("reason", ""),
                "raw": data,
            }
    except Exception as e:
        logger.error(f"WayForPay regularApi REMOVE error: {e}", exc_info=True)
        return {"success": False, "reason_code": "ERROR", "reason": str(e), "raw": {}}


async def remove_recurring_token(rec_token: str) -> bool:
    """
    Видаляє збережений токен картки в WayForPay.
    Викликається коли юзер скасовує підписку.
    """
    signature_message = f"{MERCHANT_LOGIN};{rec_token}"
    signature = _hmac_md5(signature_message, MERCHANT_SECRET)
    
    payload = {
        "transactionType": "REMOVE",
        "merchantAccount": MERCHANT_LOGIN,
        "merchantAuthType": "SimpleSignature",
        "merchantSignature": signature,
        "apiVersion": 1,
        "recToken": rec_token,
    }
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(WAYFORPAY_API_URL, json=payload)
            data = response.json()
            success = str(data.get("reasonCode")) == "1100"
            logger.info(f"Token removal: success={success}, response={data}")
            return success
    except Exception as e:
        logger.error(f"Token removal error: {e}")
        return False