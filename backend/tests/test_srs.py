"""Тести SM-2 SRS алгоритму."""
from core.srs import calculate_next_review, format_interval


class TestCalculateNextReview:
    def test_first_knew_gives_3_days(self):
        interval, _, _, status = calculate_next_review("knew", 1.0, 2.5, review_count=0)
        assert interval == 3.0
        assert status == "learning"

    def test_second_knew_gives_7_days(self):
        interval, _, _, _ = calculate_next_review("knew", 3.0, 2.6, review_count=1)
        assert interval == 7.0

    def test_third_knew_grows_with_ease(self):
        interval, _, _, _ = calculate_next_review("knew", 7.0, 2.5, review_count=2)
        assert interval == 17.5  # 7 × 2.5

    def test_struggled_first_time_gives_1_5(self):
        interval, _, _, _ = calculate_next_review("struggled", 1.0, 2.5, review_count=0)
        assert interval == 1.5

    def test_struggled_grows_slower(self):
        interval, _, _, _ = calculate_next_review("struggled", 5.0, 2.5, review_count=2)
        assert interval == 6.5  # 5 × 1.3

    def test_forgot_resets_to_1_day(self):
        interval, _, _, _ = calculate_next_review("forgot", 30.0, 2.5, review_count=5)
        assert interval == 1.0

    def test_forgot_decreases_ease(self):
        _, ease, _, _ = calculate_next_review("forgot", 30.0, 2.5, review_count=5)
        assert ease == 2.3  # 2.5 − 0.2

    def test_knew_increases_ease(self):
        _, ease, _, _ = calculate_next_review("knew", 7.0, 2.5, review_count=2)
        assert ease == 2.6  # 2.5 + 0.1

    def test_max_interval_capped_at_365(self):
        interval, _, _, _ = calculate_next_review("knew", 200.0, 3.0, review_count=10)
        assert interval == 365.0

    def test_min_ease_clamped(self):
        _, ease, _, _ = calculate_next_review("forgot", 1.0, 1.4, review_count=0)
        assert ease == 1.3

    def test_max_ease_clamped(self):
        _, ease, _, _ = calculate_next_review("knew", 7.0, 3.5, review_count=2)
        assert ease == 3.5  # not 3.6

    def test_status_becomes_mastered_at_21_days(self):
        _, _, _, status = calculate_next_review("knew", 21.0, 2.5, review_count=5)
        assert status == "mastered"

    def test_status_remains_learning_below_21(self):
        _, _, _, status = calculate_next_review("knew", 7.0, 2.5, review_count=2)
        assert status == "learning"


class TestFormatInterval:
    def test_one_day(self):
        # Українські множинні форми мають 'день'/'дні'/'днів'
        assert "день" in format_interval(1)

    def test_three_days(self):
        assert "дні" in format_interval(3) or "днів" in format_interval(3)

    def test_seven_days_is_one_week(self):
        assert "тижд" in format_interval(7)

    def test_30_days_is_one_month(self):
        assert "міс" in format_interval(30)

    def test_365_days_is_one_year(self):
        assert "рік" in format_interval(365)
