"""Tests for spine.ops.health — health and capabilities operations."""

from spine.ops.database import initialize_database
from spine.ops.health import get_capabilities, get_health


class TestGetHealth:
    def test_healthy(self, ctx):
        initialize_database(ctx)
        result = get_health(ctx)
        assert result.success is True
        assert result.data.status == "healthy"
        assert result.data.checks["database"] == "ok"
        assert result.data.version == "0.3.1"

    def test_health_without_tables(self, ctx):
        result = get_health(ctx)
        assert result.success is True
        assert result.data.database.connected is True


class TestGetCapabilities:
    def test_returns_capabilities(self, ctx):
        result = get_capabilities(ctx)
        assert result.success is True
        assert result.data.tier == "standard"
        assert result.data.sync_execution is True
        assert result.data.async_execution is True
        assert result.data.scheduling is True
        assert result.data.dlq is True
