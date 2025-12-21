"""Tests for ``spine.ops.quality`` — quality result operations."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from spine.ops.context import OperationContext
from spine.ops.quality import list_quality_results
from spine.ops.requests import ListQualityResultsRequest


@pytest.fixture()
def ctx():
    conn = MagicMock()
    return OperationContext(conn=conn, caller="test")


def _quality_row(**overrides):
    base = {
        "workflow": "ingest",
        "checks_passed": 10,
        "checks_failed": 2,
        "score": 0.8333,
        "run_at": "2026-01-01T00:00:00",
    }
    base.update(overrides)
    return base


class TestListQualityResults:
    @patch("spine.ops.quality._quality_repo")
    def test_success(self, mock_repo_fn, ctx):
        repo = MagicMock()
        repo.aggregate_by_workflow.return_value = ([_quality_row()], 1)
        mock_repo_fn.return_value = repo

        req = ListQualityResultsRequest()
        result = list_quality_results(ctx, req)

        assert result.success is True
        assert result.total == 1
        assert result.data[0].workflow == "ingest"
        assert result.data[0].checks_passed == 10

    @patch("spine.ops.quality._quality_repo")
    def test_empty(self, mock_repo_fn, ctx):
        repo = MagicMock()
        repo.aggregate_by_workflow.return_value = ([], 0)
        mock_repo_fn.return_value = repo

        req = ListQualityResultsRequest()
        result = list_quality_results(ctx, req)

        assert result.success is True
        assert result.total == 0
        assert result.data == []

    @patch("spine.ops.quality._quality_repo")
    def test_error(self, mock_repo_fn, ctx):
        repo = MagicMock()
        repo.aggregate_by_workflow.side_effect = RuntimeError("db down")
        mock_repo_fn.return_value = repo

        req = ListQualityResultsRequest()
        result = list_quality_results(ctx, req)

        assert result.success is False
        assert "INTERNAL" in result.error.code

    @patch("spine.ops.quality._quality_repo")
    def test_row_with_keys_method(self, mock_repo_fn, ctx):
        class RowLike:
            def keys(self):
                return ["workflow", "checks_passed", "checks_failed", "score", "run_at"]

            def __iter__(self):
                for k in self.keys():
                    yield k

            def __getitem__(self, k):
                return _quality_row()[k]

        repo = MagicMock()
        repo.aggregate_by_workflow.return_value = ([RowLike()], 1)
        mock_repo_fn.return_value = repo

        req = ListQualityResultsRequest()
        result = list_quality_results(ctx, req)

        assert result.success is True
        assert result.data[0].checks_passed == 10

    @patch("spine.ops.quality._quality_repo")
    def test_row_tuple_fallback(self, mock_repo_fn, ctx):
        repo = MagicMock()
        repo.aggregate_by_workflow.return_value = ([(123,)], 1)
        mock_repo_fn.return_value = repo

        req = ListQualityResultsRequest()
        result = list_quality_results(ctx, req)

        assert result.success is True
        assert result.data[0].workflow == ""  # fallback empty
