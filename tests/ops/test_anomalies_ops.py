"""Tests for ``spine.ops.anomalies`` — anomaly listing operations."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from spine.ops.context import OperationContext
from spine.ops.anomalies import list_anomalies
from spine.ops.requests import ListAnomaliesRequest


@pytest.fixture()
def ctx():
    conn = MagicMock()
    return OperationContext(conn=conn, caller="test")


def _anomaly_row(**overrides):
    base = {
        "id": "anom_001",
        "workflow": "ingest",
        "metric": "latency_p99",
        "severity": "warning",
        "value": 12.5,
        "threshold": 10.0,
        "detected_at": "2026-01-01T00:00:00",
    }
    base.update(overrides)
    return base


class TestListAnomalies:
    @patch("spine.ops.anomalies._anomaly_repo")
    def test_success(self, mock_repo_fn, ctx):
        repo = MagicMock()
        repo.list_anomalies.return_value = ([_anomaly_row()], 1)
        mock_repo_fn.return_value = repo

        req = ListAnomaliesRequest()
        result = list_anomalies(ctx, req)

        assert result.success is True
        assert result.total == 1
        assert result.data[0].id == "anom_001"
        assert result.data[0].severity == "warning"

    @patch("spine.ops.anomalies._anomaly_repo")
    def test_with_filters(self, mock_repo_fn, ctx):
        repo = MagicMock()
        repo.list_anomalies.return_value = ([], 0)
        mock_repo_fn.return_value = repo

        req = ListAnomaliesRequest(workflow="ingest", severity="critical")
        result = list_anomalies(ctx, req)

        assert result.success is True
        assert result.total == 0

    @patch("spine.ops.anomalies._anomaly_repo")
    def test_error_returns_failure(self, mock_repo_fn, ctx):
        repo = MagicMock()
        repo.list_anomalies.side_effect = RuntimeError("db error")
        mock_repo_fn.return_value = repo

        req = ListAnomaliesRequest()
        result = list_anomalies(ctx, req)

        assert result.success is False
        assert "INTERNAL" in result.error.code

    @patch("spine.ops.anomalies._anomaly_repo")
    def test_row_with_keys_method(self, mock_repo_fn, ctx):
        """Test the hasattr(row, 'keys') branch."""

        class RowLike:
            def keys(self):
                return ["id", "workflow", "metric", "severity", "value", "threshold", "detected_at"]

            def __iter__(self):
                for k in self.keys():
                    yield k

            def __getitem__(self, k):
                return _anomaly_row()[k]

        repo = MagicMock()
        repo.list_anomalies.return_value = ([RowLike()], 1)
        mock_repo_fn.return_value = repo

        req = ListAnomaliesRequest()
        result = list_anomalies(ctx, req)

        assert result.success is True
        assert result.data[0].id == "anom_001"

    @patch("spine.ops.anomalies._anomaly_repo")
    def test_row_fallback_tuple(self, mock_repo_fn, ctx):
        """Test the fallback branch with non-dict non-keys row."""
        repo = MagicMock()
        repo.list_anomalies.return_value = ([("just_a_tuple",)], 1)
        mock_repo_fn.return_value = repo

        req = ListAnomaliesRequest()
        result = list_anomalies(ctx, req)

        assert result.success is True
        # Fallback creates an empty AnomalySummary
        assert result.data[0].id == ""
