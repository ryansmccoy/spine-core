"""Tests for ``spine.ops.sources`` — source CRUD operations via repository pattern."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from spine.ops.context import OperationContext
from spine.ops.sources import (
    delete_source,
    enable_source,
    disable_source,
    get_source,
    list_sources,
    register_source,
    invalidate_source_cache,
    list_source_fetches,
    list_source_cache,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def ctx():
    """Minimal OperationContext with a mock conn."""
    conn = MagicMock()
    return OperationContext(conn=conn, caller="test")


@pytest.fixture()
def dry_ctx():
    """OperationContext with dry_run=True."""
    conn = MagicMock()
    return OperationContext(conn=conn, caller="test", dry_run=True)


def _source_row(**overrides):
    """Build a minimal source row dict."""
    base = {
        "id": "src_abc123",
        "name": "test-source",
        "source_type": "api",
        "domain": "finance",
        "url": "https://example.com",
        "enabled": 1,
        "tags": None,
        "config": None,
        "fetch_count": 5,
        "error_count": 0,
        "last_fetched_at": "2026-01-01T00:00:00",
        "created_at": "2026-01-01T00:00:00",
        "updated_at": "2026-01-01T00:00:00",
        "created_by": "test",
        "description": "Test source",
        "schedule": None,
        "auth_type": None,
        "auth_config": None,
        "headers": None,
        "retry_policy": None,
        "timeout_seconds": 30,
        "rate_limit": None,
        "last_error": None,
        "last_error_at": None,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# list_sources
# ---------------------------------------------------------------------------

class TestListSources:
    @patch("spine.ops.sources._source_repo")
    def test_list_returns_paged_result(self, mock_repo_factory, ctx):
        repo = MagicMock()
        repo.list_sources.return_value = ([_source_row()], 1)
        mock_repo_factory.return_value = repo

        from spine.ops.sources import ListSourcesRequest
        result = list_sources(ctx, ListSourcesRequest(limit=10, offset=0))
        assert result.success is True
        assert result.total == 1

    @patch("spine.ops.sources._source_repo")
    def test_list_empty(self, mock_repo_factory, ctx):
        repo = MagicMock()
        repo.list_sources.return_value = ([], 0)
        mock_repo_factory.return_value = repo

        from spine.ops.sources import ListSourcesRequest
        result = list_sources(ctx, ListSourcesRequest())
        assert result.success is True
        assert result.total == 0

    @patch("spine.ops.sources._source_repo")
    def test_list_handles_exception(self, mock_repo_factory, ctx):
        repo = MagicMock()
        repo.list_sources.side_effect = Exception("DB error")
        mock_repo_factory.return_value = repo

        from spine.ops.sources import ListSourcesRequest
        result = list_sources(ctx, ListSourcesRequest())
        assert result.success is False


# ---------------------------------------------------------------------------
# get_source
# ---------------------------------------------------------------------------

class TestGetSource:
    @patch("spine.ops.sources._source_repo")
    def test_get_existing(self, mock_repo_factory, ctx):
        repo = MagicMock()
        repo.get_source.return_value = _source_row()
        mock_repo_factory.return_value = repo

        result = get_source(ctx, "src_abc123")
        assert result.success is True

    @patch("spine.ops.sources._source_repo")
    def test_get_not_found(self, mock_repo_factory, ctx):
        repo = MagicMock()
        repo.get_source.return_value = None
        mock_repo_factory.return_value = repo

        result = get_source(ctx, "src_missing")
        assert result.success is False


# ---------------------------------------------------------------------------
# register_source
# ---------------------------------------------------------------------------

class TestRegisterSource:
    def test_dry_run(self, dry_ctx):
        from spine.ops.sources import CreateSourceRequest
        result = register_source(dry_ctx, CreateSourceRequest(name="test", source_type="http"))
        assert result.success is True
        assert result.data.get("dry_run") is True

    @patch("spine.ops.sources._source_repo")
    def test_register_success(self, mock_repo_factory, ctx):
        repo = MagicMock()
        mock_repo_factory.return_value = repo

        from spine.ops.sources import CreateSourceRequest
        result = register_source(ctx, CreateSourceRequest(name="new-src", source_type="http"))
        assert result.success is True
        repo.create_source.assert_called_once()


# ---------------------------------------------------------------------------
# delete_source
# ---------------------------------------------------------------------------

class TestDeleteSource:
    def test_dry_run(self, dry_ctx):
        result = delete_source(dry_ctx, "src_abc")
        assert result.success is True
        assert result.data.get("dry_run") is True

    @patch("spine.ops.sources._source_repo")
    def test_delete_success(self, mock_repo_factory, ctx):
        repo = MagicMock()
        repo.delete_source.return_value = True
        mock_repo_factory.return_value = repo
        result = delete_source(ctx, "src_abc")
        assert result.success is True

    @patch("spine.ops.sources._source_repo")
    def test_delete_exception(self, mock_repo_factory, ctx):
        repo = MagicMock()
        repo.delete_source.side_effect = Exception("DB error")
        mock_repo_factory.return_value = repo
        result = delete_source(ctx, "src_missing")
        assert result.success is False


# ---------------------------------------------------------------------------
# enable / disable
# ---------------------------------------------------------------------------

class TestEnableDisable:
    @patch("spine.ops.sources._source_repo")
    def test_enable_success(self, mock_repo_factory, ctx):
        repo = MagicMock()
        repo.update_source.return_value = True
        mock_repo_factory.return_value = repo
        result = enable_source(ctx, "src_abc")
        assert result.success is True

    @patch("spine.ops.sources._source_repo")
    def test_disable_success(self, mock_repo_factory, ctx):
        repo = MagicMock()
        repo.update_source.return_value = True
        mock_repo_factory.return_value = repo
        result = disable_source(ctx, "src_abc")
        assert result.success is True


# ---------------------------------------------------------------------------
# source fetches / cache
# ---------------------------------------------------------------------------

class TestFetchesAndCache:
    @patch("spine.ops.sources._source_repo")
    def test_list_fetches(self, mock_repo_factory, ctx):
        repo = MagicMock()
        repo.list_fetches.return_value = ([], 0)
        mock_repo_factory.return_value = repo

        from spine.ops.sources import ListSourceFetchesRequest
        result = list_source_fetches(ctx, ListSourceFetchesRequest())
        assert result.success is True

    @patch("spine.ops.sources._source_repo")
    def test_list_cache(self, mock_repo_factory, ctx):
        repo = MagicMock()
        repo.list_cache.return_value = ([], 0)
        mock_repo_factory.return_value = repo

        result = list_source_cache(ctx)
        assert result.success is True

    @patch("spine.ops.sources._source_repo")
    def test_invalidate_cache_dry_run(self, mock_repo_factory, dry_ctx):
        repo = MagicMock()
        repo.list_cache.return_value = ([], 0)
        mock_repo_factory.return_value = repo
        result = invalidate_source_cache(dry_ctx, "src_abc")
        assert result.success is True
