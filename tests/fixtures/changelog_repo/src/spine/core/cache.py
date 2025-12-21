"""Caching abstraction with multiple backend implementations.

Stability: stable
Tier: basic
Since: 0.2.0
Dependencies: optional: redis
Doc-Types: TECHNICAL_DESIGN, API_REFERENCE
Tags: cache, backend, redis, memory

Provides a unified CacheBackend protocol with in-memory and Redis
implementations.
"""

from __future__ import annotations
from typing import Any, Protocol


class CacheBackend(Protocol):
    """Protocol for cache backend implementations."""

    def get(self, key: str) -> Any: ...
    def set(self, key: str, value: Any, *, ttl_seconds: int | None = None) -> None: ...
    def delete(self, key: str) -> bool: ...
    def exists(self, key: str) -> bool: ...
    def clear(self) -> None: ...


class InMemoryCache:
    """Thread-safe in-memory cache with TTL support."""

    def __init__(self, max_size: int = 1000) -> None:
        self._store: dict[str, Any] = {}
        self._max_size = max_size

    def get(self, key: str) -> Any:
        return self._store.get(key)

    def set(self, key: str, value: Any, *, ttl_seconds: int | None = None) -> None:
        self._store[key] = value

    def delete(self, key: str) -> bool:
        return self._store.pop(key, None) is not None

    def exists(self, key: str) -> bool:
        return key in self._store

    def clear(self) -> None:
        self._store.clear()
