"""TON blockchain watcher — converts on-chain payments to Pro activations.

How it works:

1. Frontend (ProPage) hits `POST /api/buy/ton/init` → backend writes a row
   to `payment_history` with `currency='TON'`, `status='pending'`, and
   `order_reference` = a short unique `comment` string like
   `ws_<telegram_id>_<period>_<short_ts>`.
2. User signs a TON Connect transaction in Tonkeeper that includes this
   comment as the payment's TL-B text-comment payload. The TON network
   confirms the transaction onto our wallet (`WORDSNAP_TON_WALLET`).
3. This loop polls TONAPI every 90 seconds for recent transactions on our
   wallet. For each incoming tx with a comment matching the `ws_*` pattern,
   we look up the pending `payment_history` row, activate Pro through
   `activate_pro_subscription()`, mark the row `success`, and stash the tx
   hash + raw payload for audit.

Why polling instead of webhooks: TONAPI does offer webhooks (Cocoon) but
they require additional setup and a public callback URL we'd have to secure.
A 90-second polling loop costs ~1000 free-tier requests/day (well within
limits), and the latency penalty is acceptable for a one-time top-up flow
where the user is already shown "waiting for chain confirmation…".

Idempotency: we look up by `order_reference` and only flip pending →
success. If the same tx is seen twice (TONAPI re-serving, restart, etc.),
the second update is a no-op because the row is already `success`.

Failed amounts: if a user sends a different amount than they were quoted
(e.g. wallet UI rounding, attempts to underpay), we still activate Pro on
match. The `payment_history.amount` records the actual amount received, so
revenue accounting stays honest. Stronger anti-underpay logic is a TODO if
real users start gaming it (extremely unlikely at this scale).
"""
from __future__ import annotations

import asyncio
import base64
import logging
import os
import re
from datetime import datetime, timezone

import httpx
from sqlalchemy import select, update as sa_update

from core.db import SessionLocal
from core.models import PaymentHistory, User
from core.user_service import activate_pro_subscription

logger = logging.getLogger(__name__)

# 90s = ~960 requests/day to TONAPI (free tier is ~1 RPS sustained, way more
# than enough). UX: «waiting for chain confirmation» message stays for up to
# 90s in the worst case which feels OK for a one-time TON payment.
CHECK_INTERVAL_SECONDS = 90
TONAPI_BASE = "https://tonapi.io/v2"

# Comment pattern emitted by `/api/buy/ton/init`: ws_<telegram_id>_<period>_<short_ts>
_COMMENT_RE = re.compile(r"^ws_\d+_(?:monthly|annual)_\d{1,6}$")


def _parse_period_from_comment(comment: str) -> str | None:
    """`ws_469478065_monthly_123456` → `monthly`."""
    if not _COMMENT_RE.match(comment):
        return None
    parts = comment.split("_")
    if len(parts) < 4:
        return None
    return parts[2] if parts[2] in ("monthly", "annual") else None


def _extract_comment(action: dict) -> str | None:
    """TONAPI returns parsed TonTransfer actions where the human-readable
    comment is sometimes already extracted into `comment`, sometimes only
    available as raw `payload` (hex of the comment cell — op 0x00000000 +
    UTF-8 text). Try both."""
    tt = action.get("TonTransfer") or {}
    if tt.get("comment"):
        return str(tt["comment"])
    # Raw cell — first 8 hex chars are the op code, then UTF-8 text.
    raw = tt.get("payload") or ""
    if not raw:
        return None
    if raw.startswith("00000000"):
        try:
            return bytes.fromhex(raw[8:]).decode("utf-8", errors="ignore").strip("\x00 ")
        except Exception:
            return None
    return None


async def _fetch_recent_events(wallet: str, api_key: str, limit: int = 30) -> list[dict]:
    """Pull recent events (≈ transactions) on our wallet. Returns parsed
    action list. Errors are logged + swallowed; the loop will retry next tick."""
    url = f"{TONAPI_BASE}/accounts/{wallet}/events"
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.get(url, headers=headers, params={"limit": limit})
            r.raise_for_status()
            data = r.json()
            return data.get("events", []) or []
    except Exception as exc:
        logger.warning("TONAPI fetch failed: %s", exc)
        return []


