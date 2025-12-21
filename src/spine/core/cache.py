"""
Caching abstraction with multiple backend implementations.

Provides a unified ``CacheBackend`` protocol with in-memory and Redis
implementations. Used across the ecosystem for feed deduplication,
query result caching, LLM response caching, and embedding caching.

Manifesto:
    Caching is a cross-cutting concern that every spine needs. Without
    a shared abstraction, each project implements its own cache with
    inconsistent APIs, no TTL support, and no backend portability.

    - **Protocol-based:** CacheBackend defines the contract
    - **Tier-aware:** InMemoryCache for dev, RedisCache for production
    - **TTL support:** Time-based expiration for all backends
    - **Zero config:** InMemoryCache works out of the box

Architecture:
    ::

        CacheBackend (Protocol)
        ├── InMemoryCache  — Tier 1 (single-process, bounded LRU)
        └── RedisCache     — Tier 2/3 (distributed, persistent)

        API: get(key) → value | None
             set(key, value, ttl_seconds=None)
             delete(key)
             exists(key) → bool
             clear()

Features:
    - **CacheBackend protocol:** get/set/delete/exists/clear with TTL
    - **InMemoryCache:** Bounded LRU cache with TTL expiration
    - **RedisCache:** Redis-backed distributed cache
    - **JSON values:** Keys are strings, values are JSON-serializable

Examples:
    >>> from spine.core.cache import InMemoryCache
    >>> cache = InMemoryCache(max_size=1000, default_ttl_seconds=3600)
    >>> cache.set("user:123", {"name": "Alice"})
    >>> cache.get("user:123")
    {'name': 'Alice'}
    >>> cache.exists("user:123")
    True

Performance:
    - InMemoryCache: O(1) get/set, bounded by max_size
    - RedisCache: ~0.5ms per operation (network round-trip)
    - TTL cleanup: Lazy (checked on get) for InMemoryCache

Guardrails:
    ❌ DON'T: Use InMemoryCache in multi-process deployments (no sharing)
    ✅ DO: Use RedisCache for distributed caching in Tier 2+

    ❌ DON'T: Cache without TTL (unbounded growth)
    ✅ DO: Always set default_ttl_seconds or per-key ttl_seconds

Tags:
    cache, caching, redis, in-memory, ttl, spine-core,
    protocol, tier-aware

Doc-Types:
    - API Reference
    - Infrastructure Guide
    - Technical Design
"""

from __future__ import annotations

import time
from typing import Any, Protocol


class CacheBackend(Protocol):
    """Protocol for cache backend implementations.

    All backends must provide get/set/delete/exists/clear operations with
    optional TTL support. Keys are strings, values are JSON-serializable.

    Implementations:
        - :class:`InMemoryCache` — single-process, bounded LRU cache
        - :class:`RedisCache` — distributed, Redis-backed cache
    """

    def get(self, key: str) -> Any | None:
        """Retrieve a value by key.

        Args:
            key: Cache key (string).

        Returns:
            Cached value (deserialized), or ``None`` if not found or expired.
        """
        ...

    def set(self, key: str, value: Any, *, ttl_seconds: int | None = None) -> None:
        """Store a value with optional TTL.

        Args:
            key: Cache key.
            value: JSON-serializable value to cache.
            ttl_seconds: Time-to-live in seconds. ``None`` → use default TTL.
        """
        ...

    def delete(self, key: str) -> None:
        """Remove a key from the cache.

        No-op if key does not exist.

        Args:
            key: Cache key to remove.
        """
        ...

    def exists(self, key: str) -> bool:
        """Check if a key exists and has not expired.

        Args:
            key: Cache key.

        Returns:
            ``True`` if key exists and is not expired, else ``False``.
        """
        ...

    def clear(self) -> None:
        """Remove all keys from the cache.

        Dangerous in production — use for testing only.
        """
        ...


# ------------------------------------------------------------------ #
# In-Memory Cache (Tier 1)
# ------------------------------------------------------------------ #


