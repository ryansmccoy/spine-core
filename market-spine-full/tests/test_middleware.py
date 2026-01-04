"""Tests for rate limiting middleware."""

import pytest
import time
from unittest.mock import MagicMock, patch

from market_spine.api.middleware.rate_limit import RateLimiter, RateLimitMiddleware


class TestRateLimiter:
    """Tests for RateLimiter class."""

    def test_allows_requests_under_limit(self):
        """Test that requests under the limit are allowed."""
        limiter = RateLimiter(max_tokens=10, refill_rate=1)
        request = MagicMock()
        request.headers = {}
        request.client.host = "127.0.0.1"

        # First 10 requests should be allowed
        for _ in range(10):
            allowed, headers = limiter.allow_request(request)
            assert allowed is True

    def test_blocks_requests_over_limit(self):
        """Test that requests over the limit are blocked."""
        limiter = RateLimiter(max_tokens=5, refill_rate=0.1)
        request = MagicMock()
        request.headers = {}
        request.client.host = "127.0.0.1"

        # Use up all tokens
        for _ in range(5):
            limiter.allow_request(request)

        # Next request should be blocked
        allowed, headers = limiter.allow_request(request)
        assert allowed is False
        assert "Retry-After" in headers

    def test_tokens_refill_over_time(self):
        """Test that tokens refill based on elapsed time."""
        limiter = RateLimiter(max_tokens=5, refill_rate=100)  # 100 tokens/sec
        request = MagicMock()
        request.headers = {}
        request.client.host = "127.0.0.1"

        # Use all tokens
        for _ in range(5):
            limiter.allow_request(request)

        # Should be blocked
        allowed, _ = limiter.allow_request(request)
        assert allowed is False

        # Wait a bit for refill
        time.sleep(0.1)

        # Should be allowed again
        allowed, _ = limiter.allow_request(request)
        assert allowed is True

    def test_uses_forwarded_for_header(self):
        """Test that X-Forwarded-For is used for client identification."""
        limiter = RateLimiter(max_tokens=2, refill_rate=0)

        # Request from proxy
        request1 = MagicMock()
        request1.headers = {"x-forwarded-for": "1.2.3.4, 5.6.7.8"}
        request1.client.host = "10.0.0.1"

        # Different actual client
        request2 = MagicMock()
        request2.headers = {"x-forwarded-for": "9.9.9.9"}
        request2.client.host = "10.0.0.1"

        # Each should have separate buckets
        for _ in range(2):
            allowed, _ = limiter.allow_request(request1)
            assert allowed is True

        for _ in range(2):
            allowed, _ = limiter.allow_request(request2)
            assert allowed is True

    def test_returns_rate_limit_headers(self):
        """Test that rate limit headers are returned."""
        limiter = RateLimiter(max_tokens=10, refill_rate=1)
        request = MagicMock()
        request.headers = {}
        request.client.host = "127.0.0.1"

        allowed, headers = limiter.allow_request(request)

        assert "X-RateLimit-Limit" in headers
        assert headers["X-RateLimit-Limit"] == "10"
        assert "X-RateLimit-Remaining" in headers
        assert "X-RateLimit-Reset" in headers


class TestRateLimitMiddleware:
    """Tests for RateLimitMiddleware."""

    def test_excludes_health_paths(self):
        """Test that health paths are excluded from rate limiting."""
        middleware = RateLimitMiddleware(
            app=MagicMock(),
            max_tokens=1,
            refill_rate=0,
            exclude_paths=["/health", "/metrics"],
        )

        # Create mock request for health endpoint
        request = MagicMock()
        request.url.path = "/health/live"
        request.headers = {}
        request.client.host = "127.0.0.1"

        # Check that path is excluded
        excluded = any(request.url.path.startswith(p) for p in middleware.exclude_paths)
        assert excluded is True

    def test_includes_non_excluded_paths(self):
        """Test that non-excluded paths are rate limited."""
        middleware = RateLimitMiddleware(
            app=MagicMock(),
            max_tokens=1,
            refill_rate=0,
            exclude_paths=["/health"],
        )

        request = MagicMock()
        request.url.path = "/executions"

        excluded = any(request.url.path.startswith(p) for p in middleware.exclude_paths)
        assert excluded is False
