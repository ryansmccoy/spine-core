"""Tests for ``spine.core.adapters.postgresql`` — PostgreSQL adapter."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from spine.core.adapters.postgresql import PostgreSQLAdapter
from spine.core.errors import DatabaseConnectionError


class TestPostgreSQLAdapterInit:
    def test_default_config(self):
        adapter = PostgreSQLAdapter()
        assert adapter.db_type.value == "postgresql"
        assert adapter.is_connected is False

    def test_custom_config(self):
        adapter = PostgreSQLAdapter(
            host="db.example.com",
            port=5433,
            database="mydb",
            username="admin",
            password="secret",
            pool_size=10,
        )
        assert adapter.is_connected is False


class TestPostgreSQLAdapterConnect:
    @patch("psycopg2.pool.ThreadedConnectionPool")
    def test_connect_success(self, mock_pool_cls):
        mock_pool = MagicMock()
        mock_pool_cls.return_value = mock_pool

        adapter = PostgreSQLAdapter(host="localhost", database="spine")
        adapter.connect()
        assert adapter.is_connected is True

    @patch("psycopg2.pool.ThreadedConnectionPool")
    def test_connect_failure(self, mock_pool_cls):
        import psycopg2
        mock_pool_cls.side_effect = psycopg2.OperationalError("Connection refused")

        adapter = PostgreSQLAdapter(host="bad-host", database="spine")
        with pytest.raises(DatabaseConnectionError, match="Failed to connect"):
            adapter.connect()


class TestPostgreSQLAdapterDisconnect:
    @patch("psycopg2.pool.ThreadedConnectionPool")
    def test_disconnect(self, mock_pool_cls):
        mock_pool = MagicMock()
        mock_pool_cls.return_value = mock_pool

        adapter = PostgreSQLAdapter(host="localhost", database="spine")
        adapter.connect()
        adapter.disconnect()
        assert adapter.is_connected is False
        mock_pool.closeall.assert_called_once()

    def test_disconnect_when_not_connected(self):
        adapter = PostgreSQLAdapter()
        adapter.disconnect()  # No-op; should not raise


class TestPostgreSQLAdapterConnection:
    @patch("psycopg2.pool.ThreadedConnectionPool")
    def test_get_connection(self, mock_pool_cls):
        mock_pool = MagicMock()
        mock_conn = MagicMock()
        mock_pool.getconn.return_value = mock_conn
        mock_pool_cls.return_value = mock_pool

        adapter = PostgreSQLAdapter(host="localhost", database="spine")
        adapter.connect()
        conn = adapter.get_connection()
        assert conn is mock_conn

    @patch("psycopg2.pool.ThreadedConnectionPool")
    def test_transaction_commit(self, mock_pool_cls):
        mock_pool = MagicMock()
        mock_conn = MagicMock()
        mock_pool.getconn.return_value = mock_conn
        mock_pool_cls.return_value = mock_pool

        adapter = PostgreSQLAdapter(host="localhost", database="spine")
        adapter.connect()

        with adapter.transaction() as conn:
            conn.execute("INSERT INTO t VALUES (1)")

        mock_conn.commit.assert_called_once()
        mock_pool.putconn.assert_called_once_with(mock_conn)

    @patch("psycopg2.pool.ThreadedConnectionPool")
    def test_transaction_rollback(self, mock_pool_cls):
        mock_pool = MagicMock()
        mock_conn = MagicMock()
        mock_pool.getconn.return_value = mock_conn
        mock_pool_cls.return_value = mock_pool

        adapter = PostgreSQLAdapter(host="localhost", database="spine")
        adapter.connect()

        with pytest.raises(RuntimeError):
            with adapter.transaction() as conn:
                raise RuntimeError("boom")

        mock_conn.rollback.assert_called_once()
        mock_pool.putconn.assert_called_once_with(mock_conn)
