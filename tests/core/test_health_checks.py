"""Tests for ``spine.core.health_checks`` — dependency health check functions."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestCheckPostgres:
    @pytest.mark.asyncio
    async def test_check_postgres_success(self):
        asyncpg = pytest.importorskip("asyncpg")

        with patch.object(asyncpg, "connect", new_callable=AsyncMock) as mock_connect:
            conn = AsyncMock()
            conn.fetchval = AsyncMock(return_value=1)
            conn.close = AsyncMock()
            mock_connect.return_value = conn

            from spine.core.health_checks import check_postgres

            result = await check_postgres("postgresql://localhost/test")
            assert result is True
            conn.fetchval.assert_called_once_with("SELECT 1")
            conn.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_check_postgres_connection_error(self):
        asyncpg = pytest.importorskip("asyncpg")

        with patch.object(asyncpg, "connect", new_callable=AsyncMock) as mock_connect:
            mock_connect.side_effect = OSError("Connection refused")

            from spine.core.health_checks import check_postgres

            with pytest.raises(OSError, match="Connection refused"):
                await check_postgres("postgresql://localhost/test")


class TestCheckHTTP:
    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_check_http_success(self, mock_client_cls):
        from spine.core.health_checks import check_http

        resp = MagicMock()
        resp.status_code = 200
        resp.raise_for_status = MagicMock()

        client = AsyncMock()
        client.get = AsyncMock(return_value=resp)
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = client

        result = await check_http("http://localhost:9200")
        assert result is True

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_check_http_server_error(self, mock_client_cls):
        import httpx

        from spine.core.health_checks import check_http

        client = AsyncMock()
        resp = MagicMock()
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "500", request=MagicMock(), response=resp,
        )
        client.get = AsyncMock(return_value=resp)
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = client

        with pytest.raises(httpx.HTTPStatusError):
            await check_http("http://localhost:9200")


class TestConvenienceWrappers:
    @pytest.mark.asyncio
    @patch("spine.core.health_checks.check_http", new_callable=AsyncMock)
    async def test_check_elasticsearch(self, mock_check):
        from spine.core.health_checks import check_elasticsearch

        mock_check.return_value = True
        result = await check_elasticsearch("http://localhost:10920")
        assert result is True
        mock_check.assert_called_once_with("http://localhost:10920/_cluster/health")

    @pytest.mark.asyncio
    @patch("spine.core.health_checks.check_http", new_callable=AsyncMock)
    async def test_check_qdrant(self, mock_check):
        from spine.core.health_checks import check_qdrant

        mock_check.return_value = True
        result = await check_qdrant("http://localhost:10633")
        assert result is True
        mock_check.assert_called_once_with("http://localhost:10633/healthz")

    @pytest.mark.asyncio
    @patch("spine.core.health_checks.check_http", new_callable=AsyncMock)
    async def test_check_ollama(self, mock_check):
        from spine.core.health_checks import check_ollama

        mock_check.return_value = True
        result = await check_ollama("http://localhost:10434")
        assert result is True
        mock_check.assert_called_once_with("http://localhost:10434/api/tags")

    @pytest.mark.asyncio
    @patch("spine.core.health_checks.check_http", new_callable=AsyncMock)
    async def test_check_elasticsearch_default_url(self, mock_check):
        from spine.core.health_checks import check_elasticsearch

        mock_check.return_value = True
        result = await check_elasticsearch()
        assert result is True
        mock_check.assert_called_once_with("http://localhost:10920/_cluster/health")