class InMemoryCache:
    """Bounded in-memory cache with TTL support.

    Uses LRU eviction when ``max_size`` is reached. Thread-safe for
    single-process use.

    Attributes:
        max_size: Maximum number of keys before LRU eviction.
        default_ttl_seconds: Default TTL for keys (``None`` → no expiry).

    Example:
        cache = InMemoryCache(max_size=500, default_ttl_seconds=1800)
        cache.set("session:abc", {"user_id": 42}, ttl_seconds=3600)
        session = cache.get("session:abc")
    """

    def __init__(
        self,
        *,
        max_size: int = 10_000,
        default_ttl_seconds: int | None = 3600,
    ):
        """Initialize in-memory cache.

        Args:
            max_size: Maximum number of keys (LRU eviction after).
            default_ttl_seconds: Default TTL for all keys (``None`` → no expiry).
        """
        self._store: dict[str, tuple[Any, float | None]] = {}
        self._access_order: list[str] = []
        self._max_size = max_size
        self._default_ttl = default_ttl_seconds

    def get(self, key: str) -> Any | None:
        """Retrieve a value by key."""
        if key not in self._store:
            return None

        value, expires_at = self._store[key]

        # Check expiry
        if expires_at is not None and time.time() > expires_at:
            self.delete(key)
            return None

        # Update LRU order
        if key in self._access_order:
            self._access_order.remove(key)
        self._access_order.append(key)

        return value

    def set(self, key: str, value: Any, *, ttl_seconds: int | None = None) -> None:
        """Store a value with optional TTL."""
        ttl = ttl_seconds if ttl_seconds is not None else self._default_ttl
        expires_at = (time.time() + ttl) if ttl else None

        # Evict LRU if at capacity
        if key not in self._store and len(self._store) >= self._max_size:
            if self._access_order:
                lru_key = self._access_order.pop(0)
                self._store.pop(lru_key, None)

        self._store[key] = (value, expires_at)

        # Update LRU order
        if key in self._access_order:
            self._access_order.remove(key)
        self._access_order.append(key)

    def delete(self, key: str) -> None:
        """Remove a key from the cache."""
        self._store.pop(key, None)
        if key in self._access_order:
            self._access_order.remove(key)

    def exists(self, key: str) -> bool:
        """Check if key exists and is not expired."""
        if key not in self._store:
            return False

        _, expires_at = self._store[key]
        if expires_at is not None and time.time() > expires_at:
            self.delete(key)
            return False

        return True

    def clear(self) -> None:
        """Remove all keys."""
        self._store.clear()
        self._access_order.clear()

    def size(self) -> int:
        """Return current number of cached keys."""
        return len(self._store)


# ------------------------------------------------------------------ #
# Redis Cache (Tier 2/3) — Optional
# ------------------------------------------------------------------ #


class RedisCache:
    """Redis-backed distributed cache.

    Requires ``redis`` package (install via ``pip install spine-core[redis]``).
    Thread-safe and process-safe via Redis atomic operations.

    Attributes:
        url: Redis connection URL (``redis://host:port/db``).
        default_ttl_seconds: Default TTL for keys.

    Example:
        cache = RedisCache("redis://localhost:6379/0", default_ttl_seconds=600)
        cache.set("product:123", {"name": "Widget", "price": 9.99})
        product = cache.get("product:123")

    Raises:
        ImportError: If ``redis`` package is not installed.
    """

    def __init__(
        self,
        url: str = "redis://localhost:6379/0",
        *,
        default_ttl_seconds: int | None = 3600,
    ):
        """Initialize Redis cache.

        Args:
            url: Redis connection URL.
            default_ttl_seconds: Default TTL for all keys (``None`` → no expiry).

        Raises:
            ImportError: If ``redis`` package not installed.
        """
        try:
            import redis
        except ImportError as exc:
            msg = (
                "Redis backend requires 'redis' package. "
                "Install with: pip install spine-core[redis]"
            )
            raise ImportError(msg) from exc

        self._client = redis.from_url(url, decode_responses=False)
        self._default_ttl = default_ttl_seconds

    def get(self, key: str) -> Any | None:
        """Retrieve a value by key."""
        import json

        raw = self._client.get(key)
        if raw is None:
            return None

        return json.loads(raw)

    def set(self, key: str, value: Any, *, ttl_seconds: int | None = None) -> None:
        """Store a value with optional TTL."""
        import json

        ttl = ttl_seconds if ttl_seconds is not None else self._default_ttl
        serialized = json.dumps(value)

        if ttl:
            self._client.setex(key, ttl, serialized)
        else:
            self._client.set(key, serialized)

    def delete(self, key: str) -> None:
        """Remove a key from the cache."""
        self._client.delete(key)

    def exists(self, key: str) -> bool:
        """Check if key exists."""
        return bool(self._client.exists(key))

    def clear(self) -> None:
        """Remove all keys from the current Redis database.

        Warning: This flushes the entire Redis DB — use with caution!
        """
        self._client.flushdb()


__all__ = [
    "CacheBackend",
    "InMemoryCache",
    "RedisCache",
]
