"""Tests for ``spine.ops.sources`` — error handling branches.

Uses monkeypatch for proper mock isolation (no cross-test state leakage).
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from spine.ops.context import OperationContext
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
)
from spine.ops.sources import test_database_connection as _test_db_conn


@pytest.fixture()
def ctx():
    return OperationContext(conn=MagicMock(), caller="test")


def _repo_returning(**overrides) -> MagicMock:
    """Return a mock repo whose specified methods raise RuntimeError."""
    mock = MagicMock()
    for method, effect in overrides.items():
        getattr(mock, method).side_effect = effect
    return mock


class TestSourcesErrorPaths:
    """Cover the except branches (logger.exception + fail return) for every op."""

    def test_list_sources_error(self, ctx, monkeypatch):
        repo = _repo_returning(list_sources=RuntimeError("db"))
        monkeypatch.setattr("spine.ops.sources._source_repo", lambda _: repo)
        from spine.ops.requests import ListSourcesRequest

        result = list_sources(ctx, ListSourcesRequest())
        assert result.success is False

    def test_get_source_error(self, ctx, monkeypatch):
        repo = _repo_returning(get_source=RuntimeError("db"))
        monkeypatch.setattr("spine.ops.sources._source_repo", lambda _: repo)
        result = get_source(ctx, "s1")
        assert result.success is False

    def test_register_source_error(self, ctx, monkeypatch):
        repo = _repo_returning(create_source=RuntimeError("db"))
        monkeypatch.setattr("spine.ops.sources._source_repo", lambda _: repo)
        from spine.ops.requests import CreateSourceRequest

        result = register_source(ctx, CreateSourceRequest(name="x", source_type="file"))
        assert result.success is False

    def test_delete_source_error(self, ctx, monkeypatch):
        repo = _repo_returning(delete_source=RuntimeError("db"))
        monkeypatch.setattr("spine.ops.sources._source_repo", lambda _: repo)
        result = delete_source(ctx, "s1")
        assert result.success is False

    def test_enable_source_error(self, ctx, monkeypatch):
        repo = _repo_returning(set_enabled=RuntimeError("db"))
        monkeypatch.setattr("spine.ops.sources._source_repo", lambda _: repo)
        result = enable_source(ctx, "s1")
        assert result.success is False

    def test_disable_source_error(self, ctx, monkeypatch):
        repo = _repo_returning(set_enabled=RuntimeError("db"))
        monkeypatch.setattr("spine.ops.sources._source_repo", lambda _: repo)
        result = disable_source(ctx, "s1")
        assert result.success is False

    def test_list_source_fetches_error(self, ctx, monkeypatch):
        repo = _repo_returning(list_fetches=RuntimeError("db"))
        monkeypatch.setattr("spine.ops.sources._source_repo", lambda _: repo)
        from spine.ops.requests import ListSourceFetchesRequest

        result = list_source_fetches(ctx, ListSourceFetchesRequest(source_id="s1"))
        assert result.success is False

    def test_list_source_cache_error(self, ctx, monkeypatch):
        repo = _repo_returning(list_cache=RuntimeError("db"))
        monkeypatch.setattr("spine.ops.sources._source_repo", lambda _: repo)
        result = list_source_cache(ctx, "s1")
        assert result.success is False

    def test_invalidate_source_cache_error(self, ctx, monkeypatch):
        repo = _repo_returning(invalidate_cache=RuntimeError("db"))
        monkeypatch.setattr("spine.ops.sources._source_repo", lambda _: repo)
        result = invalidate_source_cache(ctx, "s1")
        assert result.success is False

    def test_list_database_connections_error(self, ctx, monkeypatch):
        repo = _repo_returning(list_db_connections=RuntimeError("db"))
        monkeypatch.setattr("spine.ops.sources._source_repo", lambda _: repo)
        from spine.ops.requests import ListDatabaseConnectionsRequest

        result = list_database_connections(ctx, ListDatabaseConnectionsRequest())
        assert result.success is False

    def test_register_database_connection_error(self, ctx, monkeypatch):
        repo = _repo_returning(create_db_connection=RuntimeError("db"))
        monkeypatch.setattr("spine.ops.sources._source_repo", lambda _: repo)
        from spine.ops.requests import CreateDatabaseConnectionRequest

        result = register_database_connection(
            ctx, CreateDatabaseConnectionRequest(name="x", dialect="postgres", host="localhost")
        )
        assert result.success is False

    def test_delete_database_connection_error(self, ctx, monkeypatch):
        repo = _repo_returning(delete_db_connection=RuntimeError("db"))
        monkeypatch.setattr("spine.ops.sources._source_repo", lambda _: repo)
        result = delete_database_connection(ctx, "c1")
        assert result.success is False

    def test_test_database_connection_error(self, ctx, monkeypatch):
        repo = _repo_returning(get_db_connection=RuntimeError("db"))
        monkeypatch.setattr("spine.ops.sources._source_repo", lambda _: repo)
        result = _test_db_conn(ctx, "c1")
        assert result.success is False


class TestSourcesRowConverters:
    """Cover _row_to_source_summary tuple fallback."""

    def test_list_sources_tuple_rows(self, ctx, monkeypatch):
        from spine.ops.requests import ListSourcesRequest

        repo = MagicMock()
        repo.list_sources.return_value = (
            [("s1", "src", "file", "{}", "fin", 1, "2024-01-01", "2024-01-01")], 1
        )
        monkeypatch.setattr("spine.ops.sources._source_repo", lambda _: repo)
        result = list_sources(ctx, ListSourcesRequest())
        assert result.success is True
