"""TON-USD spot price with 1-hour memoisation.

Shared between `webhook/api_routes.py` (the /api/buy/ton/init endpoint
that quotes invoices) and `scheduler/ton_watcher.py` (which credits
affiliate revenue share in USD-equivalent at the time the payment lands).
Was previously inlined as a module-level cache inside api_routes; the
watcher used a hardcoded $1.70/TON for its affiliate computation, which
silently bit-rotted as soon as TON moved.

CoinGecko's free `/simple/price` endpoint is rate-limited at ~30 calls/min
— we hit it at most once an hour, well within bounds. Any failure (network,
5xx, parse error) falls back to the last successful price, ultimately to
the hardcoded $1.70 if we've never fetched.

Targets that DRIVE the dynamic invoice amounts also live here so the two
callers stay in sync — bump them in one place when the card / Stars pricing
changes.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx

logger = logging.getLogger(__name__)

_TON_PRICE_CACHE: dict = {"price_usd": 1.70, "fetched_at": None}
_TON_PRICE_TTL_SECONDS = 3600

# Target net USD per period — matches card net after WayForPay 3%
# (monthly $1.49 × 0.97 ≈ $1.45, annual $8.99 × 0.97 ≈ $8.72; targets bumped
# slightly above for the buffer the user wanted when Stars pricing was set).
TARGET_NET_USD = {"monthly": 1.50, "annual": 9.00}
MIN_TON = {"monthly": 1.0, "annual": 2.0}


async def get_ton_price_usd() -> float:
    """Returns the current TON price in USD with 1-hour memoisation.
    Async because the underlying httpx call is async; safe to call from
    any awaitable context. Logs the new price on every refresh so we can
    sanity-check from Railway logs."""
    now = datetime.now(timezone.utc)
    cached_at = _TON_PRICE_CACHE.get("fetched_at")
    if cached_at and (now - cached_at).total_seconds() < _TON_PRICE_TTL_SECONDS:
        return _TON_PRICE_CACHE["price_usd"]
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(
                "https://api.coingecko.com/api/v3/simple/price",
                params={"ids": "the-open-network", "vs_currencies": "usd"},
            )
            r.raise_for_status()
            price = float(r.json()["the-open-network"]["usd"])
            if price > 0:
                _TON_PRICE_CACHE.update({"price_usd": price, "fetched_at": now})
                logger.info("ton price refreshed: $%.3f", price)
                return price
    except Exception as exc:
        logger.warning(
            "ton price fetch failed (using cached $%.3f): %s",
            _TON_PRICE_CACHE["price_usd"], exc,
        )
    return _TON_PRICE_CACHE["price_usd"]
