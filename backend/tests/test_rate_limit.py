"""M8: in-memory rate limiter (pure logic)."""
from core.rate_limit import allow


def test_allows_up_to_limit_then_blocks():
    key = "test:unique:key"
    assert all(allow(key, 5, 60) for _ in range(5))
    assert allow(key, 5, 60) is False  # 6th blocked
    assert allow("other:key", 5, 60) is True  # independent key
