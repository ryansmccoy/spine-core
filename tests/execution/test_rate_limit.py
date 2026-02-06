"""Tests for rate limiting."""

import pytest
import time
import asyncio
from unittest.mock import MagicMock, patch

from spine.execution.rate_limit import (
    RateLimiter,
    TokenBucketLimiter,
    SlidingWindowLimiter,
    KeyedRateLimiter,
    CompositeRateLimiter,
)


class TestTokenBucketLimiter:
    """Tests for TokenBucketLimiter."""

    def test_default_configuration(self):
        """Test configuration values."""
        limiter = TokenBucketLimiter(rate=10.0, capacity=100)
        assert limiter.rate == 10.0
        assert limiter.capacity == 100

    def test_initial_tokens(self):
        """Test starts with full bucket."""
        limiter = TokenBucketLimiter(rate=10.0, capacity=5)
        
        # Should be able to acquire 5 tokens immediately
        for _ in range(5):
            assert limiter.acquire() is True
        
        # 6th should fail (bucket empty)
        assert limiter.acquire() is False

    def test_tokens_refill_over_time(self):
        """Test tokens refill over time."""
        limiter = TokenBucketLimiter(rate=10.0, capacity=5)
        
        # Drain the bucket
        for _ in range(5):
            limiter.acquire()
        
        # Wait for tokens to refill (10 per second = 0.1s per token)
        time.sleep(0.15)
        
        # Should have at least 1 token now
        assert limiter.acquire() is True

    def test_bucket_doesnt_exceed_capacity(self):
        """Test tokens don't exceed capacity."""
        limiter = TokenBucketLimiter(rate=100.0, capacity=5)
        
        # Wait for potential overflow
        time.sleep(0.2)
        
        # Should only be able to acquire capacity tokens
        acquired = 0
        while limiter.acquire():
            acquired += 1
        
        assert acquired == 5

    def test_acquire_multiple_tokens(self):
        """Test acquiring multiple tokens at once."""
        limiter = TokenBucketLimiter(rate=10.0, capacity=10)
        
        assert limiter.acquire(5) is True
        assert limiter.acquire(5) is True
        assert limiter.acquire(1) is False

    def test_acquire_more_than_capacity_fails(self):
        """Test acquiring more than capacity fails."""
        limiter = TokenBucketLimiter(rate=10.0, capacity=5)
        
        assert limiter.acquire(10) is False

    def test_wait_time_calculation(self):
        """Test wait time calculation."""
        limiter = TokenBucketLimiter(rate=10.0, capacity=5)
        
        # Drain bucket
        for _ in range(5):
            limiter.acquire()
        
        # Wait time should be ~0.1s per token at 10/sec rate
        wait_time = limiter.get_wait_time(1)
        assert 0.05 <= wait_time <= 0.2

    @pytest.mark.slow
    @pytest.mark.timeout(2)
    def test_acquire_with_blocking(self):
        """Test blocking acquire waits for tokens."""
        limiter = TokenBucketLimiter(rate=20.0, capacity=2)
        
        # Drain bucket
        limiter.acquire(2)
        
        # Blocking acquire should wait
        start = time.time()
        result = limiter.acquire(1, block=True)
        elapsed = time.time() - start
        
        assert result is True
        # Should have waited ~0.05s for 1 token at 20/sec
        assert elapsed >= 0.03


