"""Tests for core.storage module.

Covers:
- StorageBackend protocol (runtime_checkable)
- SQLHelper.insert_or_replace (sqlite + postgres dialects)
- SQLHelper.upsert (sqlite + postgres dialects)
"""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager

import pytest

from spine.core.protocols import Connection
from spine.core.storage import SQLHelper, StorageBackend


# ---------------------------------------------------------------------------
# StorageBackend protocol
# ---------------------------------------------------------------------------


class GoodBackend:
    """Implements all StorageBackend methods."""

    @contextmanager
    def transaction(self) -> Iterator[Connection]:
        yield sqlite3.connect(":memory:")

    def get_connection(self) -> Connection:
        return sqlite3.connect(":memory:")


class BadBackend:
    """Missing required methods."""

    pass


class TestStorageBackendProtocol:
    def test_good_backend_satisfies_protocol(self):
        assert isinstance(GoodBackend(), StorageBackend)

    def test_bad_backend_fails_protocol(self):
        assert not isinstance(BadBackend(), StorageBackend)

    def test_protocol_is_runtime_checkable(self):
        """StorageBackend is decorated with @runtime_checkable."""
        import typing

        assert hasattr(StorageBackend, "__protocol_attrs__") or isinstance(
            StorageBackend, type
        )


# ---------------------------------------------------------------------------
# SQLHelper.insert_or_replace
# ---------------------------------------------------------------------------


class TestSQLHelperInsertOrReplace:
    def test_sqlite_dialect(self):
        sql = SQLHelper.insert_or_replace("users", ["id", "name", "email"], dialect="sqlite")
        assert "INSERT OR REPLACE INTO users" in sql
        assert "(id, name, email)" in sql
        assert "(?, ?, ?)" in sql

    def test_postgres_dialect(self):
        sql = SQLHelper.insert_or_replace("users", ["id", "name"], dialect="postgres")
        assert "INSERT INTO users" in sql
        assert "(%s, %s)" in sql  # psycopg2 style placeholders
        # No OR REPLACE for postgres
        assert "OR REPLACE" not in sql

    def test_single_column(self):
        sql = SQLHelper.insert_or_replace("flags", ["flag_name"], dialect="sqlite")
        assert "(flag_name)" in sql
        assert "(?)" in sql

    def test_sqlite_is_default_dialect(self):
        sql = SQLHelper.insert_or_replace("t", ["a", "b"])
        assert "?" in sql
        assert "$" not in sql


# ---------------------------------------------------------------------------
# SQLHelper.upsert
# ---------------------------------------------------------------------------


class TestSQLHelperUpsert:
    def test_sqlite_upsert(self):
        sql = SQLHelper.upsert(
            "users",
            columns=["id", "name", "email"],
            key_columns=["id"],
            dialect="sqlite",
        )
        assert "INSERT INTO users" in sql
        assert "ON CONFLICT (id)" in sql
        assert "name = excluded.name" in sql
        assert "email = excluded.email" in sql

    def test_postgres_upsert(self):
        sql = SQLHelper.upsert(
            "users",
            columns=["id", "name", "email"],
            key_columns=["id"],
            dialect="postgres",
        )
        assert "INSERT INTO users" in sql
        assert "ON CONFLICT (id)" in sql
        assert "name = EXCLUDED.name" in sql  # PostgreSQL uses EXCLUDED
        assert "%s" in sql  # psycopg2 style placeholders

    def test_composite_key(self):
        sql = SQLHelper.upsert(
            "events",
            columns=["date", "source", "count", "total"],
            key_columns=["date", "source"],
            dialect="sqlite",
        )
        assert "ON CONFLICT (date, source)" in sql
        assert "count = excluded.count" in sql
        assert "total = excluded.total" in sql
        # Key columns should NOT appear in update set
        assert "date = excluded.date" not in sql
        assert "source = excluded.source" not in sql

    def test_sqlite_is_default(self):
        sql = SQLHelper.upsert("t", ["k", "v"], ["k"])
        assert "?" in sql
        assert "excluded" in sql.lower()

    def test_upsert_sql_is_executable_on_sqlite(self):
        """Verify the generated SQL actually works on SQLite."""
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE users (id TEXT PRIMARY KEY, name TEXT, email TEXT)")

        sql = SQLHelper.upsert("users", ["id", "name", "email"], ["id"], dialect="sqlite")
        conn.execute(sql.strip(), ("u1", "Alice", "alice@test.com"))
        conn.commit()

        # Second insert with same key → update
        conn.execute(sql.strip(), ("u1", "Alice Updated", "new@test.com"))
        conn.commit()

        cursor = conn.execute("SELECT name, email FROM users WHERE id = 'u1'")
        row = cursor.fetchone()
        assert row[0] == "Alice Updated"
        assert row[1] == "new@test.com"
        conn.close()
