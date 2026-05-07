#!/usr/bin/env python3
"""Створює дашборд + 8 готових інсайтів у PostHog через REST API.

Ідемпотентний — якщо інсайт із тим самим ім'ям уже є, пропускає його.
Якщо дашборду нема — створює новий і пінить туди всі інсайти.

Використання:
    export POSTHOG_PERSONAL_API_KEY='phx_...'   # створи у PostHog → Settings → Personal API Keys
    export POSTHOG_PROJECT_ID='12345'           # числовий ID з URL: app.posthog.com/project/12345
    export POSTHOG_HOST='https://eu.posthog.com'  # опційно, default EU
    python3 scripts/setup_posthog_dashboard.py

PERSONAL_API_KEY scope: треба `insight:write`, `dashboard:write` (можна просто
поставити "Read & Write" на проєкт — PostHog UI спрощує).
"""
from __future__ import annotations

import json
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


def _events(*specs: tuple[str, dict | None]) -> list[dict]:
    """Будує список events для filter у форматі PostHog (legacy filters API).

    Кожен spec — (event_name, properties_dict | None). Props автоматично
    обгортається у [{key, value, operator: "exact", type: "event"}].
    """
    out: list[dict] = []
    for order, (name, props) in enumerate(specs):
        item: dict[str, Any] = {"id": name, "order": order, "type": "events"}
        if props:
            item["properties"] = [
                {"key": k, "value": v, "operator": "exact", "type": "event"}
                for k, v in props.items()
            ]
        out.append(item)
    return out


# ── Інсайти ─────────────────────────────────────────────────────────────
INSIGHTS: list[dict] = [
    {
        "name": "1. Activation funnel (new user → first review)",
        "description": "З /start у боті до першого review_submitted. Drop-off показує де нові юзери губляться.",
        "filters": {
            "insight": "FUNNELS",
            "events": _events(
                ("user_started", None),
                ("lang_selected", None),
                ("region_selected", None),
                ("word_added", {"source": "bot_setup"}),
                ("review_submitted", None),
            ),
            "funnel_window_interval": 7,
            "funnel_window_interval_unit": "day",
            "date_from": "-30d",
        },
    },
    {
        "name": "2. Pro conversion (precise)",
        "description": "pro_page_viewed → buy_clicked → buy_open_attempt → payment_succeeded. Покаже на якому кроці втрачаєш конверсію.",
        "filters": {
            "insight": "FUNNELS",
            "events": _events(
                ("pro_page_viewed", None),
                ("buy_clicked", None),
                ("buy_open_attempt", None),
                ("payment_succeeded", None),
            ),
            "funnel_window_interval": 30,
            "funnel_window_interval_unit": "minute",
            "date_from": "-30d",
            "breakdown": "period",
            "breakdown_type": "event",
        },
    },
    {
        "name": "3. Paywall → upgrade",
        "description": "Як часто free-tier limit конвертить у Pro. Найважливіший монетизаційний funnel.",
        "filters": {
            "insight": "FUNNELS",
            "events": _events(
                ("paywall_hit", {"reason": "daily_limit"}),
                ("pro_page_viewed", None),
                ("buy_clicked", None),
                ("payment_succeeded", None),
            ),
            "funnel_window_interval": 7,
            "funnel_window_interval_unit": "day",
            "date_from": "-30d",
        },
    },
    {
        "name": "4. Welcome stories engagement",
        "description": "Скільки людей долистує до s3 (там CTA +10 днів Pro). Drop-off на 1→2 — нудний перший слайд.",
        "filters": {
            "insight": "FUNNELS",
            "events": _events(
                ("welcome_started", None),
                ("welcome_step_viewed", {"n": 2}),
                ("welcome_step_viewed", {"n": 3}),
                ("welcome_completed", None),
            ),
            "funnel_window_interval": 5,
            "funnel_window_interval_unit": "minute",
            "date_from": "-30d",
        },
    },
    {
        "name": "5. Add-word success rate (mini-app)",
        "description": "add_word_attempted → word_added{source:miniapp}. Скільки спроб додати слово реально проходять.",
        "filters": {
            "insight": "FUNNELS",
            "events": _events(
                ("add_word_attempted", None),
                ("word_added", {"source": "miniapp"}),
            ),
            "funnel_window_interval": 60,
            "funnel_window_interval_unit": "second",
            "date_from": "-30d",
        },
    },
    {
        "name": "6. Mode adoption (Cards / Quiz / Spelling)",
        "description": "Скільки разів кожен режим вибирали. Breakdown by mode.",
        "filters": {
            "insight": "TRENDS",
            "events": [{"id": "review_mode_selected", "type": "events", "math": "total"}],
            "breakdown": "mode",
            "breakdown_type": "event",
            "interval": "week",
            "date_from": "-30d",
            "display": "ActionsLineGraph",
        },
    },
    {
        "name": "7. Mode quality (review_submitted by mode, easy answers)",
        "description": "Частка result=knew по режимах — який режим дає кращий learning outcome.",
        "filters": {
            "insight": "TRENDS",
            "events": [{
                "id": "review_submitted",
                "type": "events",
                "math": "total",
                "properties": [
                    {"key": "result", "value": "knew", "operator": "exact", "type": "event"},
                ],
            }],
            "breakdown": "mode",
            "breakdown_type": "event",
            "interval": "week",
            "date_from": "-30d",
            "display": "ActionsLineGraph",
        },
    },
    {
        "name": "8. Streak milestones (3/7/14/30/60/100 days)",
        "description": "Скільки людей переступає кожен поріг serії. Health-метрика всього проєкту.",
        "filters": {
            "insight": "TRENDS",
            "events": [{"id": "streak_milestone", "type": "events", "math": "total"}],
            "breakdown": "days",
            "breakdown_type": "event",
            "interval": "week",
            "date_from": "-90d",
            "display": "ActionsLineGraph",
        },
    },
]


# ── HTTP helpers ────────────────────────────────────────────────────────
def get_dashboard_id(name: str) -> int | None:
    """Шукає дашборд по імені, повертає id або None."""
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
    """Повертає назви інсайтів, що вже на дашборді — щоб не дублювати.

    PostHog API інколи 500-ить на GET /insights/?dashboards=... для щойно
    створених дашбордів. Якщо filter падає — fallback через GET dashboard
    detail (там у tiles є вкладені інсайти). Якщо й це падає — повертаємо
    порожній set (краще створити дублі, ніж зломатись)."""
    try:
        r = requests.get(
            f"{BASE}/insights/",
            headers=HEADERS,
            params={"dashboards": dashboard_id, "limit": 200},
            timeout=15,
        )
        if r.status_code < 400:
            return {i.get("name") for i in r.json().get("results", []) if i.get("name")}
        print(f"  ! /insights filter returned {r.status_code}, falling back to dashboard detail")
    except Exception as e:
        print(f"  ! /insights filter failed: {e}, falling back to dashboard detail")

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
        "filters": spec["filters"],
        "dashboards": [dashboard_id],
    }
    r = requests.post(f"{BASE}/insights/", headers=HEADERS, json=payload, timeout=15)
    if r.status_code >= 400:
        print(f"  ✗ {spec['name']}: HTTP {r.status_code}\n{r.text[:400]}", file=sys.stderr)
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
