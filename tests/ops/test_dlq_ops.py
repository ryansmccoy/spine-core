"""Tests for ``spine.ops.dlq`` — dead letter queue operations."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from spine.ops.context import OperationContext
from spine.ops.dlq import list_dead_letters, replay_dead_letter
from spine.ops.requests import ListDeadLettersRequest, ReplayDeadLetterRequest


@pytest.fixture()
def ctx():
    conn = MagicMock()
    return OperationContext(conn=conn, caller="test")


@pytest.fixture()
def dry_ctx():
    conn = MagicMock()
    return OperationContext(conn=conn, caller="test", dry_run=True)


def _dlq_row(**overrides):
    base = {
        "id": "dlq_001",
        "workflow": "ingest",
        "error": "timeout exceeded",
        "created_at": "2026-01-01T00:00:00",
        "replay_count": 0,
    }
    base.update(overrides)
    return base


class TestListDeadLetters:
    @patch("spine.ops.dlq._dlq_repo")
    def test_success(self, mock_repo_fn, ctx):
        repo = MagicMock()
        repo.list_dead_letters.return_value = ([_dlq_row()], 1)
        mock_repo_fn.return_value = repo

        req = ListDeadLettersRequest()
        result = list_dead_letters(ctx, req)

        assert result.success is True
        assert result.total == 1
        assert len(result.data) == 1
        assert result.data[0].id == "dlq_001"

    @patch("spine.ops.dlq._dlq_repo")
    def test_with_workflow_filter(self, mock_repo_fn, ctx):
        repo = MagicMock()
        repo.list_dead_letters.return_value = ([], 0)
        mock_repo_fn.return_value = repo

        req = ListDeadLettersRequest(workflow="ingest")
        result = list_dead_letters(ctx, req)

        assert result.success is True
        repo.list_dead_letters.assert_called_once()

    @patch("spine.ops.dlq._dlq_repo")
    def test_error_returns_failure(self, mock_repo_fn, ctx):
        repo = MagicMock()
        repo.list_dead_letters.side_effect = RuntimeError("db down")
        mock_repo_fn.return_value = repo

        req = ListDeadLettersRequest()
        result = list_dead_letters(ctx, req)

        assert result.success is False
        assert result.error is not None


class TestReplayDeadLetter:
    @patch("spine.ops.dlq._dlq_repo")
    def test_success(self, mock_repo_fn, ctx):
        repo = MagicMock()
        repo.exists.return_value = True
        mock_repo_fn.return_value = repo

        req = ReplayDeadLetterRequest(dead_letter_id="dlq_001")
        result = replay_dead_letter(ctx, req)

        assert result.success is True
        repo.increment_replay.assert_called_once_with("dlq_001")
        ctx.conn.commit.assert_called_once()

    def test_missing_id_fails(self, ctx):
        req = ReplayDeadLetterRequest(dead_letter_id="")
        result = replay_dead_letter(ctx, req)

        assert result.success is False
        assert "required" in result.error.message.lower()

    def test_dry_run_skips(self, dry_ctx):
        req = ReplayDeadLetterRequest(dead_letter_id="dlq_001")
        result = replay_dead_letter(dry_ctx, req)

        assert result.success is True

    @patch("spine.ops.dlq._dlq_repo")
    def test_not_found(self, mock_repo_fn, ctx):
        repo = MagicMock()
        repo.exists.return_value = False
        mock_repo_fn.return_value = repo

        req = ReplayDeadLetterRequest(dead_letter_id="missing")
        result = replay_dead_letter(ctx, req)

        assert result.success is False
        assert "not found" in result.error.message.lower()

    @patch("spine.ops.dlq._dlq_repo")
    def test_error(self, mock_repo_fn, ctx):
        repo = MagicMock()
        repo.exists.side_effect = RuntimeError("db error")
        mock_repo_fn.return_value = repo

        req = ReplayDeadLetterRequest(dead_letter_id="dlq_001")
        result = replay_dead_letter(ctx, req)

        assert result.success is False
