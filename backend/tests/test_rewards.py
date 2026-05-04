"""Тести для XP-системи та tier-логіки."""
from core.rewards import (
    current_tier,
    detect_tier_crossed,
    next_tier,
    xp_for_result,
    TIERS,
)


class TestCurrentTier:
    def test_zero_xp_is_beginner(self):
        threshold, key, _ = current_tier(0)
        assert threshold == 0
        assert key == "rewards.beginner"

    def test_499_xp_still_beginner(self):
        _, key, _ = current_tier(499)
        assert key == "rewards.beginner"

    def test_500_xp_is_apprentice(self):
        _, key, _ = current_tier(500)
        assert key == "rewards.apprentice"

    def test_1000_xp_is_word_master(self):
        threshold, key, reward = current_tier(1000)
        assert threshold == 1000
        assert key == "rewards.word_master"
        assert reward == "rewards.discount_25"

    def test_huge_xp_is_max_tier(self):
        threshold, key, reward = current_tier(999_999)
        assert threshold == 5_000
        assert key == "rewards.sage"
        assert reward == "rewards.discount_100"


class TestNextTier:
    def test_below_500_next_is_apprentice(self):
        nxt = next_tier(100)
        assert nxt is not None
        assert nxt[0] == 500

    def test_at_500_next_is_word_master(self):
        nxt = next_tier(500)
        assert nxt is not None
        assert nxt[0] == 1000

    def test_above_max_returns_none(self):
        assert next_tier(50_000) is None


class TestDetectTierCrossed:
    def test_no_cross_returns_none(self):
        assert detect_tier_crossed(100, 200) is None

    def test_cross_500_threshold(self):
        crossed = detect_tier_crossed(490, 510)
        assert crossed is not None
        assert crossed[0] == 500

    def test_exact_threshold_hit(self):
        crossed = detect_tier_crossed(499, 500)
        assert crossed is not None
        assert crossed[0] == 500

    def test_one_below_threshold_no_cross(self):
        assert detect_tier_crossed(498, 499) is None

    def test_jump_through_multiple_tiers_returns_first(self):
        crossed = detect_tier_crossed(0, 5000)
        assert crossed is not None
        # Стартуємо з порога Apprentice (першого ненульового)
        assert crossed[0] == 500


class TestXpForResult:
    def test_knew(self):
        assert xp_for_result("knew") == 10

    def test_struggled(self):
        assert xp_for_result("struggled") == 6

    def test_forgot(self):
        assert xp_for_result("forgot") == 2

    def test_unknown_returns_default(self):
        assert xp_for_result("invalid") == 5


class TestTiersInvariants:
    def test_thresholds_are_ascending(self):
        thresholds = [t[0] for t in TIERS]
        assert thresholds == sorted(thresholds)

    def test_first_tier_is_zero(self):
        assert TIERS[0][0] == 0

    def test_each_tier_has_translation_key(self):
        for threshold, key, reward in TIERS:
            assert key.startswith("rewards.")
            if reward is not None:
                assert reward.startswith("rewards.")
