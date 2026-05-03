"""
XP-нагороди: тіри і milestones.

XP нараховується за кожне повторення:
- knew (знав)        → 10 XP
- struggled (згадав) → 6 XP
- forgot (забув)     → 2 XP (нагорода за саму спробу)

Тіри прив'язані до накопиченого total_xp.
"""

XP_PER_RESULT = {
    "knew": 10,
    "struggled": 6,
    "forgot": 2,
}

# (xp_threshold, tier_key, reward_key)
# reward_key=None → ще тільки статус, без бонусу
TIERS: list[tuple[int, str, str | None]] = [
    (0,     "rewards.beginner",     None),
    (500,   "rewards.apprentice",   None),
    (2000,  "rewards.word_master",  "rewards.discount_25"),
    (5000,  "rewards.polyglot",     "rewards.discount_50"),
    (10000, "rewards.sage",         "rewards.free_month"),
]


def current_tier(xp: int) -> tuple[int, str, str | None]:
    """Найвищий tier, який юзер уже досяг."""
    achieved = [t for t in TIERS if xp >= t[0]]
    return achieved[-1] if achieved else TIERS[0]


def next_tier(xp: int) -> tuple[int, str, str | None] | None:
    """Наступний tier, до якого ще треба добити."""
    for t in TIERS:
        if xp < t[0]:
            return t
    return None


def xp_for_result(result: str) -> int:
    return XP_PER_RESULT.get(result, 5)
