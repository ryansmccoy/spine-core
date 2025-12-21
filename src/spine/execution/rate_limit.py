"""Rate Limiting — token-bucket and sliding-window throughput control.

Manifesto:
External APIs (SEC EDGAR, LLM endpoints) enforce rate limits.
Exceeding them causes bans or 429 errors.  In-process rate limiters
let spine throttle outgoing calls *before* hitting the limit.

ARCHITECTURE
────────────
::

    RateLimiter (ABC)
      ├── TokenBucketLimiter     ─ steady rate + burst capacity
      ├── SlidingWindowLimiter   ─ exact count in rolling window
      ├── KeyedRateLimiter       ─ per-key limits (e.g. per-CIK)
      └── CompositeRateLimiter   ─ combine multiple strategies

    All limiters are thread-safe (internal Lock).

BEST PRACTICES
──────────────
- Use ``TokenBucketLimiter`` for steady throughput with burst.
- Use ``SlidingWindowLimiter`` for strict per-window caps.
- Use ``KeyedRateLimiter`` when limits vary by entity (per-CIK,
  per-API-key).
- Combine with ``CircuitBreaker`` for full resilience.

Related modules:
    circuit_breaker.py — fail-fast on sustained failures
    retry.py           — backoff on transient failures
    timeout.py         — enforce deadlines

Example::

    limiter = TokenBucketLimiter(rate=10, capacity=20)
    if limiter.acquire():
        make_api_call()
    else:
        raise RateLimitExceeded("Too many requests")

Tags:
    spine-core, execution, rate-limit, throttle, token-bucket

Doc-Types:
    api-reference
"""

import threading
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime


def utcnow() -> datetime:
    """Return timezone-aware UTC datetime."""
    return datetime.now(UTC)


class RateLimitExceeded(Exception):
    """Raised when rate limit is exceeded."""

    def __init__(
        self,
        message: str = "Rate limit exceeded",
        retry_after: float | None = None,
    ):
        super().__init__(message)
        self.retry_after = retry_after


class RateLimiter(ABC):
    """Abstract base for rate limiters."""

    @abstractmethod
    def acquire(self, tokens: int = 1, block: bool = False) -> bool:
        """Attempt to acquire tokens.

        Args:
            tokens: Number of tokens to acquire
            block: If True, block until tokens available

        Returns:
            True if tokens acquired, False otherwise
        """
        ...

    @abstractmethod
    def get_wait_time(self, tokens: int = 1) -> float:
        """Get seconds to wait before tokens available.

        Args:
            tokens: Number of tokens needed

        Returns:
            Seconds to wait (0 if available now)
        """
        ...


@dataclass
class TokenBucketLimiter(RateLimiter):
    """Token bucket rate limiter.

    Tokens are added at a fixed rate up to capacity.
    Allows bursts up to capacity, then limits to rate.

    Attributes:
        rate: Tokens added per second
        capacity: Maximum tokens (burst size)
    """

    rate: float  # tokens per second
    capacity: float  # max tokens

    _tokens: float = field(default=0.0, init=False)
    _last_update: float = field(default_factory=time.monotonic, init=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False)

    def __post_init__(self):
        """Initialize with full bucket."""
        self._tokens = self.capacity

    def _refill(self) -> None:
        """Add tokens based on elapsed time."""
        now = time.monotonic()
        elapsed = now - self._last_update
        self._tokens = min(
            self.capacity,
            self._tokens + (elapsed * self.rate),
        )
        self._last_update = now

    def acquire(self, tokens: int = 1, block: bool = False) -> bool:
        """Attempt to acquire tokens."""
        with self._lock:
            self._refill()

            if self._tokens >= tokens:
                self._tokens -= tokens
                return True

            if not block:
                return False

            # Calculate wait time and block
            wait_time = self.get_wait_time(tokens)

        # Release lock while sleeping
        time.sleep(wait_time)

        # Try again
        return self.acquire(tokens, block=False)

    def get_wait_time(self, tokens: int = 1) -> float:
        """Get seconds until tokens available."""
        with self._lock:
            self._refill()

            if self._tokens >= tokens:
                return 0.0

            needed = tokens - self._tokens
            return needed / self.rate

    @property
    def available_tokens(self) -> float:
        """Get current available tokens."""
        with self._lock:
            self._refill()
            return self._tokens


