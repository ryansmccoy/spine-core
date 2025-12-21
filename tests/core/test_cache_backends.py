"""Tests for ``spine.core.cache`` — InMemoryCache and RedisCache."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from spine.core.cache import InMemoryCache, RedisCache


class TestInMemoryCache:
    def test_get_set(self):
        c = InMemoryCache(default_ttl_seconds=None)
        c.set("k1", {"val": 42})
        assert c.get("k1") == {"val": 42}

    def test_get_missing(self):
        c = InMemoryCache()
        assert c.get("nope") is None

    def test_delete(self):
        c = InMemoryCache(default_ttl_seconds=None)
        c.set("k1", 1)
        c.delete("k1")
        assert c.get("k1") is None
        c.delete("nonexistent")  # no error

    def test_exists(self):
        c = InMemoryCache(default_ttl_seconds=None)
        assert c.exists("k") is False
        c.set("k", "v")
        assert c.exists("k") is True

    def test_clear(self):
        c = InMemoryCache(default_ttl_seconds=None)
        c.set("a", 1)
        c.set("b", 2)
        c.clear()
        assert c.size() == 0

    def test_size(self):
        c = InMemoryCache(default_ttl_seconds=None)
        assert c.size() == 0
        c.set("a", 1)
        assert c.size() == 1

    def test_ttl_expiry(self):
        c = InMemoryCache(default_ttl_seconds=None)
        c.set("k", "val", ttl_seconds=1)
        assert c.get("k") == "val"
        # Manually expire by manipulating the store
        c._store["k"] = ("val", time.time() - 1)
        assert c.get("k") is None

    def test_ttl_exists_expired(self):
        c = InMemoryCache(default_ttl_seconds=None)
        c.set("k", "val", ttl_seconds=1)
        c._store["k"] = ("val", time.time() - 1)
        assert c.exists("k") is False

    def test_default_ttl(self):
        c = InMemoryCache(default_ttl_seconds=3600)
        c.set("k", "v")
        _, expires = c._store["k"]
        assert expires is not None
        assert expires > time.time()

    def test_lru_eviction(self):
        c = InMemoryCache(max_size=2, default_ttl_seconds=None)
        c.set("a", 1)
        c.set("b", 2)
        c.set("c", 3)  # evicts "a"
        assert c.get("a") is None
        assert c.get("b") == 2
        assert c.get("c") == 3

    def test_overwrite_key(self):
        c = InMemoryCache(max_size=2, default_ttl_seconds=None)
        c.set("a", 1)
        c.set("a", 2)  # overwrite, should NOT count as new key
        assert c.size() == 1
        assert c.get("a") == 2


class TestRedisCache:
    def test_init_no_redis(self):
        with patch.dict("sys.modules", {"redis": None}):
            with pytest.raises(ImportError, match="redis"):
                RedisCache()

    def test_lifecycle_with_mock_redis(self):
        """Test get/set/delete/exists/clear with a mocked redis module."""
        import json
        import types

        # Create a fake redis module
        fake_redis = types.ModuleType("redis")
        mock_client = MagicMock()
        fake_redis.from_url = MagicMock(return_value=mock_client)

        with patch.dict("sys.modules", {"redis": fake_redis}):
            c = RedisCache("redis://localhost:6379", default_ttl_seconds=60)

            # test set with TTL
            c.set("k", {"key": "val"})
            mock_client.setex.assert_called_once()

            # test set without TTL
            mock_client.reset_mock()
            c2 = RedisCache("redis://localhost:6379", default_ttl_seconds=None)
            c2.set("k", "v")
            mock_client.set.assert_called_once()

            # test get hit
            mock_client.get.return_value = json.dumps({"key": "val"}).encode()
            assert c.get("k") == {"key": "val"}

            # test get miss
            mock_client.get.return_value = None
            assert c.get("k") is None

            # test delete
            c.delete("k")
            mock_client.delete.assert_called_with("k")

            # test exists
            mock_client.exists.return_value = 1
            assert c.exists("k") is True

            # test clear
            c.clear()
            mock_client.flushdb.assert_called_once()
