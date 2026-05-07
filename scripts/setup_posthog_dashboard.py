#!/usr/bin/env python3
"""Створює дашборд + 8 готових інсайтів у PostHog через REST API.

Використовує СУЧАСНИЙ query-format (HogQL-based) — PostHog нещодавно
заблокували legacy `filters` API для нових акаунтів.

Ідемпотентний — якщо інсайт із тим самим ім'ям уже є на дашборді, пропускає.

Використання:
    export POSTHOG_PERSONAL_API_KEY='phx_...'   # PostHog → Settings → Personal API Keys
    export POSTHOG_PROJECT_ID='12345'           # числовий ID з URL
    export POSTHOG_HOST='https://eu.posthog.com'  # опційно
    python3 scripts/setup_posthog_dashboard.py
"""
from __future__ import annotations

import os
import sys
from typing import Any

try:
    import requests
except ImportError:
    print("Install requests: pip install requests", file=sys.stderr)
    sys.exit(1)


HOST = os.environ.get("POSTHOG_HOST", "https://eu.posthog.com").rstrip("/")
PROJECT_ID = os.environ.get("POSTHOG_PROJECT_ID")
PERSONAL_KEY = os.environ.get("POSTHOG_PERSONAL_API_KEY")
DASHBOARD_NAME = "WordSnap Core"

if not PROJECT_ID or not PERSONAL_KEY:
    print(
        "Missing env. Set POSTHOG_PROJECT_ID and POSTHOG_PERSONAL_API_KEY.",
        file=sys.stderr,
    )
    sys.exit(2)

HEADERS = {
    "Authorization": f"Bearer {PERSONAL_KEY}",
    "Content-Type": "application/json",
}
BASE = f"{HOST}/api/projects/{PROJECT_ID}"


# ── Query builders (modern PostHog query format) ────────────────────────
def event_node(event: str, properties: dict | None = None, math: str = "total") -> dict:
    """Будує EventsNode у форматі query API."""
    node: dict[str, Any] = {"kind": "EventsNode", "event": event, "name": event, "math": math}
    if properties:
        node["properties"] = [
            {"key": k, "value": v, "operator": "exact", "type": "event"}
            for k, v in properties.items()
        ]
    return node


def funnel_query(
    series: list[dict],
    window_interval: int,
    window_unit: str,  # "second" | "minute" | "hour" | "day" | "week"
    date_from: str = "-30d",
    breakdown: str | None = None,
) -> dict:
    src: dict[str, Any] = {
        "kind": "FunnelsQuery",
        "series": series,
        "funnelsFilter": {
            "funnelWindowInterval": window_interval,
            "funnelWindowIntervalUnit": window_unit,
        },
        "dateRange": {"date_from": date_from},
    }
    if breakdown:
        src["breakdownFilter"] = {"breakdown": breakdown, "breakdown_type": "event"}
    return {"kind": "InsightVizNode", "source": src}


def trend_query(
    series: list[dict],
    breakdown: str | None = None,
    interval: str = "week",
    date_from: str = "-30d",
) -> dict:
    src: dict[str, Any] = {
        "kind": "TrendsQuery",
        "series": series,
        "interval": interval,
        "dateRange": {"date_from": date_from},
        "trendsFilter": {"display": "ActionsLineGraph"},
    }
    if breakdown:
        src["breakdownFilter"] = {"breakdown": breakdown, "breakdown_type": "event"}
    return {"kind": "InsightVizNode", "source": src}


