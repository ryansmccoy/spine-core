"""Tests for ``spine.core.cache.RedisCache`` — Redis-backed cache backend.

Requires ``redis`` package. Tests are skipped if not installed.
"""

from __future__ import annotations

import json
import sys
from unittest.mock import MagicMock

import pytest

redis = pytest.importorskip("redis")


class TestRedisCacheInit:
    def test_init_default(self):
        from spine.core.cache import RedisCache

        with pytest.MonkeyPatch.context() as mp:
            mock_from_url = MagicMock(return_value=MagicMock())
            mp.setattr(redis, "from_url", mock_from_url)

            cache = RedisCache()
            mock_from_url.assert_called_once_with("redis://localhost:6379/0", decode_responses=False)

    def test_init_custom_url(self):
        from spine.core.cache import RedisCache

        with pytest.MonkeyPatch.context() as mp:
            mock_from_url = MagicMock(return_value=MagicMock())
            mp.setattr(redis, "from_url", mock_from_url)

            cache = RedisCache("redis://custom:6380/1", default_ttl_seconds=600)
            mock_from_url.assert_called_once_with("redis://custom:6380/1", decode_responses=False)


class TestRedisCacheOperations:
    @pytest.fixture
    def cache_and_client(self):
        from spine.core.cache import RedisCache

        with pytest.MonkeyPatch.context() as mp:
            client = MagicMock()
            mock_from_url = MagicMock(return_value=client)
            mp.setattr(redis, "from_url", mock_from_url)

            cache = RedisCache()
            yield cache, client

    def test_get_existing_key(self, cache_and_client):
        cache, client = cache_and_client
        client.get.return_value = json.dumps({"key": "value"}).encode()

        result = cache.get("test-key")
        assert result == {"key": "value"}
        client.get.assert_called_once_with("test-key")

    def test_get_missing_key(self, cache_and_client):
        cache, client = cache_and_client
        client.get.return_value = None

        result = cache.get("missing")
        assert result is None

    def test_set_with_ttl(self, cache_and_client):
        cache, client = cache_and_client
        cache._default_ttl = None
        cache.set("k", {"v": 1}, ttl_seconds=60)
        client.setex.assert_called_once_with("k", 60, json.dumps({"v": 1}))

    def test_set_with_default_ttl(self, cache_and_client):
        cache, client = cache_and_client
        cache._default_ttl = 3600
        cache.set("k", "hello")
        client.setex.assert_called_once_with("k", 3600, json.dumps("hello"))

    def test_set_no_ttl(self, cache_and_client):
        cache, client = cache_and_client
        cache._default_ttl = None
        cache.set("k", "v")
        client.set.assert_called_once_with("k", json.dumps("v"))

    def test_delete(self, cache_and_client):
        cache, client = cache_and_client
        cache.delete("k")
        client.delete.assert_called_once_with("k")

    def test_exists_true(self, cache_and_client):
        cache, client = cache_and_client
        client.exists.return_value = 1
        assert cache.exists("k") is True

    def test_exists_false(self, cache_and_client):
        cache, client = cache_and_client
        client.exists.return_value = 0
        assert cache.exists("k") is False

    def test_clear(self, cache_and_client):
        cache, client = cache_and_client
        cache.clear()
        client.flushdb.assert_called_once()
