"""
Tests for spine.core.cache module.

Covers:
- CacheBackend protocol compliance
- InMemoryCache: get/set/delete/exists/clear, LRU eviction, TTL expiry
- RedisCache: integration with real/mock Redis (requires redis extra)
"""

import time

import pytest


class TestInMemoryCache:
    """Test InMemoryCache backend."""

    def test_basic_get_set(self):
        """Cache should store and retrieve values."""
        from spine.core.cache import InMemoryCache

        cache = InMemoryCache(max_size=100, default_ttl_seconds=None)
        cache.set("key1", {"data": [1, 2, 3]})
        assert cache.get("key1") == {"data": [1, 2, 3]}

    def test_get_missing_key(self):
        """Getting a missing key should return None."""
        from spine.core.cache import InMemoryCache

        cache = InMemoryCache()
        assert cache.get("missing") is None

    def test_delete(self):
        """Delete should remove a key."""
        from spine.core.cache import InMemoryCache

        cache = InMemoryCache()
        cache.set("key1", "value1")
        assert cache.exists("key1")
        cache.delete("key1")
        assert not cache.exists("key1")
        assert cache.get("key1") is None

    def test_exists(self):
        """Exists should return True for valid keys."""
        from spine.core.cache import InMemoryCache

        cache = InMemoryCache()
        assert not cache.exists("key1")
        cache.set("key1", "value")
        assert cache.exists("key1")

    def test_clear(self):
        """Clear should remove all keys."""
        from spine.core.cache import InMemoryCache

        cache = InMemoryCache()
        cache.set("k1", 1)
        cache.set("k2", 2)
        cache.set("k3", 3)
        assert cache.size() == 3
        cache.clear()
        assert cache.size() == 0
        assert not cache.exists("k1")

    def test_ttl_expiry(self):
        """Keys should expire after TTL."""
        from spine.core.cache import InMemoryCache

        cache = InMemoryCache(default_ttl_seconds=1)
        cache.set("temp", "value", ttl_seconds=1)
        assert cache.exists("temp")
        time.sleep(1.1)
        assert not cache.exists("temp")
        assert cache.get("temp") is None

    def test_ttl_override_default(self):
        """Explicit TTL should override default."""
        from spine.core.cache import InMemoryCache

        cache = InMemoryCache(default_ttl_seconds=3600)
        cache.set("key1", "v1", ttl_seconds=1)
        assert cache.exists("key1")
        time.sleep(1.1)
        assert not cache.exists("key1")

    def test_lru_eviction(self):
        """Oldest key should be evicted when max_size reached."""
        from spine.core.cache import InMemoryCache

        cache = InMemoryCache(max_size=3, default_ttl_seconds=None)
        cache.set("k1", 1)
        cache.set("k2", 2)
        cache.set("k3", 3)
        assert cache.size() == 3

        # k1 is LRU → should be evicted
        cache.set("k4", 4)
        assert cache.size() == 3
        assert not cache.exists("k1")
        assert cache.exists("k2")
        assert cache.exists("k3")
        assert cache.exists("k4")

    def test_lru_updates_on_get(self):
        """Get should update LRU order."""
        from spine.core.cache import InMemoryCache

        cache = InMemoryCache(max_size=3, default_ttl_seconds=None)
        cache.set("k1", 1)
        cache.set("k2", 2)
        cache.set("k3", 3)

        # Access k1 → makes it most recent
        cache.get("k1")

        # Now k2 is LRU → should be evicted
        cache.set("k4", 4)
        assert cache.exists("k1")
        assert not cache.exists("k2")
        assert cache.exists("k3")
        assert cache.exists("k4")

    def test_none_ttl_never_expires(self):
        """TTL=None should never expire."""
        from spine.core.cache import InMemoryCache

        cache = InMemoryCache(default_ttl_seconds=None)
        cache.set("permanent", "value", ttl_seconds=None)
        time.sleep(0.5)
        assert cache.exists("permanent")

    def test_overwrite_existing_key(self):
        """Overwriting a key should update value and TTL."""
        from spine.core.cache import InMemoryCache

        cache = InMemoryCache()
        cache.set("key", "value1", ttl_seconds=10)
        cache.set("key", "value2", ttl_seconds=20)
        assert cache.get("key") == "value2"


@pytest.mark.skipif(
    not pytest.importorskip("redis", reason="Redis extra not installed"),
    reason="Redis integration test requires redis package",
)
class TestRedisCache:
    """Test RedisCache backend.

    Requires:
    - Redis running (Tier 3 Docker or local)
    - ``pip install spine-core[redis]``

    Skip if redis package not available.
    """

    @pytest.fixture
    def redis_url(self):
        """Redis URL for integration tests.

        Uses localhost:6379/9 (test database)
        Docker Compose Tier 3 exposes Redis on 6379.
        """
        return "redis://localhost:6379/9"

    def test_redis_get_set(self, redis_url):
        """RedisCache should store and retrieve values."""
        from spine.core.cache import RedisCache

        cache = RedisCache(redis_url, default_ttl_seconds=None)
        cache.clear()  # Clean slate

        cache.set("test:key1", {"data": [1, 2, 3]})
        assert cache.get("test:key1") == {"data": [1, 2, 3]}

        cache.clear()

    def test_redis_delete(self, redis_url):
        """Redis delete should remove keys."""
        from spine.core.cache import RedisCache

        cache = RedisCache(redis_url)
        cache.clear()

        cache.set("test:key", "value")
        assert cache.exists("test:key")
        cache.delete("test:key")
        assert not cache.exists("test:key")

        cache.clear()

    def test_redis_ttl_expiry(self, redis_url):
        """Redis keys should expire after TTL."""
        from spine.core.cache import RedisCache

        cache = RedisCache(redis_url)
        cache.clear()

        cache.set("test:temp", "value", ttl_seconds=1)
        assert cache.exists("test:temp")
        time.sleep(1.1)
        assert not cache.exists("test:temp")

        cache.clear()

    def test_redis_clear(self, redis_url):
        """Redis clear should flush database."""
        from spine.core.cache import RedisCache

        cache = RedisCache(redis_url)

        cache.set("test:k1", 1)
        cache.set("test:k2", 2)
        assert cache.exists("test:k1")

        cache.clear()

        assert not cache.exists("test:k1")
        assert not cache.exists("test:k2")


class TestCacheProtocol:
    """Test CacheBackend protocol compliance."""

    def test_in_memory_satisfies_protocol(self):
        """InMemoryCache should satisfy CacheBackend protocol."""
        from spine.core.cache import CacheBackend, InMemoryCache

        cache: CacheBackend = InMemoryCache()
        cache.set("key", "value")
        assert cache.get("key") == "value"
        cache.delete("key")
        assert not cache.exists("key")
        cache.clear()

    @pytest.mark.skipif(
        not pytest.importorskip("redis", reason="Redis extra not installed"),
        reason="Redis protocol test requires redis package",
    )
    def test_redis_satisfies_protocol(self):
        """RedisCache should satisfy CacheBackend protocol."""
        from spine.core.cache import CacheBackend, RedisCache

        cache: CacheBackend = RedisCache("redis://localhost:6379/9")
        cache.clear()
        cache.set("test:key", "value")
        assert cache.get("test:key") == "value"
        cache.delete("test:key")
        assert not cache.exists("test:key")
        cache.clear()
