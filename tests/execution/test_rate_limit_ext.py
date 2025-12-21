"""Tests for ``spine.execution.rate_limit`` — token bucket, sliding window, keyed, composite."""

from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from spine.execution.rate_limit import (
    CompositeRateLimiter,
    KeyedRateLimiter,
    RateLimitExceeded,
    SlidingWindowLimiter,
    TokenBucketLimiter,
    get_all_rate_limiters,
    get_rate_limiter,
)


class TestRateLimitExceeded:
    def test_basic(self):
        exc = RateLimitExceeded("too fast")
        assert str(exc) == "too fast"
        assert exc.retry_after is None

    def test_with_retry_after(self):
        exc = RateLimitExceeded("slow down", retry_after=1.5)
        assert exc.retry_after == 1.5


class TestTokenBucketLimiter:
    def test_acquire_succeeds_with_full_bucket(self):
        limiter = TokenBucketLimiter(rate=10.0, capacity=10.0)
        assert limiter.acquire() is True

    def test_acquire_multiple(self):
        limiter = TokenBucketLimiter(rate=10.0, capacity=5.0)
        for _ in range(5):
            assert limiter.acquire() is True
        assert limiter.acquire() is False  # bucket empty

    def test_acquire_multiple_tokens(self):
        limiter = TokenBucketLimiter(rate=10.0, capacity=10.0)
        assert limiter.acquire(tokens=5) is True
        assert limiter.acquire(tokens=6) is False  # only 5 remain

    def test_get_wait_time_zero_when_available(self):
        limiter = TokenBucketLimiter(rate=10.0, capacity=10.0)
        assert limiter.get_wait_time() == 0.0

    def test_get_wait_time_positive_when_empty(self):
        limiter = TokenBucketLimiter(rate=10.0, capacity=1.0)
        limiter.acquire()  # empty the bucket
        wt = limiter.get_wait_time()
        assert wt > 0.0

    def test_available_tokens(self):
        limiter = TokenBucketLimiter(rate=10.0, capacity=10.0)
        assert limiter.available_tokens == pytest.approx(10.0, abs=0.5)
        limiter.acquire(tokens=3)
        assert limiter.available_tokens == pytest.approx(7.0, abs=0.5)

    def test_refill_over_time(self):
        limiter = TokenBucketLimiter(rate=100.0, capacity=10.0)
        limiter.acquire(tokens=10)
        # Simulate 50ms elapsed by rewinding _last_update
        limiter._last_update -= 0.05
        assert limiter.available_tokens >= 3.0

    def test_refill_after_drain(self):
        limiter = TokenBucketLimiter(rate=1000.0, capacity=1.0)
        limiter.acquire()
        assert limiter.available_tokens < 1.0
        # Simulate 10ms elapsed by rewinding _last_update
        limiter._last_update -= 0.01
        assert limiter.available_tokens >= 0.5


class TestSlidingWindowLimiter:
    def test_acquire_within_limit(self):
        limiter = SlidingWindowLimiter(max_requests=5, window_seconds=1.0)
        for _ in range(5):
            assert limiter.acquire() is True
        assert limiter.acquire() is False

    def test_acquire_multiple_tokens(self):
        limiter = SlidingWindowLimiter(max_requests=10, window_seconds=1.0)
        assert limiter.acquire(tokens=5) is True
        assert limiter.acquire(tokens=6) is False

    def test_get_wait_time(self):
        limiter = SlidingWindowLimiter(max_requests=1, window_seconds=0.5)
        limiter.acquire()
        wt = limiter.get_wait_time()
        assert wt > 0.0

    def test_get_wait_time_zero(self):
        limiter = SlidingWindowLimiter(max_requests=5, window_seconds=1.0)
        assert limiter.get_wait_time() == 0.0

    def test_current_count(self):
        limiter = SlidingWindowLimiter(max_requests=10, window_seconds=1.0)
        assert limiter.current_count == 0
        limiter.acquire(tokens=3)
        assert limiter.current_count == 3

    def test_window_expiry(self):
        limiter = SlidingWindowLimiter(max_requests=2, window_seconds=0.05)
        limiter.acquire()
        limiter.acquire()
        assert limiter.acquire() is False
        time.sleep(0.06)
        assert limiter.acquire() is True

    def test_get_wait_time_full_window(self):
        limiter = SlidingWindowLimiter(max_requests=0, window_seconds=1.0)
        wt = limiter.get_wait_time(tokens=1)
        assert wt > 0


class TestKeyedRateLimiter:
    def test_per_key_isolation(self):
        limiter = KeyedRateLimiter(rate=10.0, capacity=2.0)
        assert limiter.acquire("a") is True
        assert limiter.acquire("a") is True
        assert limiter.acquire("a") is False
        # different key still available
        assert limiter.acquire("b") is True

    def test_factory(self):
        factory = lambda: SlidingWindowLimiter(max_requests=1, window_seconds=1.0)
        limiter = KeyedRateLimiter(factory=factory)
        assert limiter.acquire("x") is True
        assert limiter.acquire("x") is False

    def test_get(self):
        limiter = KeyedRateLimiter(rate=10.0, capacity=10.0)
        assert limiter.get("nonexistent") is None
        limiter.acquire("a")
        assert limiter.get("a") is not None

    def test_remove(self):
        limiter = KeyedRateLimiter(rate=10.0, capacity=10.0)
        limiter.acquire("a")
        limiter.remove("a")
        assert limiter.get("a") is None
        limiter.remove("nonexistent")  # no error

    def test_get_wait_time(self):
        limiter = KeyedRateLimiter(rate=10.0, capacity=1.0)
        limiter.acquire("a")
        wt = limiter.get_wait_time("a")
        assert wt > 0

    def test_cleanup_runs(self):
        limiter = KeyedRateLimiter(rate=10.0, capacity=10.0, cleanup_interval=2)
        limiter.acquire("a")
        # refill bucket to full so it looks unused
        time.sleep(0.01)
        limiter.acquire("b")  # acquire count = 2, triggers cleanup
        # 'a' may get cleaned up if its bucket is full


class TestCompositeRateLimiter:
    def test_all_pass(self):
        l1 = TokenBucketLimiter(rate=10.0, capacity=10.0)
        l2 = TokenBucketLimiter(rate=10.0, capacity=10.0)
        comp = CompositeRateLimiter([l1, l2])
        assert comp.acquire() is True

    def test_one_fails(self):
        l1 = TokenBucketLimiter(rate=10.0, capacity=10.0)
        l2 = TokenBucketLimiter(rate=10.0, capacity=1.0)
        l2.acquire()  # empty l2
        comp = CompositeRateLimiter([l1, l2])
        assert comp.acquire() is False

    def test_get_wait_time(self):
        l1 = TokenBucketLimiter(rate=10.0, capacity=10.0)
        l2 = TokenBucketLimiter(rate=10.0, capacity=10.0)
        comp = CompositeRateLimiter([l1, l2])
        assert comp.get_wait_time() == 0.0


class TestGlobalRegistry:
    def test_get_rate_limiter(self):
        limiter = get_rate_limiter("test-global-1", rate=5.0, capacity=5.0)
        assert isinstance(limiter, TokenBucketLimiter)
        # Same name returns same instance
        same = get_rate_limiter("test-global-1")
        assert same is limiter

    def test_get_all(self):
        get_rate_limiter("test-global-2")
        all_limiters = get_all_rate_limiters()
        assert "test-global-2" in all_limiters
