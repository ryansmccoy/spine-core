"""Tests for the BaseRepository class."""

from __future__ import annotations

import sqlite3

import pytest

from spine.core.dialect import SQLiteDialect
from spine.core.repository import BaseRepository


@pytest.fixture
def conn() -> sqlite3.Connection:
    """In-memory SQLite connection with a test table."""
    c = sqlite3.connect(":memory:")
    c.execute(
        """
        CREATE TABLE items (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            value INTEGER
        )
    """
    )
    c.commit()
    return c


@pytest.fixture
def repo(conn: sqlite3.Connection) -> BaseRepository:
    return BaseRepository(conn, SQLiteDialect())


class TestPh:
    def test_single(self, repo: BaseRepository) -> None:
        assert repo.ph(1) == "?"

    def test_multiple(self, repo: BaseRepository) -> None:
        assert repo.ph(3) == "?, ?, ?"


class TestExecute:
    def test_execute(self, repo: BaseRepository) -> None:
        repo.execute("INSERT INTO items (id, name, value) VALUES (?, ?, ?)", ("1", "a", 10))
        repo.commit()
        row = repo.query_one("SELECT * FROM items WHERE id = ?", ("1",))
        assert row is not None
        assert row["name"] == "a"


class TestQuery:
    def test_query_returns_dicts(self, repo: BaseRepository) -> None:
        repo.execute("INSERT INTO items (id, name, value) VALUES (?, ?, ?)", ("1", "a", 10))
        repo.execute("INSERT INTO items (id, name, value) VALUES (?, ?, ?)", ("2", "b", 20))
        repo.commit()

        rows = repo.query("SELECT * FROM items ORDER BY id")
        assert len(rows) == 2
        assert rows[0]["id"] == "1"
        assert rows[1]["name"] == "b"

    def test_query_empty(self, repo: BaseRepository) -> None:
        rows = repo.query("SELECT * FROM items")
        assert rows == []


class TestQueryOne:
    def test_found(self, repo: BaseRepository) -> None:
        repo.execute("INSERT INTO items (id, name, value) VALUES (?, ?, ?)", ("1", "a", 10))
        repo.commit()
        row = repo.query_one("SELECT * FROM items WHERE id = ?", ("1",))
        assert row is not None
        assert row["value"] == 10

    def test_not_found(self, repo: BaseRepository) -> None:
        row = repo.query_one("SELECT * FROM items WHERE id = ?", ("999",))
        assert row is None


class TestInsert:
    def test_insert(self, repo: BaseRepository) -> None:
        repo.insert("items", {"id": "1", "name": "x", "value": 42})
        repo.commit()
        row = repo.query_one("SELECT * FROM items WHERE id = ?", ("1",))
        assert row["name"] == "x"
        assert row["value"] == 42

    def test_insert_many(self, repo: BaseRepository) -> None:
        repo.insert_many(
            "items",
            [
                {"id": "1", "name": "a", "value": 1},
                {"id": "2", "name": "b", "value": 2},
                {"id": "3", "name": "c", "value": 3},
            ],
        )
        repo.commit()
        rows = repo.query("SELECT * FROM items ORDER BY id")
        assert len(rows) == 3