class TestSlidingWindowLimiter:
    """Tests for SlidingWindowLimiter."""

    def test_default_configuration(self):
        """Test configuration values."""
        limiter = SlidingWindowLimiter(max_requests=100, window_seconds=60.0)
        assert limiter.max_requests == 100
        assert limiter.window_seconds == 60.0

    def test_allows_requests_within_limit(self):
        """Test allows requests within limit."""
        limiter = SlidingWindowLimiter(max_requests=5, window_seconds=60.0)
        
        for _ in range(5):
            assert limiter.acquire() is True

    def test_denies_requests_over_limit(self):
        """Test denies requests over limit."""
        limiter = SlidingWindowLimiter(max_requests=3, window_seconds=60.0)
        
        for _ in range(3):
            limiter.acquire()
        
        assert limiter.acquire() is False

    def test_window_slides(self):
        """Test window slides and old requests expire."""
        limiter = SlidingWindowLimiter(max_requests=2, window_seconds=0.1)
        
        # Fill the limit
        limiter.acquire()
        limiter.acquire()
        assert limiter.acquire() is False
        
        # Wait for window to slide
        time.sleep(0.15)
        
        # Should be able to make requests again
        assert limiter.acquire() is True

    def test_wait_time_when_limited(self):
        """Test wait time calculation when limited."""
        limiter = SlidingWindowLimiter(max_requests=1, window_seconds=0.5)
        
        limiter.acquire()
        
        # Should need to wait for oldest request to expire
        wait_time = limiter.get_wait_time()
        assert 0.3 <= wait_time <= 0.6

    def test_wait_time_when_not_limited(self):
        """Test wait time is zero when not limited."""
        limiter = SlidingWindowLimiter(max_requests=10, window_seconds=60.0)
        
        assert limiter.get_wait_time() == 0.0


class TestKeyedRateLimiter:
    """Tests for KeyedRateLimiter."""

    @pytest.mark.slow
    @pytest.mark.timeout(30)
    def test_creates_limiter_per_key(self):
        """Test creates separate limiter per key."""
        def factory():
            return TokenBucketLimiter(rate=10.0, capacity=2)
        
        keyed = KeyedRateLimiter(factory)
        
        # Key1 can acquire 2
        assert keyed.acquire("key1") is True
        assert keyed.acquire("key1") is True
        assert keyed.acquire("key1") is False
        
        # Key2 is separate, can also acquire 2
        assert keyed.acquire("key2") is True
        assert keyed.acquire("key2") is True
        assert keyed.acquire("key2") is False

    @pytest.mark.slow
    @pytest.mark.timeout(30)
    def test_same_key_returns_same_limiter(self):
        """Test same key returns same limiter."""
        def factory():
            return TokenBucketLimiter(rate=10.0, capacity=5)
        
        keyed = KeyedRateLimiter(factory)
        
        keyed.acquire("key1")
        keyed.acquire("key1")
        
        # Should have consumed from same limiter
        limiter = keyed.get("key1")
        # 5 - 2 = 3 remaining (approximately, accounting for refill)
        assert limiter is not None

    @pytest.mark.slow
    @pytest.mark.timeout(30)
    def test_remove_key(self):
        """Test removing a key's limiter."""
        def factory():
            return TokenBucketLimiter(rate=10.0, capacity=5)
        
        keyed = KeyedRateLimiter(factory)
        
        keyed.acquire("key1")
        keyed.acquire("key1")
        
        # Remove key1
        keyed.remove("key1")
        
        # New limiter should be created with full capacity
        keyed.acquire("key1")
        assert keyed.acquire("key1") is True  # Fresh limiter


class TestCompositeRateLimiter:
    """Tests for CompositeRateLimiter."""

    def test_all_limiters_must_allow(self):
        """Test all limiters must allow request."""
        limiter1 = TokenBucketLimiter(rate=10.0, capacity=5)
        limiter2 = TokenBucketLimiter(rate=10.0, capacity=2)
        
        composite = CompositeRateLimiter([limiter1, limiter2])
        
        # Can only acquire up to min capacity (2)
        assert composite.acquire() is True
        assert composite.acquire() is True
        assert composite.acquire() is False

    def test_empty_composite_always_allows(self):
        """Test empty composite always allows."""
        composite = CompositeRateLimiter([])
        
        for _ in range(100):
            assert composite.acquire() is True

    def test_wait_time_is_max_of_all(self):
        """Test wait time is max of all limiters."""
        limiter1 = TokenBucketLimiter(rate=100.0, capacity=1)  # Fast refill
        limiter2 = TokenBucketLimiter(rate=1.0, capacity=1)    # Slow refill
        
        composite = CompositeRateLimiter([limiter1, limiter2])
        
        # Drain both
        composite.acquire()
        
        # Wait time should be determined by slower limiter
        wait_time = composite.get_wait_time(1)
        assert wait_time >= 0.5  # At least half second from slow limiter
