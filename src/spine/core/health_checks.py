"""Common dependency health-check callables for the Spine ecosystem.

Each function is an ``async`` callable that returns ``True`` on success or
raises on failure.  They are designed to be used with
:class:`spine.core.health.HealthCheck` and ``functools.partial`` to bind
connection URLs at app-startup time.

Manifesto:
    Health checks are the bridge between infrastructure dependencies
    and the health router. Each check is a pure async function that
    probes a single dependency — easy to test, easy to compose.

Features:
    - **check_postgres():** PostgreSQL connectivity via asyncpg
    - **check_redis():** Redis PING via aioredis
    - **check_ollama():** Ollama API /api/tags via httpx
    - **check_elasticsearch():** ES cluster health via httpx
    - **Composable:** Use functools.partial to bind URLs at startup

Examples:
    >>> from functools import partial
    >>> from spine.core.health import HealthCheck
    >>> from spine.core.health_checks import check_postgres, check_redis
    >>> checks = [
    ...     HealthCheck("postgres", partial(check_postgres, "postgresql://...")),
    ...     HealthCheck("redis", partial(check_redis, "redis://localhost:10379")),
    ... ]

Tags:
    health-checks, postgres, redis, ollama, elasticsearch, spine-core,
    async, dependency-probing

Doc-Types:
    - API Reference
    - Deployment Guide
"""

from __future__ import annotations

# ── PostgreSQL ───────────────────────────────────────────────────────────


async def check_postgres(url: str) -> bool:
    """``SELECT 1`` against a PostgreSQL instance via *asyncpg*.

    Raises on connection failure or timeout.
    """
    import asyncpg  # noqa: PLC0415

    conn = await asyncpg.connect(url, timeout=3)
    try:
        await conn.fetchval("SELECT 1")
        return True
    finally:
        await conn.close()


# ── Redis ────────────────────────────────────────────────────────────────


async def check_redis(url: str) -> bool:
    """``PING`` a Redis instance via *redis.asyncio*.

    Raises if Redis is unreachable.
    """
    import redis.asyncio as aioredis  # noqa: PLC0415

    r = aioredis.from_url(url, socket_timeout=3)
    try:
        pong = await r.ping()
        return bool(pong)
    finally:
        await r.aclose()


# ── Generic HTTP endpoint ────────────────────────────────────────────────


async def check_http(url: str, *, timeout: float = 3.0) -> bool:
    """``GET`` an HTTP endpoint and expect a 2xx response.

    Useful for Elasticsearch, Qdrant, Ollama, or any service that
    exposes a health URL.
    """
    import httpx  # noqa: PLC0415

    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return True


# ── Convenience wrappers for infrastructure services ─────────────────────


async def check_elasticsearch(url: str = "http://localhost:10920") -> bool:
    """Check Elasticsearch cluster health via ``/_cluster/health``."""
    return await check_http(f"{url}/_cluster/health")


async def check_qdrant(url: str = "http://localhost:10633") -> bool:
    """Check Qdrant via ``/healthz``."""
    return await check_http(f"{url}/healthz")


async def check_ollama(url: str = "http://localhost:10434") -> bool:
    """Check Ollama via ``/api/tags``."""
    return await check_http(f"{url}/api/tags")