# ── Інсайти ─────────────────────────────────────────────────────────────
INSIGHTS: list[dict] = [
    {
        "name": "1. Activation funnel (new user → first review)",
        "description": "З /start у боті до першого review_submitted. Drop-off показує де нові юзери губляться.",
        "query": funnel_query(
            series=[
                event_node("user_started"),
                event_node("lang_selected"),
                event_node("region_selected"),
                event_node("word_added", {"source": "bot_setup"}),
                event_node("review_submitted"),
            ],
            window_interval=7,
            window_unit="day",
        ),
    },
    {
        "name": "2. Pro conversion (precise)",
        "description": "pro_page_viewed → buy_clicked → buy_open_attempt → payment_succeeded. Покаже на якому кроці втрачаєш конверсію.",
        "query": funnel_query(
            series=[
                event_node("pro_page_viewed"),
                event_node("buy_clicked"),
                event_node("buy_open_attempt"),
                event_node("payment_succeeded"),
            ],
            window_interval=30,
            window_unit="minute",
            breakdown="period",
        ),
    },
    {
        "name": "3. Paywall → upgrade",
        "description": "Як часто free-tier limit конвертить у Pro. Найважливіший монетизаційний funnel.",
        "query": funnel_query(
            series=[
                event_node("paywall_hit", {"reason": "daily_limit"}),
                event_node("pro_page_viewed"),
                event_node("buy_clicked"),
                event_node("payment_succeeded"),
            ],
            window_interval=7,
            window_unit="day",
        ),
    },
    {
        "name": "4. Welcome stories engagement",
        "description": "Скільки людей долистує до s3 (там CTA +10 днів Pro).",
        "query": funnel_query(
            series=[
                event_node("welcome_started"),
                event_node("welcome_step_viewed", {"n": 2}),
                event_node("welcome_step_viewed", {"n": 3}),
                event_node("welcome_completed"),
            ],
            window_interval=5,
            window_unit="minute",
        ),
    },
    {
        "name": "5. Add-word success rate (mini-app)",
        "description": "add_word_attempted → word_added{source:miniapp}.",
        "query": funnel_query(
            series=[
                event_node("add_word_attempted"),
                event_node("word_added", {"source": "miniapp"}),
            ],
            window_interval=60,
            window_unit="second",
        ),
    },
    {
        "name": "6. Mode adoption (Cards / Quiz / Spelling)",
        "description": "Скільки разів кожен режим вибирали. Breakdown by mode.",
        "query": trend_query(
            series=[event_node("review_mode_selected")],
            breakdown="mode",
        ),
    },
    {
        "name": "7. Mode quality (review_submitted by mode, easy answers)",
        "description": "Частка result=knew по режимах — який режим дає кращий learning outcome.",
        "query": trend_query(
            series=[event_node("review_submitted", {"result": "knew"})],
            breakdown="mode",
        ),
    },
    {
        "name": "8. Streak milestones (3/7/14/30/60/100 days)",
        "description": "Скільки людей переступає кожен поріг serії. Health-метрика всього проєкту.",
        "query": trend_query(
            series=[event_node("streak_milestone")],
            breakdown="days",
            date_from="-90d",
        ),
    },
]


# ── HTTP helpers ────────────────────────────────────────────────────────
def get_dashboard_id(name: str) -> int | None:
    r = requests.get(f"{BASE}/dashboards/", headers=HEADERS, params={"limit": 200}, timeout=15)
    r.raise_for_status()
    for d in r.json().get("results", []):
        if d.get("name") == name:
            return d["id"]
    return None


def create_dashboard(name: str) -> int:
    r = requests.post(
        f"{BASE}/dashboards/",
        headers=HEADERS,
        json={"name": name, "description": "Auto-generated by setup_posthog_dashboard.py"},
        timeout=15,
    )
    r.raise_for_status()
    return r.json()["id"]


def get_existing_insight_names(dashboard_id: int) -> set[str]:
    """Перевага — детальний dashboard endpoint (повертає tiles з вкладеними
    insights). Filter API інколи 500-ить на щойно створених дашбордах."""
    try:
        r = requests.get(f"{BASE}/dashboards/{dashboard_id}/", headers=HEADERS, timeout=15)
        if r.status_code < 400:
            tiles = r.json().get("tiles", []) or []
            names: set[str] = set()
            for tile in tiles:
                ins = tile.get("insight") or {}
                if ins.get("name"):
                    names.add(ins["name"])
            return names
    except Exception as e:
        print(f"  ! dashboard detail failed: {e}")
    return set()


def create_insight(spec: dict, dashboard_id: int) -> dict:
    payload = {
        "name": spec["name"],
        "description": spec.get("description", ""),
        "query": spec["query"],
        "dashboards": [dashboard_id],
    }
    r = requests.post(f"{BASE}/insights/", headers=HEADERS, json=payload, timeout=15)
    if r.status_code >= 400:
        print(f"  ✗ {spec['name']}: HTTP {r.status_code}\n{r.text[:600]}", file=sys.stderr)
        r.raise_for_status()
    return r.json()


# ── main ────────────────────────────────────────────────────────────────
def main() -> int:
    print(f"PostHog: {HOST}  project={PROJECT_ID}")
    dashboard_id = get_dashboard_id(DASHBOARD_NAME)
    if dashboard_id:
        print(f"Dashboard exists: id={dashboard_id}")
    else:
        dashboard_id = create_dashboard(DASHBOARD_NAME)
        print(f"Dashboard created: id={dashboard_id}")

    existing = get_existing_insight_names(dashboard_id)
    if existing:
        print(f"Existing insights on dashboard: {len(existing)}")

    created = 0
    skipped = 0
    for spec in INSIGHTS:
        if spec["name"] in existing:
            print(f"  ↷ skip: {spec['name']}")
            skipped += 1
            continue
        out = create_insight(spec, dashboard_id)
        print(f"  ✓ created: {spec['name']}  id={out.get('id')}")
        created += 1

    print(
        f"\nDone. created={created} skipped={skipped}\n"
        f"Open: {HOST}/project/{PROJECT_ID}/dashboard/{dashboard_id}"
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except requests.HTTPError as e:
        print(f"HTTP error: {e}\n{e.response.text if e.response is not None else ''}", file=sys.stderr)
        sys.exit(3)
    except KeyboardInterrupt:
        sys.exit(130)
