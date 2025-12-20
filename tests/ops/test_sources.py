"""Tests for spine.ops.sources — source, fetch, cache, and DB connection operations."""

import json

from spine.ops.database import initialize_database
from spine.ops.sources import (
    delete_database_connection,
    delete_source,
    disable_source,
    enable_source,
    get_source,
    invalidate_source_cache,
    list_database_connections,
    list_source_cache,
    list_source_fetches,
    list_sources,
    register_database_connection,
    register_source,
    test_database_connection as check_database_connection,
)
from spine.ops.requests import (
    CreateDatabaseConnectionRequest,
    CreateSourceRequest,
    ListDatabaseConnectionsRequest,
    ListSourceFetchesRequest,
    ListSourcesRequest,
)


# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #


def _insert_source(ctx, source_id="src_test1", name="finra.weekly",
                    source_type="file", domain="finra", enabled=1):
    """Insert a test source row."""
    ctx.conn.execute(
        """
        INSERT INTO core_sources (
            id, name, source_type, config_json, domain,
            enabled, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
        """,
        (source_id, name, source_type, '{"path": "data/*.psv"}',
         domain, enabled),
    )
    ctx.conn.commit()


def _insert_fetch(ctx, fetch_id="fetch_test1", source_id="src_test1",
                   source_name="finra.weekly", status="SUCCESS"):
    """Insert a test source fetch row."""
    ctx.conn.execute(
        """
        INSERT INTO core_source_fetches (
            id, source_id, source_name, source_type, source_locator,
            status, record_count, byte_count, started_at, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
        """,
        (fetch_id, source_id, source_name, "file", "data/test.psv",
         status, 100, 2048),
    )
    ctx.conn.commit()


def _insert_cache_entry(ctx, cache_key="cache_test1", source_id="src_test1"):
    """Insert a test source cache row."""
    ctx.conn.execute(
        """
        INSERT INTO core_source_cache (
            cache_key, source_id, source_type, source_locator,
            content_hash, content_size, fetched_at, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
        """,
        (cache_key, source_id, "file", "data/test.psv", "abc123", 2048),
    )
    ctx.conn.commit()


def _insert_db_connection(ctx, conn_id="db_test1", name="prod-postgres",
                           dialect="postgresql", enabled=1):
    """Insert a test database connection row."""
    ctx.conn.execute(
        """
        INSERT INTO core_database_connections (
            id, name, dialect, host, port, database,
            pool_size, max_overflow, pool_timeout,
            enabled, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
        """,
        (conn_id, name, dialect, "localhost", 5432, "spine_db",
         5, 10, 30, enabled),
    )
    ctx.conn.commit()


# ------------------------------------------------------------------ #
# Sources CRUD
# ------------------------------------------------------------------ #


class TestListSources:
    def test_empty(self, ctx):
        initialize_database(ctx)
        result = list_sources(ctx, ListSourcesRequest())
        assert result.success is True
        assert result.data == []
        assert result.total == 0

    def test_with_data(self, ctx):
        initialize_database(ctx)
        _insert_source(ctx)
        result = list_sources(ctx, ListSourcesRequest())
        assert result.success is True
        assert result.total == 1
        assert result.data[0].name == "finra.weekly"
        assert result.data[0].source_type == "file"

    def test_filter_by_type(self, ctx):
        initialize_database(ctx)
        _insert_source(ctx, "s1", "source-file", "file")
        _insert_source(ctx, "s2", "source-http", "http")

        result = list_sources(ctx, ListSourcesRequest(source_type="http"))
        assert result.success is True
        assert result.total == 1
        assert result.data[0].name == "source-http"

    def test_filter_by_domain(self, ctx):
        initialize_database(ctx)
        _insert_source(ctx, "s1", "src-a", domain="finra")
        _insert_source(ctx, "s2", "src-b", domain="market_data")

        result = list_sources(ctx, ListSourcesRequest(domain="finra"))
        assert result.success is True
        assert result.total == 1

    def test_filter_by_enabled(self, ctx):
        initialize_database(ctx)
        _insert_source(ctx, "s1", "active", enabled=1)
        _insert_source(ctx, "s2", "inactive", enabled=0)

        result = list_sources(ctx, ListSourcesRequest(enabled=True))
        assert result.success is True
        assert result.total == 1
        assert result.data[0].name == "active"

    def test_pagination(self, ctx):
        initialize_database(ctx)
        for i in range(5):
            _insert_source(ctx, f"s_{i}", f"source-{i}")

        result = list_sources(ctx, ListSourcesRequest(limit=2, offset=0))
        assert result.success is True
        assert result.total == 5
        assert len(result.data) == 2
        assert result.has_more is True