async def _process_event(ev: dict, wallet: str) -> None:
    """For each TON-transfer-to-us in this event, see if the comment matches
    a pending payment_history row → activate Pro + mark success.

    Address-match rationale: dropped. TONAPI returns recipient addresses in
    raw `0:hex` form, but the env var `WORDSNAP_TON_WALLET` is the friendly
    `UQ…` base64 — string comparison (and the loose substring fallback I had
    initially) never matched. We could canonicalise via a TON address lib,
    but the comment alone is sufficient: it's a unique self-issued tag of
    the form `ws_<tg_id>_<period>_<short_ts>` that only exists for an
    invoice WE created. If we see a TonTransfer with that comment in OUR
    wallet's event stream, it's our payment. The payment_history lookup +
    `status == 'success'` short-circuit covers idempotency. Outgoing
    refunds also appear in the event stream but won't carry our comment
    format, so they're a no-op."""
    for action in ev.get("actions", []) or []:
        if action.get("type") != "TonTransfer":
            continue
        tt = action.get("TonTransfer") or {}
        comment = _extract_comment(action)
        if not comment or not _COMMENT_RE.match(comment):
            continue

        amount_nano = int(tt.get("amount") or 0)
        amount_ton = round(amount_nano / 1_000_000_000, 4)
        tx_hash = ev.get("event_id")

        async with SessionLocal() as session:
            ph = (await session.execute(
                select(PaymentHistory).where(PaymentHistory.order_reference == comment)
            )).scalar_one_or_none()
            if ph is None:
                logger.info("ton: tx with unknown comment %s, ignoring", comment)
                continue
            if ph.status == "success":
                # Already credited — TONAPI re-serving an already-processed event.
                continue

            user = (await session.execute(
                select(User).where(User.id == ph.user_id)
            )).scalar_one_or_none()
            if user is None:
                logger.error("ton: payment %s references missing user %s", comment, ph.user_id)
                continue

            period = _parse_period_from_comment(comment) or "monthly"
            duration_days = 30 if period == "monthly" else 365

            activated = await activate_pro_subscription(
                telegram_id=user.telegram_id,
                rec_token=None,                # TON doesn't have recurring tokens
                duration_days=duration_days,
                order_ref=comment,
            )
            if not activated:
                logger.error("ton: activate_pro_subscription failed for %s", user.telegram_id)
                continue

            # subscription_status="one_time" — same reason as Stars: scheduler
            # must NOT try to recurring-charge this user (no card token).
            await session.execute(
                sa_update(User).where(User.id == user.id).values(
                    subscription_status="one_time"
                )
            )
            # Flip pending → success with the actual received amount + tx hash.
            await session.execute(
                sa_update(PaymentHistory).where(PaymentHistory.id == ph.id).values(
                    status="success",
                    transaction_status="Approved",
                    amount=amount_ton,
                    raw_payload={
                        "tx_hash": tx_hash,
                        "amount_nano": amount_nano,
                        "from_address": (tt.get("sender") or {}).get("address"),
                        "event_id": tx_hash,
                    },
                )
            )
            await session.commit()

            logger.info(
                "ton: ✅ Pro activated for tg_id=%s via tx %s (%s TON, period=%s)",
                user.telegram_id, tx_hash, amount_ton, period,
            )

        # Best-effort affiliate share — same idea as Stars handler. Uses the
        # live TON spot price (with 1h cache) so the share % is calibrated
        # to what TON was actually worth when the payment landed, not a
        # bit-rotted $1.70 from when Phase 2 shipped.
        try:
            from core.affiliates import record_payment_share
            from core.ton_pricing import get_ton_price_usd
            ton_price_usd = await get_ton_price_usd()
            usd_equiv = round(amount_ton * ton_price_usd, 2)
            await record_payment_share(
                user_id=ph.user_id,
                payment_id=ph.id,
                payment_amount=usd_equiv,
                payment_currency="USD",
            )
        except Exception as e:
            logger.warning("ton affiliate share failed (non-fatal): %s", e)

        # Best-effort thank-you message to the user.
        try:
            from bot.instance import bot as tg_bot
            await tg_bot.send_message(
                chat_id=user.telegram_id,
                text=(
                    f"⚡ <b>TON payment received!</b>\n\n"
                    f"WordSnap Pro is active for {duration_days} days. "
                    f"Enjoy unlimited learning 💜"
                ),
            )
        except Exception as e:
            logger.warning("ton thank-you message failed: %s", e)


async def ton_watcher_loop(bot=None) -> None:
    """Run forever, polling TONAPI every CHECK_INTERVAL_SECONDS for new
    transactions on `WORDSNAP_TON_WALLET`. `bot` arg accepted for parity
    with the other schedulers but currently unused — thank-you messages
    use the lazy `from bot.instance import bot` import to dodge the
    re-execute-on-main bug (see bot/instance.py docstring)."""
    wallet = os.getenv("WORDSNAP_TON_WALLET")
    api_key = os.getenv("TONAPI_KEY")
    if not wallet or not api_key:
        logger.warning(
            "ton_watcher: WORDSNAP_TON_WALLET / TONAPI_KEY not set — loop disabled."
        )
        return

    logger.info("⚡ TON watcher started (poll every %ds, wallet=%s...)",
                CHECK_INTERVAL_SECONDS, wallet[:12])

    while True:
        try:
            events = await _fetch_recent_events(wallet, api_key)
            for ev in events:
                await _process_event(ev, wallet)
        except Exception as exc:
            logger.exception("ton_watcher tick crashed: %s", exc)
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)
