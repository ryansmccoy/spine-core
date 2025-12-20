"""Tests for spine.ops.database — database operations."""

from spine.ops.database import (
    check_database_health,
    get_table_counts,
    initialize_database,
    purge_old_data,
)
from spine.ops.requests import DatabaseInitRequest, PurgeRequest


class TestInitializeDatabase:
    def test_creates_tables(self, ctx):
        result = initialize_database(ctx)
        assert result.success is True
        assert result.data is not None
        assert len(result.data.tables_created) > 0
        assert result.data.dry_run is False

    def test_dry_run(self, dry_ctx):
        result = initialize_database(dry_ctx)
        assert result.success is True
        assert result.data.dry_run is True
        assert len(result.data.tables_created) > 0

    def test_idempotent(self, ctx):
        r1 = initialize_database(ctx)
        r2 = initialize_database(ctx)
        assert r1.success is True
        assert r2.success is True


class TestGetTableCounts:
    def test_returns_counts(self, ctx):
        # First init the DB
        initialize_database(ctx)
        result = get_table_counts(ctx)
        assert result.success is True
        assert len(result.data) > 0
        # All existing tables should have count >= 0
        for tc in result.data:
            assert tc.count >= 0

    def test_missing_tables_returns_negative(self, ctx):
        # Don't init — tables don't exist
        result = get_table_counts(ctx)
        assert result.success is True
        # Missing tables get count=-1
        for tc in result.data:
            assert tc.count == -1


class TestCheckDatabaseHealth:
    def test_healthy(self, ctx):
        initialize_database(ctx)
        result = check_database_health(ctx)
        assert result.success is True
        assert result.data.connected is True
        assert result.data.backend == "sqlite"
        assert result.data.latency_ms >= 0

    def test_counts_tables(self, ctx):
        initialize_database(ctx)
        result = check_database_health(ctx)
        assert result.data.table_count > 0


class TestPurgeOldData:
    def test_dry_run(self, dry_ctx):
        result = purge_old_data(dry_ctx, PurgeRequest(older_than_days=30))
        assert result.success is True
        assert result.data.dry_run is True
        assert len(result.data.tables_purged) > 0

    def test_purge_empty_tables(self, ctx):
        initialize_database(ctx)
        result = purge_old_data(ctx, PurgeRequest(older_than_days=1))
        assert result.success is True