@dataclass
class SlidingWindowLimiter(RateLimiter):
    """Sliding window rate limiter.

    Counts requests in a sliding time window.
    More accurate than fixed windows, prevents boundary bursts.

    Attributes:
        max_requests: Maximum requests per window
        window_seconds: Window size in seconds
    """

    max_requests: int
    window_seconds: float

    _timestamps: list[float] = field(default_factory=list, init=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False)

    def _cleanup(self, now: float) -> None:
        """Remove timestamps outside the window."""
        cutoff = now - self.window_seconds
        self._timestamps = [ts for ts in self._timestamps if ts > cutoff]

    def acquire(self, tokens: int = 1, block: bool = False) -> bool:
        """Attempt to acquire tokens (tokens = request count)."""
        with self._lock:
            now = time.monotonic()
            self._cleanup(now)

            if len(self._timestamps) + tokens <= self.max_requests:
                for _ in range(tokens):
                    self._timestamps.append(now)
                return True

            if not block:
                return False

            wait_time = self.get_wait_time(tokens)

        # Release lock while sleeping
        time.sleep(wait_time)
        return self.acquire(tokens, block=False)

    def get_wait_time(self, tokens: int = 1) -> float:
        """Get seconds until window has room."""
        with self._lock:
            now = time.monotonic()
            self._cleanup(now)

            available = self.max_requests - len(self._timestamps)
            if available >= tokens:
                return 0.0

            # Need to wait for oldest timestamps to expire
            need_to_expire = tokens - available
            if need_to_expire <= len(self._timestamps):
                oldest = self._timestamps[need_to_expire - 1]
                return max(0, (oldest + self.window_seconds) - now)

            return self.window_seconds

    @property
    def current_count(self) -> int:
        """Get current request count in window."""
        with self._lock:
            self._cleanup(time.monotonic())
            return len(self._timestamps)


@dataclass
class KeyedRateLimiter:
    """Rate limiter with per-key limits.

    Useful for per-user, per-IP, or per-resource rate limiting.

    Can be created with explicit rate/capacity or a factory function.

    Example:
        >>> limiter = KeyedRateLimiter(rate=10, capacity=20)
        >>> limiter.acquire("user-123")  # Per-user limit
        >>>
        >>> # Or with factory
        >>> def factory():
        ...     return TokenBucketLimiter(rate=5, capacity=10)
        >>> limiter = KeyedRateLimiter(factory=factory)
    """

    rate: float = 10.0
    capacity: float = 20.0
    factory: Callable[[], RateLimiter] | None = None
    cleanup_interval: int = 1000  # Cleanup every N acquires

    _limiters: dict[str, RateLimiter] = field(default_factory=dict, init=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False)
    _acquire_count: int = field(default=0, init=False)

    def _get_limiter(self, key: str) -> RateLimiter:
        """Get or create limiter for key."""
        if key not in self._limiters:
            if self.factory:
                self._limiters[key] = self.factory()
            else:
                self._limiters[key] = TokenBucketLimiter(
                    rate=self.rate,
                    capacity=self.capacity,
                )
        return self._limiters[key]

    def _maybe_cleanup(self) -> None:
        """Periodically clean up unused limiters."""
        self._acquire_count += 1
        if self._acquire_count >= self.cleanup_interval:
            self._acquire_count = 0
            # Remove limiters with full buckets (unused)
            to_remove = [
                key
                for key, limiter in self._limiters.items()
                if isinstance(limiter, TokenBucketLimiter) and limiter.available_tokens >= self.capacity
            ]
            for key in to_remove:
                del self._limiters[key]

    def acquire(self, key: str, tokens: int = 1, block: bool = False) -> bool:
        """Acquire tokens for a specific key."""
        with self._lock:
            self._maybe_cleanup()
            limiter = self._get_limiter(key)

        return limiter.acquire(tokens, block)

    def get(self, key: str) -> RateLimiter | None:
        """Get limiter for key if exists."""
        with self._lock:
            return self._limiters.get(key)

    def remove(self, key: str) -> None:
        """Remove limiter for key."""
        with self._lock:
            self._limiters.pop(key, None)

    def get_wait_time(self, key: str, tokens: int = 1) -> float:
        """Get wait time for a specific key."""
        with self._lock:
            limiter = self._get_limiter(key)

        return limiter.get_wait_time(tokens)


class CompositeRateLimiter(RateLimiter):
    """Combines multiple rate limiters.

    All limiters must allow the request for it to proceed.

    Example:
        >>> # 100/min AND 1000/hour
        >>> limiter = CompositeRateLimiter([
        ...     SlidingWindowLimiter(100, 60),
        ...     SlidingWindowLimiter(1000, 3600),
        ... ])
    """

    def __init__(self, limiters: list[RateLimiter]):
        self._limiters = limiters

    def acquire(self, tokens: int = 1, block: bool = False) -> bool:
        """Acquire from all limiters."""
        # First check all without acquiring
        for limiter in self._limiters:
            if limiter.get_wait_time(tokens) > 0 and not block:
                return False

        # Acquire from all
        for limiter in self._limiters:
            if not limiter.acquire(tokens, block):
                return False

        return True

    def get_wait_time(self, tokens: int = 1) -> float:
        """Get max wait time across all limiters."""
        return max(limiter.get_wait_time(tokens) for limiter in self._limiters)


# Global rate limiter registry
_rate_limiters: dict[str, RateLimiter] = {}
_registry_lock = threading.Lock()


def get_rate_limiter(
    name: str,
    rate: float = 10.0,
    capacity: float = 20.0,
) -> RateLimiter:
    """Get or create a named rate limiter."""
    with _registry_lock:
        if name not in _rate_limiters:
            _rate_limiters[name] = TokenBucketLimiter(rate=rate, capacity=capacity)
        return _rate_limiters[name]


def get_all_rate_limiters() -> dict[str, RateLimiter]:
    """Get all registered rate limiters."""
    with _registry_lock:
        return dict(_rate_limiters)
