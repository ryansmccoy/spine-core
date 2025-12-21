"""Tests for ``spine.ops.database`` — database operations."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from spine.ops.context import OperationContext


def _mock_context(tables=None, backend="sqlite"):
    """Create a mock OperationContext with a connection that simulates DB behavior."""
    conn = MagicMock()
    # Default: list_tables returns some tables
    if tables is not None:
        conn.execute.return_value.fetchall.return_value = [(t,) for t in tables]
    ctx = OperationContext(conn=conn, caller="test")
    return ctx


class TestInitializeDatabase:
    def test_initialize_database_success(self):
        from spine.ops.database import initialize_database

        ctx = _mock_context()
        result = initialize_database(ctx)
        assert result.success is True

    def test_initialize_database_with_request(self):
        from spine.ops.database import initialize_database
        from spine.ops.requests import DatabaseInitRequest

        ctx = _mock_context()
        request = DatabaseInitRequest()
        result = initialize_database(ctx, request)
        assert result.success is True


class TestGetTableCounts:
    def test_table_counts_success(self):
        from spine.ops.database import get_table_counts

        conn = MagicMock()
        # Simulate table counts: each execute for count returns [(5,)]
        call_count = 0

        def side_effect(sql, params=()):
            nonlocal call_count
            cursor = MagicMock()
            if "count" in sql.lower() or "COUNT" in sql:
                cursor.fetchone.return_value = (call_count,)
                call_count += 1
            else:
                cursor.fetchall.return_value = []
            return cursor

        conn.execute.side_effect = side_effect
        ctx = OperationContext(conn=conn, caller="test")
        result = get_table_counts(ctx)
        assert result.success is True


class TestCheckDatabaseHealth:
    def test_health_check_success(self):
        from spine.ops.database import check_database_health

        conn = MagicMock()
        # type(conn).__name__ returns "SqliteConnection" for backend detection
        type(conn).__name__ = "SqliteConnection"

        # Simulate SELECT 1 success
        cursor = MagicMock()
        cursor.fetchone.return_value = (1,)
        conn.execute.return_value = cursor

        ctx = OperationContext(conn=conn, caller="test")
        result = check_database_health(ctx)
        assert result.success is True
        assert result.data is not None

    def test_health_check_failure(self):
        from spine.ops.database import check_database_health

        conn = MagicMock()
        conn.execute.side_effect = Exception("DB down")
        type(conn).__name__ = "SqliteConnection"

        ctx = OperationContext(conn=conn, caller="test")
        result = check_database_health(ctx)
        # Should still succeed but report unhealthy, or fail gracefully
        assert result is not None


class TestPurgeOldData:
    def test_purge_success(self):
        from spine.ops.database import purge_old_data
        from spine.ops.requests import PurgeRequest

        conn = MagicMock()
        cursor = MagicMock()
        cursor.rowcount = 5
        conn.execute.return_value = cursor

        ctx = OperationContext(conn=conn, caller="test")
        request = PurgeRequest(older_than_days=30)
        result = purge_old_data(ctx, request)
        assert result.success is True

    def test_purge_zero_days(self):
        from spine.ops.database import purge_old_data
        from spine.ops.requests import PurgeRequest

        conn = MagicMock()
        cursor = MagicMock()
        cursor.rowcount = 0
        conn.execute.return_value = cursor

        ctx = OperationContext(conn=conn, caller="test")
        request = PurgeRequest(older_than_days=0)
        result = purge_old_data(ctx, request)
        assert result is not None