class TestGetSource:
    def test_not_found(self, ctx):
        initialize_database(ctx)
        result = get_source(ctx, "nonexistent")
        assert result.success is False
        assert result.error.code == "NOT_FOUND"

    def test_found(self, ctx):
        initialize_database(ctx)
        _insert_source(ctx)
        result = get_source(ctx, "src_test1")
        assert result.success is True
        assert result.data.name == "finra.weekly"
        assert result.data.source_type == "file"
        assert result.data.enabled is True


class TestRegisterSource:
    def test_register(self, ctx):
        initialize_database(ctx)
        request = CreateSourceRequest(
            name="new-source",
            source_type="http",
            config={"url": "https://api.example.com"},
            domain="market_data",
        )
        result = register_source(ctx, request)
        assert result.success is True
        assert result.data["created"] is True
        assert result.data["name"] == "new-source"
        assert "id" in result.data

    def test_register_dry_run(self, dry_ctx):
        initialize_database(dry_ctx)
        request = CreateSourceRequest(name="dry-source")
        result = register_source(dry_ctx, request)
        assert result.success is True
        assert result.data["dry_run"] is True


class TestDeleteSource:
    def test_delete(self, ctx):
        initialize_database(ctx)
        _insert_source(ctx)
        result = delete_source(ctx, "src_test1")
        assert result.success is True
        assert result.data["deleted"] is True

        check = get_source(ctx, "src_test1")
        assert check.success is False

    def test_delete_dry_run(self, ctx):
        initialize_database(ctx)
        _insert_source(ctx)
        result = delete_source(ctx, "src_test1", dry_run=True)
        assert result.success is True
        assert result.data["dry_run"] is True

        check = get_source(ctx, "src_test1")
        assert check.success is True


class TestEnableDisableSource:
    def test_enable(self, ctx):
        initialize_database(ctx)
        _insert_source(ctx, enabled=0)
        result = enable_source(ctx, "src_test1")
        assert result.success is True
        assert result.data["enabled"] is True

    def test_disable(self, ctx):
        initialize_database(ctx)
        _insert_source(ctx, enabled=1)
        result = disable_source(ctx, "src_test1")
        assert result.success is True
        assert result.data["disabled"] is True

    def test_enable_dry_run(self, dry_ctx):
        initialize_database(dry_ctx)
        result = enable_source(dry_ctx, "src_test1")
        assert result.success is True
        assert result.data["dry_run"] is True

    def test_disable_dry_run(self, dry_ctx):
        initialize_database(dry_ctx)
        result = disable_source(dry_ctx, "src_test1")
        assert result.success is True
        assert result.data["dry_run"] is True


# ------------------------------------------------------------------ #
# Source Fetches
# ------------------------------------------------------------------ #


class TestListSourceFetches:
    def test_empty(self, ctx):
        initialize_database(ctx)
        result = list_source_fetches(ctx, ListSourceFetchesRequest())
        assert result.success is True
        assert result.data == []
        assert result.total == 0

    def test_with_data(self, ctx):
        initialize_database(ctx)
        _insert_fetch(ctx)
        result = list_source_fetches(ctx, ListSourceFetchesRequest())
        assert result.success is True
        assert result.total == 1
        assert result.data[0].status == "SUCCESS"

    def test_filter_by_source_id(self, ctx):
        initialize_database(ctx)
        _insert_fetch(ctx, "f1", "src_1")
        _insert_fetch(ctx, "f2", "src_2", "other")

        result = list_source_fetches(
            ctx, ListSourceFetchesRequest(source_id="src_1")
        )
        assert result.success is True
        assert result.total == 1

    def test_filter_by_status(self, ctx):
        initialize_database(ctx)
        _insert_fetch(ctx, "f1", status="SUCCESS")
        _insert_fetch(ctx, "f2", "src_2", "other", status="FAILED")

        result = list_source_fetches(
            ctx, ListSourceFetchesRequest(status="FAILED")
        )
        assert result.success is True
        assert result.total == 1
        assert result.data[0].status == "FAILED"

    def test_pagination(self, ctx):
        initialize_database(ctx)
        for i in range(5):
            _insert_fetch(ctx, f"f_{i}", f"src_{i}", f"source-{i}")

        result = list_source_fetches(
            ctx, ListSourceFetchesRequest(limit=2, offset=0)
        )
        assert result.success is True
        assert result.total == 5
        assert len(result.data) == 2


# ------------------------------------------------------------------ #
# Source Cache
# ------------------------------------------------------------------ #


