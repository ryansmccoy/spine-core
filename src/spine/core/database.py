"""
Spine-Core Database Pool - Async PostgreSQL connection pool utilities.

This module provides standardized database connection pooling using asyncpg
that can be imported by any spine package.

Manifesto:
    Database connections are expensive (TCP handshake, auth, TLS).
    A connection pool maintains warm connections ready for use.
    This module provides:

    - **Pooling:** Efficient connection reuse across requests
    - **Normalization:** URL format handling for asyncpg compatibility
    - **Lifecycle:** Clean pool creation and shutdown
    - **Monitoring:** Connection pool health checks

    Every spine that needs PostgreSQL should use spine.core.database.

Architecture:
    ::

        ┌─────────────────────────────────────────────────────────────┐
        │                    Connection Pool                          │
        └─────────────────────────────────────────────────────────────┘

        Pool Management:
        ┌────────────────────────────────────────────────────────────┐
        │ pool = await create_pool(database_url, min_size=5)         │
        │                                                             │
        │ async with pool.acquire() as conn:                          │
        │     result = await conn.fetch("SELECT * FROM users")        │
        │                                                             │
        │ await close_pool(pool)                                      │
        └────────────────────────────────────────────────────────────┘

        Pool State:
        ┌────────────────────────────────────────────────────────────┐
        │  ┌─────────┬─────────┬─────────┬─────────┬─────────┐       │
        │  │  conn1  │  conn2  │  conn3  │   ...   │  connN  │       │
        │  │  (idle) │ (in-use)│  (idle) │         │  (idle) │       │
        │  └─────────┴─────────┴─────────┴─────────┴─────────┘       │
        │  min_size=5 ───────────────────────────► max_size=20       │
        └────────────────────────────────────────────────────────────┘

Features:
    - Async connection pooling with asyncpg
    - URL normalization (SQLAlchemy dialect stripping)
    - SSL configuration support
    - Health check functionality
    - Graceful shutdown

Examples:
    Create and use a pool:

    >>> from spine.core.database import create_pool, close_pool
    >>> pool = await create_pool("postgresql://user:pass@localhost/db")
    >>> async with pool.acquire() as conn:
    ...     rows = await conn.fetch("SELECT * FROM users LIMIT 10")
    >>> await close_pool(pool)

    With custom pool sizes:

    >>> pool = await create_pool(
    ...     "postgresql://localhost/spine",
    ...     min_size=2,
    ...     max_size=20,
    ... )

Performance:
    - Connection acquisition: ~50μs from pool (vs ~50ms new connection)
    - Recommended: min_size=5, max_size=20 for typical workloads
    - Pool exhaustion blocks callers until connection available

Guardrails:
    - PREFER dependency injection over global pools in production
    - ALWAYS use context manager (async with pool.acquire())
    - NEVER hold connections longer than necessary
    - MONITOR pool metrics (size, free_size)
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from asyncpg import Pool

logger = logging.getLogger("spine.core.database")


def normalize_database_url(url: str) -> str:
    """Normalize database URL for asyncpg compatibility.

    Converts SQLAlchemy-style URLs (postgresql+asyncpg://) to
    plain PostgreSQL URLs (postgresql://) and removes unsupported
    query parameters.

    Args:
        url: Database connection URL

    Returns:
        Normalized URL suitable for asyncpg

    Examples:
        >>> normalize_database_url("postgresql+asyncpg://localhost/db")
        'postgresql://localhost/db'

        >>> normalize_database_url("postgresql://localhost/db?sslmode=require")
        'postgresql://localhost/db'
    """
    # Strip SQLAlchemy dialect prefix
    if url.startswith("postgresql+asyncpg://"):
        url = url.replace("postgresql+asyncpg://", "postgresql://", 1)

    # Remove sslmode query parameter (asyncpg handles SSL via ssl= param)
    if "?sslmode=" in url or "&sslmode=" in url:
        url = re.sub(r"[?&]sslmode=[^&]*", "", url)
        url = url.rstrip("?&")

    return url


async def create_pool(
    database_url: str,
    min_size: int = 5,
    max_size: int = 20,
    command_timeout: float = 60.0,
    ssl: bool = False,
) -> Pool:
    """Create an asyncpg connection pool.

    Args:
        database_url: PostgreSQL connection string
        min_size: Minimum connections to maintain (default: 5)
        max_size: Maximum connections allowed (default: 20)
        command_timeout: Query timeout in seconds (default: 60)
        ssl: Enable SSL/TLS (default: False for local dev)

    Returns:
        Configured asyncpg connection pool

    Raises:
        RuntimeError: If pool creation fails
        asyncpg.PostgresError: If connection fails

    Examples:
        >>> pool = await create_pool("postgresql://localhost/spine")
        >>> pool.get_size()
        5
    """
    try:
        import asyncpg
    except ImportError as e:
        raise ImportError("asyncpg is required for database pooling. Install with: pip install asyncpg") from e

    # Normalize URL for asyncpg
    database_url = normalize_database_url(database_url)

    logger.info(f"Creating connection pool (min={min_size}, max={max_size})")

    pool = await asyncpg.create_pool(
        database_url,
        min_size=min_size,
        max_size=max_size,
        command_timeout=command_timeout,
        ssl=ssl,
    )

    if pool is None:
        raise RuntimeError("Failed to create connection pool")

    # Test the connection
    async with pool.acquire() as conn:
        version = await conn.fetchval("SELECT version()")
        logger.info(f"Connected to PostgreSQL: {version[:60]}...")

    return pool


async def close_pool(pool: Pool) -> None:
    """Close the connection pool gracefully.

    Waits for all connections to be released before closing.

    Args:
        pool: The pool to close

    Examples:
        >>> await close_pool(pool)
    """
    logger.info("Closing connection pool")
    await pool.close()


async def pool_health_check(pool: Pool) -> dict:
    """Check pool health and return statistics.

    Args:
        pool: The pool to check

    Returns:
        Dict with pool statistics:
        - size: Current number of connections
        - free_size: Number of idle connections
        - min_size: Minimum pool size
        - max_size: Maximum pool size
        - healthy: True if pool is operational

    Examples:
        >>> stats = await pool_health_check(pool)
        >>> stats['healthy']
        True
    """
    try:
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")

        return {
            "size": pool.get_size(),
            "free_size": pool.get_idle_size(),
            "min_size": pool.get_min_size(),
            "max_size": pool.get_max_size(),
            "healthy": True,
        }
    except Exception as e:
        logger.error(f"Pool health check failed: {e}")
        return {
            "size": pool.get_size() if pool else 0,
            "free_size": 0,
            "min_size": 0,
            "max_size": 0,
            "healthy": False,
            "error": str(e),
        }


__all__ = [
    "normalize_database_url",
    "create_pool",
    "close_pool",
    "pool_health_check",
]
