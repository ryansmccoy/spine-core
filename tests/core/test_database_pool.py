"""Tests for ``spine.core.database`` — async connection pool utilities."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from spine.core.database import normalize_database_url


class TestNormalizeDatabaseUrl:
    def test_strips_asyncpg_dialect(self):
        url = "postgresql+asyncpg://user:pass@host/db"
        assert normalize_database_url(url) == "postgresql://user:pass@host/db"

    def test_passes_plain_url(self):
        url = "postgresql://user:pass@host/db"
        assert normalize_database_url(url) == "postgresql://user:pass@host/db"

    def test_strips_sslmode_query_param(self):
        url = "postgresql://host/db?sslmode=require"
        assert normalize_database_url(url) == "postgresql://host/db"

    def test_strips_sslmode_with_other_params(self):
        url = "postgresql://host/db?sslmode=require&timeout=30"
        result = normalize_database_url(url)
        assert "sslmode" not in result

    def test_handles_both_dialect_and_sslmode(self):
        url = "postgresql+asyncpg://host/db?sslmode=prefer"
        result = normalize_database_url(url)
        assert result.startswith("postgresql://")
        assert "asyncpg" not in result
        assert "sslmode" not in result

    def test_handles_ampersand_sslmode(self):
        url = "postgresql://host/db?option=1&sslmode=require"
        result = normalize_database_url(url)
        assert "sslmode" not in result


class TestCreatePool:
    @pytest.mark.asyncio
    @patch("asyncpg.create_pool", new_callable=AsyncMock)
    async def test_create_pool_success(self, mock_create_pool):
        from spine.core.database import create_pool

        mock_pool = MagicMock()
        mock_conn = AsyncMock()
        mock_conn.fetchval = AsyncMock(return_value="PostgreSQL 15.2")

        # Mock the async context manager for pool.acquire()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_create_pool.return_value = mock_pool

        pool = await create_pool("postgresql://localhost/test")
        assert pool is mock_pool
        mock_create_pool.assert_called_once()

    @pytest.mark.asyncio
    @patch("asyncpg.create_pool", new_callable=AsyncMock)
    async def test_create_pool_none_raises(self, mock_create_pool):
        from spine.core.database import create_pool

        mock_create_pool.return_value = None

        with pytest.raises(RuntimeError, match="Failed to create"):
            await create_pool("postgresql://localhost/test")

    @pytest.mark.asyncio
    @patch("asyncpg.create_pool", new_callable=AsyncMock)
    async def test_create_pool_custom_sizes(self, mock_create_pool):
        from spine.core.database import create_pool

        mock_pool = MagicMock()
        mock_conn = AsyncMock()
        mock_conn.fetchval = AsyncMock(return_value="PostgreSQL 15.2")
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_create_pool.return_value = mock_pool

        await create_pool("postgresql://localhost/test", min_size=2, max_size=10)
        _, kwargs = mock_create_pool.call_args
        assert kwargs.get("min_size") == 2
        assert kwargs.get("max_size") == 10


class TestClosePool:
    @pytest.mark.asyncio
    async def test_close_pool(self):
        from spine.core.database import close_pool

        mock_pool = AsyncMock()
        await close_pool(mock_pool)
        mock_pool.close.assert_called_once()


class TestPoolHealthCheck:
    @pytest.mark.asyncio
    async def test_health_check_healthy(self):
        from spine.core.database import pool_health_check

        mock_pool = MagicMock()
        mock_pool.get_size.return_value = 5
        mock_pool.get_idle_size.return_value = 3
        mock_pool.get_min_size.return_value = 5
        mock_pool.get_max_size.return_value = 20

        mock_conn = AsyncMock()
        mock_conn.fetchval = AsyncMock(return_value=1)
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)

        stats = await pool_health_check(mock_pool)
        assert stats["healthy"] is True
        assert stats["size"] == 5
        assert stats["free_size"] == 3

    @pytest.mark.asyncio
    async def test_health_check_unhealthy(self):
        from spine.core.database import pool_health_check

        mock_pool = MagicMock()
        mock_pool.get_size.return_value = 0
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(
            side_effect=Exception("Connection failed"),
        )
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)

        stats = await pool_health_check(mock_pool)
        assert stats["healthy"] is False
        assert "error" in stats
