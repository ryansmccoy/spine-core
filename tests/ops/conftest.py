"""Shared fixtures for spine.ops tests."""

import sqlite3
from typing import Any

import pytest

from spine.ops.context import OperationContext


class MockConnection:
    """Minimal Connection protocol implementation backed by in-memory SQLite."""

    def __init__(self) -> None:
        self._conn = sqlite3.connect(":memory:")
        self._conn.row_factory = sqlite3.Row
        self._cursor = self._conn.cursor()

    def execute(self, sql: str, params: tuple = ()) -> Any:
        self._cursor.execute(sql, params)
        return self._cursor

    def executemany(self, sql: str, params: list[tuple]) -> Any:
        self._cursor.executemany(sql, params)
        return self._cursor

    def fetchone(self) -> Any:
        return self._cursor.fetchone()

    def fetchall(self) -> list:
        return self._cursor.fetchall()

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    def close(self) -> None:
        self._conn.close()


@pytest.fixture()
def mock_conn() -> MockConnection:
    """In-memory SQLite connection implementing the Connection protocol."""
    conn = MockConnection()
    yield conn
    conn.close()


@pytest.fixture()
def ctx(mock_conn: MockConnection) -> OperationContext:
    """Default OperationContext wired to the mock connection."""
    return OperationContext(conn=mock_conn, caller="test")


@pytest.fixture()
def dry_ctx(mock_conn: MockConnection) -> OperationContext:
    """OperationContext with dry_run=True."""
    return OperationContext(conn=mock_conn, caller="test", dry_run=True)
