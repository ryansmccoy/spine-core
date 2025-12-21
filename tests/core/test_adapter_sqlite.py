"""Tests for ``spine.core.adapters.sqlite`` — SQLite adapter."""

from __future__ import annotations

import sqlite3
from unittest.mock import patch

import pytest

from spine.core.adapters.sqlite import SQLiteAdapter
from spine.core.errors import DatabaseConnectionError


class TestSQLiteAdapterInit:
    def test_default_memory(self):
        adapter = SQLiteAdapter()
        assert adapter.db_type.value == "sqlite"
        assert adapter.is_connected is False

    def test_custom_path(self):
        adapter = SQLiteAdapter(path="/tmp/test.db")
        assert adapter.is_connected is False


class TestSQLiteAdapterConnect:
    def test_connect_memory(self):
        adapter = SQLiteAdapter(path=":memory:")
        adapter.connect()
        assert adapter.is_connected is True
        adapter.disconnect()

    def test_connect_readonly(self):
        adapter = SQLiteAdapter(path=":memory:", readonly=True)
        adapter.connect()
        assert adapter.is_connected is True
        adapter.disconnect()

    def test_connect_sets_row_factory(self):
        adapter = SQLiteAdapter(path=":memory:")
        adapter.connect()
        conn = adapter.get_connection()
        assert conn.row_factory == sqlite3.Row
        adapter.disconnect()

    def test_connect_enables_foreign_keys(self):
        adapter = SQLiteAdapter(path=":memory:")
        adapter.connect()
        conn = adapter.get_connection()
        cursor = conn.execute("PRAGMA foreign_keys")
        fk_enabled = cursor.fetchone()[0]
        assert fk_enabled == 1
        adapter.disconnect()

    @patch("sqlite3.connect", side_effect=sqlite3.OperationalError("unable to open database"))
    def test_connect_failure_raises(self, mock_connect):
        adapter = SQLiteAdapter(path="/nonexistent/path.db")
        with pytest.raises(DatabaseConnectionError):
            adapter.connect()


class TestSQLiteAdapterDisconnect:
    def test_disconnect(self):
        adapter = SQLiteAdapter(path=":memory:")
        adapter.connect()
        assert adapter.is_connected is True
        adapter.disconnect()
        assert adapter.is_connected is False

    def test_disconnect_when_not_connected(self):
        adapter = SQLiteAdapter()
        adapter.disconnect()  # Should not raise
        assert adapter.is_connected is False


class TestSQLiteAdapterGetConnection:
    def test_get_connection(self):
        adapter = SQLiteAdapter(path=":memory:")
        adapter.connect()
        conn = adapter.get_connection()
        assert conn is not None
        adapter.disconnect()

    def test_get_connection_auto_connects(self):
        adapter = SQLiteAdapter(path=":memory:")
        conn = adapter.get_connection()
        assert conn is not None
        adapter.disconnect()


class TestSQLiteAdapterTransaction:
    def test_transaction_commit(self):
        adapter = SQLiteAdapter(path=":memory:")
        adapter.connect()
        conn = adapter.get_connection()
        conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, name TEXT)")

        with adapter.transaction() as txn_conn:
            txn_conn.execute("INSERT INTO t (name) VALUES ('test')")

        cursor = conn.execute("SELECT name FROM t")
        rows = cursor.fetchall()
        assert len(rows) == 1
        adapter.disconnect()

    def test_transaction_rollback(self):
        adapter = SQLiteAdapter(path=":memory:")
        adapter.connect()
        conn = adapter.get_connection()
        conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, name TEXT)")
        conn.execute("INSERT INTO t (name) VALUES ('existing')")
        conn.commit()

        with pytest.raises(RuntimeError):
            with adapter.transaction() as txn_conn:
                txn_conn.execute("INSERT INTO t (name) VALUES ('new')")
                raise RuntimeError("force rollback")

        adapter.disconnect()


class TestSQLiteAdapterQuery:
    def test_query_returns_dicts(self):
        adapter = SQLiteAdapter(path=":memory:")
        adapter.connect()
        conn = adapter.get_connection()
        conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, name TEXT)")
        conn.execute("INSERT INTO t (name) VALUES ('alice')")
        conn.commit()

        rows = adapter.query("SELECT id, name FROM t")
        assert len(rows) == 1
        assert rows[0]["name"] == "alice"
        adapter.disconnect()

    def test_query_empty_result(self):
        adapter = SQLiteAdapter(path=":memory:")
        adapter.connect()
        conn = adapter.get_connection()
        conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY)")

        rows = adapter.query("SELECT * FROM t")
        assert rows == []
        adapter.disconnect()
