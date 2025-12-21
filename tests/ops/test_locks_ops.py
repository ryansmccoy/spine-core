"""Tests for ``spine.ops.locks`` — lock management operations."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from spine.ops.context import OperationContext
from spine.ops.locks import (
    list_locks,
    list_schedule_locks,
    release_lock,
    release_schedule_lock,
)


@pytest.fixture()
def ctx():
    conn = MagicMock()
    return OperationContext(conn=conn, caller="test")


@pytest.fixture()
def dry_ctx():
    conn = MagicMock()
    return OperationContext(conn=conn, caller="test", dry_run=True)


class TestListLocks:
    @patch("spine.ops.locks._lock_repo")
    def test_success(self, mock_repo_fn, ctx):
        repo = MagicMock()
        repo.list_locks.return_value = [
            {"lock_key": "wf:ingest", "owner": "worker-1", "acquired_at": None, "expires_at": None},
        ]
        mock_repo_fn.return_value = repo

        result = list_locks(ctx)
        assert result.success is True
        assert len(result.data) == 1
        assert result.data[0].lock_key == "wf:ingest"

    @patch("spine.ops.locks._lock_repo")
    def test_error_returns_empty(self, mock_repo_fn, ctx):
        repo = MagicMock()
        repo.list_locks.side_effect = RuntimeError("no table")
        mock_repo_fn.return_value = repo

        result = list_locks(ctx)
        assert result.success is True  # gracefully returns empty
        assert result.data == []

    @patch("spine.ops.locks._lock_repo")
    def test_row_with_keys(self, mock_repo_fn, ctx):
        class RowLike:
            def keys(self):
                return ["lock_key", "owner", "acquired_at", "expires_at"]

            def __iter__(self):
                for k in self.keys():
                    yield k

            def __getitem__(self, k):
                return {"lock_key": "k1", "owner": "o1", "acquired_at": None, "expires_at": None}[k]

        repo = MagicMock()
        repo.list_locks.return_value = [RowLike()]
        mock_repo_fn.return_value = repo

        result = list_locks(ctx)
        assert result.data[0].lock_key == "k1"

    @patch("spine.ops.locks._lock_repo")
    def test_row_tuple_fallback(self, mock_repo_fn, ctx):
        repo = MagicMock()
        repo.list_locks.return_value = [("key-1",)]
        mock_repo_fn.return_value = repo

        result = list_locks(ctx)
        assert result.data[0].lock_key == "key-1"


class TestReleaseLock:
    @patch("spine.ops.locks._lock_repo")
    def test_success(self, mock_repo_fn, ctx):
        repo = MagicMock()
        mock_repo_fn.return_value = repo

        result = release_lock(ctx, "my-lock")
        assert result.success is True
        repo.release_lock.assert_called_once_with("my-lock")

    def test_empty_key_fails(self, ctx):
        result = release_lock(ctx, "")
        assert result.success is False
        assert "required" in result.error.message.lower()

    def test_dry_run(self, dry_ctx):
        result = release_lock(dry_ctx, "my-lock")
        assert result.success is True

    @patch("spine.ops.locks._lock_repo")
    def test_error(self, mock_repo_fn, ctx):
        repo = MagicMock()
        repo.release_lock.side_effect = RuntimeError("db err")
        mock_repo_fn.return_value = repo

        result = release_lock(ctx, "my-lock")
        assert result.success is False


class TestListScheduleLocks:
    @patch("spine.ops.locks._lock_repo")
    def test_success(self, mock_repo_fn, ctx):
        repo = MagicMock()
        repo.list_schedule_locks.return_value = (
            [{"schedule_id": "s1", "locked_by": "w1", "locked_at": None, "expires_at": None}],
            1,
        )
        mock_repo_fn.return_value = repo

        result = list_schedule_locks(ctx)
        assert result.success is True
        assert result.data[0].schedule_id == "s1"

    @patch("spine.ops.locks._lock_repo")
    def test_with_request(self, mock_repo_fn, ctx):
        from spine.ops.requests import ListScheduleLocksRequest

        repo = MagicMock()
        repo.list_schedule_locks.return_value = ([], 0)
        mock_repo_fn.return_value = repo

        req = ListScheduleLocksRequest(limit=10, offset=5)
        result = list_schedule_locks(ctx, req)
        assert result.success is True

    @patch("spine.ops.locks._lock_repo")
    def test_error_returns_empty(self, mock_repo_fn, ctx):
        repo = MagicMock()
        repo.list_schedule_locks.side_effect = RuntimeError("no table")
        mock_repo_fn.return_value = repo

        result = list_schedule_locks(ctx)
        assert result.success is True
        assert result.data == []


class TestReleaseScheduleLock:
    @patch("spine.ops.locks._lock_repo")
    def test_success(self, mock_repo_fn, ctx):
        repo = MagicMock()
        mock_repo_fn.return_value = repo

        result = release_schedule_lock(ctx, "sched-1")
        assert result.success is True

    def test_empty_id_fails(self, ctx):
        result = release_schedule_lock(ctx, "")
        assert result.success is False

    def test_dry_run(self, dry_ctx):
        result = release_schedule_lock(dry_ctx, "sched-1")
        assert result.success is True

    @patch("spine.ops.locks._lock_repo")
    def test_error(self, mock_repo_fn, ctx):
        repo = MagicMock()
        repo.release_schedule_lock.side_effect = RuntimeError("err")
        mock_repo_fn.return_value = repo

        result = release_schedule_lock(ctx, "sched-1")
        assert result.success is False
