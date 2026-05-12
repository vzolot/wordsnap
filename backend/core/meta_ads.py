"""Read-only Meta Marketing API client for the admin /stats_admin_ads commands.

Pulls paid-ads performance (impressions / reach / link clicks / CTR / CPC /
spend) for the WordSnap ad account. Mirrors the digest the threads-bot repo
sends from `scripts/ads_pipeline.py` / `@engage_wsbot`.

Needs on the backend's Railway service:
  - META_ADS_ACCESS_TOKEN  — system-user token with `ads_read` (or ads_management)
  - META_AD_ACCOUNT_ID     — numeric ad account id (the `act_` prefix is added)
  - META_ADS_API_VERSION   — optional, defaults to v23.0

Campaigns/ads themselves are created from the threads-bot repo — this module
only reports, never writes.
"""
from __future__ import annotations

import logging
import os
from html import escape
from typing import Any, Literal

import httpx

logger = logging.getLogger(__name__)

GRAPH_BASE = "https://graph.facebook.com"

AdsPeriod = Literal["today", "yesterday", "last_30d"]

_PERIOD_LABEL: dict[AdsPeriod, str] = {
    "today": "сьогодні (з 00:00)",
    "yesterday": "вчора",
    "last_30d": "останні 30 днів",
}

_INSIGHT_FIELDS = (
    "campaign_name,impressions,reach,clicks,ctr,cpc,spend,actions,cost_per_action_type"
)


def _creds() -> tuple[str, str, str] | None:
    token = os.getenv("META_ADS_ACCESS_TOKEN", "").strip()
    acct = os.getenv("META_AD_ACCOUNT_ID", "").strip()
    if not token or not acct:
        return None
    if not acct.startswith("act_"):
        acct = f"act_{acct}"
    version = os.getenv("META_ADS_API_VERSION", "v23.0").strip() or "v23.0"
    return token, acct, version


def _link_clicks(row: dict[str, Any]) -> tuple[int | None, float | None]:
    clicks: int | None = None
    for a in row.get("actions") or []:
        if a.get("action_type") == "link_click":
            clicks = int(float(a.get("value", 0)))
    cpc: float | None = None
    for a in row.get("cost_per_action_type") or []:
        if a.get("action_type") == "link_click":
            cpc = float(a.get("value", 0))
    return clicks, cpc


async def build_ads_report(period: AdsPeriod) -> str:
    """Return an HTML digest of paid-ads performance for `period`."""
    creds = _creds()
    if creds is None:
        return (
            "⚠️ <b>META_ADS_* не налаштовано</b> на цьому сервісі.\n"
            "Додай у Railway env: <code>META_ADS_ACCESS_TOKEN</code>, "
            "<code>META_AD_ACCOUNT_ID</code> (і опц. <code>META_ADS_API_VERSION</code>)."
        )
    token, acct, version = creds
    base = f"{GRAPH_BASE}/{version}"
    header = f"📣 <b>Реклама — {_PERIOD_LABEL[period]}</b>"

    async with httpx.AsyncClient(timeout=30) as client:
        try:
            r = await client.get(
                f"{base}/{acct}/campaigns",
                params={"fields": "name,effective_status", "limit": 50, "access_token": token},
            )
            r.raise_for_status()
            campaigns = r.json().get("data", [])
        except Exception as e:  # noqa: BLE001 — surface a friendly message, log the detail
            logger.error("ads report: list campaigns failed: %s", e, exc_info=True)
            return f"{header}\n\n⚠️ Не вдалось дістати список кампаній — глянь логи."

        if not campaigns:
            return f"{header}\n\nКампаній ще немає."

        lines = [header]
        total_spend = 0.0
        total_clicks = 0
        had_data = False
        for c in campaigns:
            cid = c["id"]
            try:
                ir = await client.get(
                    f"{base}/{cid}/insights",
                    params={
                        "level": "campaign",
                        "date_preset": period,
                        "fields": _INSIGHT_FIELDS,
                        "access_token": token,
                    },
                )
                ir.raise_for_status()
                rows = ir.json().get("data", [])
            except Exception as e:  # noqa: BLE001
                logger.warning("ads report: insights for %s failed: %s", cid, e)
                continue
            if not rows:
                continue
            had_data = True
            row = rows[0]
            name = escape(str(row.get("campaign_name", cid)))
            impressions = int(float(row.get("impressions", 0)))
            reach = int(float(row.get("reach", 0)))
            spend = float(row.get("spend", 0))
            ctr = float(row.get("ctr", 0))
            clicks, cpc = _link_clicks(row)
            if clicks is None:
                clicks = int(float(row.get("clicks", 0)))
            total_spend += spend
            total_clicks += clicks
            cpc_part = f" · CPC {cpc:.2f}" if cpc is not None else ""
            lines.append(
                f"\n<b>{name}</b>\n"
                f"  показів {impressions:,} · охоплення {reach:,}\n"
                f"  кліків {clicks} · CTR {ctr:.2f}%{cpc_part}\n"
                f"  витрачено {spend:.2f}"
            )

    if not had_data:
        lines.append("\n<i>Поки без показів (кампанія щойно активована або на review Meta).</i>")
    else:
        lines.append(f"\n<b>Разом:</b> {total_clicks} кліків · {total_spend:.2f} витрачено")
    return "\n".join(lines)