class TestListSourceCache:
    def test_empty(self, ctx):
        initialize_database(ctx)
        result = list_source_cache(ctx)
        assert result.success is True
        assert result.data == []
        assert result.total == 0

    def test_with_data(self, ctx):
        initialize_database(ctx)
        _insert_cache_entry(ctx)
        result = list_source_cache(ctx)
        assert result.success is True
        assert result.total == 1
        assert result.data[0].cache_key == "cache_test1"

    def test_filter_by_source_id(self, ctx):
        initialize_database(ctx)
        _insert_cache_entry(ctx, "ck1", "src_1")
        _insert_cache_entry(ctx, "ck2", "src_2")

        result = list_source_cache(ctx, source_id="src_1")
        assert result.success is True
        assert result.total == 1


class TestInvalidateSourceCache:
    def test_invalidate(self, ctx):
        initialize_database(ctx)
        _insert_cache_entry(ctx)
        result = invalidate_source_cache(ctx, "src_test1")
        assert result.success is True
        assert result.data["invalidated"] is True

    def test_invalidate_dry_run(self, ctx):
        initialize_database(ctx)
        _insert_cache_entry(ctx)
        result = invalidate_source_cache(ctx, "src_test1", dry_run=True)
        assert result.success is True
        assert result.data["dry_run"] is True
        assert result.data["would_delete"] == 1


# ------------------------------------------------------------------ #
# Database Connections
# ------------------------------------------------------------------ #


class TestListDatabaseConnections:
    def test_empty(self, ctx):
        initialize_database(ctx)
        result = list_database_connections(ctx, ListDatabaseConnectionsRequest())
        assert result.success is True
        assert result.data == []
        assert result.total == 0

    def test_with_data(self, ctx):
        initialize_database(ctx)
        _insert_db_connection(ctx)
        result = list_database_connections(ctx, ListDatabaseConnectionsRequest())
        assert result.success is True
        assert result.total == 1
        assert result.data[0].name == "prod-postgres"

    def test_filter_by_dialect(self, ctx):
        initialize_database(ctx)
        _insert_db_connection(ctx, "db_1", "pg-conn", "postgresql")
        _insert_db_connection(ctx, "db_2", "mysql-conn", "mysql")

        result = list_database_connections(
            ctx, ListDatabaseConnectionsRequest(dialect="postgresql")
        )
        assert result.success is True
        assert result.total == 1
        assert result.data[0].name == "pg-conn"

    def test_filter_by_enabled(self, ctx):
        initialize_database(ctx)
        _insert_db_connection(ctx, "db_1", "active", enabled=1)
        _insert_db_connection(ctx, "db_2", "disabled", enabled=0)

        result = list_database_connections(
            ctx, ListDatabaseConnectionsRequest(enabled=True)
        )
        assert result.success is True
        assert result.total == 1

    def test_pagination(self, ctx):
        initialize_database(ctx)
        for i in range(5):
            _insert_db_connection(ctx, f"db_{i}", f"conn-{i}")

        result = list_database_connections(
            ctx, ListDatabaseConnectionsRequest(limit=2, offset=0)
        )
        assert result.success is True
        assert result.total == 5
        assert len(result.data) == 2


class TestRegisterDatabaseConnection:
    def test_register(self, ctx):
        initialize_database(ctx)
        request = CreateDatabaseConnectionRequest(
            name="new-db",
            dialect="postgresql",
            host="db.example.com",
            port=5432,
            database="analytics",
        )
        result = register_database_connection(ctx, request)
        assert result.success is True
        assert result.data["created"] is True
        assert result.data["name"] == "new-db"

    def test_register_dry_run(self, dry_ctx):
        initialize_database(dry_ctx)
        request = CreateDatabaseConnectionRequest(name="dry-db")
        result = register_database_connection(dry_ctx, request)
        assert result.success is True
        assert result.data["dry_run"] is True


class TestDeleteDatabaseConnection:
    def test_delete(self, ctx):
        initialize_database(ctx)
        _insert_db_connection(ctx)
        result = delete_database_connection(ctx, "db_test1")
        assert result.success is True
        assert result.data["deleted"] is True

    def test_delete_dry_run(self, ctx):
        initialize_database(ctx)
        _insert_db_connection(ctx)
        result = delete_database_connection(ctx, "db_test1", dry_run=True)
        assert result.success is True
        assert result.data["dry_run"] is True


class TestTestDatabaseConnection:
    def test_not_found(self, ctx):
        initialize_database(ctx)
        result = check_database_connection(ctx, "nonexistent")
        assert result.success is False
        assert result.error.code == "NOT_FOUND"

    def test_found(self, ctx):
        initialize_database(ctx)
        _insert_db_connection(ctx)
        result = check_database_connection(ctx, "db_test1")
        assert result.success is True
        assert result.data["test_status"] == "not_implemented"
