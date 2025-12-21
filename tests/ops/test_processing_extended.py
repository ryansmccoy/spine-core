"""Extended tests for spine.ops.processing module.

Covers list_manifest_entries, get_manifest_entry, list_rejects,
count_rejects_by_reason, list_work_items, claim_work_item,
complete_work_item, fail_work_item, cancel_work_item,
and retry_failed_work_items.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from spine.ops.context import OperationContext
from spine.ops.processing import (
    cancel_work_item,
    claim_work_item,
    complete_work_item,
    count_rejects_by_reason,
    fail_work_item,
    get_manifest_entry,
    list_manifest_entries,
    list_rejects,
    list_work_items,
    retry_failed_work_items,
)
from spine.ops.requests import (
    ClaimWorkItemRequest,
    ListManifestEntriesRequest,
    ListRejectsRequest,
    ListWorkItemsRequest,
)


def _ctx(dry_run: bool = False) -> OperationContext:
    conn = MagicMock()
    return OperationContext(conn=conn, dry_run=dry_run, request_id="test-req-1")


# ------------------------------------------------------------------ #
# Manifest entries
# ------------------------------------------------------------------ #


class TestListManifestEntries:
    @patch("spine.ops.processing.ManifestRepository")
    def test_no_request(self, MockRepo):
        repo = MockRepo.return_value
        repo.list_entries.return_value = (
            [{"domain": "equity", "partition_key": "2024-01", "stage": "raw"}],
            1,
        )
        ctx = _ctx()
        result = list_manifest_entries(ctx)
        assert result.success is True
        assert result.total == 1
        assert result.data[0].domain == "equity"

    @patch("spine.ops.processing.ManifestRepository")
    def test_with_filters(self, MockRepo):
        repo = MockRepo.return_value
        repo.list_entries.return_value = ([], 0)
        ctx = _ctx()
        req = ListManifestEntriesRequest(domain="equity", limit=10, offset=0)
        result = list_manifest_entries(ctx, req)
        assert result.success is True
        assert result.total == 0

    @patch("spine.ops.processing.ManifestRepository")
    def test_exception(self, MockRepo):
        repo = MockRepo.return_value
        repo.list_entries.side_effect = RuntimeError("table missing")
        ctx = _ctx()
        result = list_manifest_entries(ctx)
        # Should return empty, not raise
        assert result.success is True
        assert result.total == 0


class TestGetManifestEntry:
    def test_missing_fields(self):
        ctx = _ctx()
        result = get_manifest_entry(ctx, "", "2024-01", "raw")
        assert result.success is False
        assert "required" in result.error.message.lower()

    @patch("spine.ops.processing.ManifestRepository")
    def test_found(self, MockRepo):
        repo = MockRepo.return_value
        repo.get_entry.return_value = {
            "domain": "equity",
            "partition_key": "2024-01",
            "stage": "raw",
            "row_count": 500,
        }
        ctx = _ctx()
        result = get_manifest_entry(ctx, "equity", "2024-01", "raw")
        assert result.success is True
        assert result.data.domain == "equity"
        assert result.data.row_count == 500

    @patch("spine.ops.processing.ManifestRepository")
    def test_not_found(self, MockRepo):
        repo = MockRepo.return_value
        repo.get_entry.return_value = None
        ctx = _ctx()
        result = get_manifest_entry(ctx, "equity", "2024-01", "raw")
        assert result.success is False
        assert "NOT_FOUND" in result.error.code


# ------------------------------------------------------------------ #
# Rejects
# ------------------------------------------------------------------ #


class TestListRejects:
    @patch("spine.ops.processing.RejectRepository")
    def test_no_request(self, MockRepo):
        repo = MockRepo.return_value
        repo.list_rejects.return_value = (
            [{"domain": "equity", "partition_key": "2024-01", "stage": "raw",
              "reason_code": "SCHEMA_MISMATCH", "execution_id": "ex-1"}],
            1,
        )
        ctx = _ctx()
        result = list_rejects(ctx)
        assert result.success is True
        assert result.total == 1

    @patch("spine.ops.processing.RejectRepository")
    def test_exception(self, MockRepo):
        repo = MockRepo.return_value
        repo.list_rejects.side_effect = RuntimeError("no table")
        ctx = _ctx()
        result = list_rejects(ctx)
        assert result.success is True
        assert result.total == 0


class TestCountRejectsByReason:
    @patch("spine.ops.processing.RejectRepository")
    def test_returns_counts(self, MockRepo):
        repo = MockRepo.return_value
        repo.count_by_reason.return_value = [
            {"reason_code": "SCHEMA_MISMATCH", "cnt": 42},
            {"reason_code": "NULL_KEY", "cnt": 7},
        ]
        ctx = _ctx()
        result = count_rejects_by_reason(ctx, domain="equity")
        assert result.success is True
        assert len(result.data) == 2

    @patch("spine.ops.processing.RejectRepository")
    def test_exception(self, MockRepo):
        repo = MockRepo.return_value
        repo.count_by_reason.side_effect = RuntimeError("db error")
        ctx = _ctx()
        result = count_rejects_by_reason(ctx)
        assert result.success is False
        assert "INTERNAL" in result.error.code


# ------------------------------------------------------------------ #
# Work Items
# ------------------------------------------------------------------ #


class TestListWorkItems:
    @patch("spine.ops.processing.WorkItemRepository")
    def test_no_request(self, MockRepo):
        repo = MockRepo.return_value
        repo.list_items.return_value = (
            [{"id": 1, "domain": "equity", "workflow": "daily_ingest",
              "partition_key": "2024-01", "state": "PENDING"}],
            1,
        )
        ctx = _ctx()
        result = list_work_items(ctx)
        assert result.success is True
        assert result.total == 1


class TestClaimWorkItem:
    def test_missing_fields(self):
        ctx = _ctx()
        req = ClaimWorkItemRequest(item_id=0, worker_id="")
        result = claim_work_item(ctx, req)
        assert result.success is False

    def test_dry_run(self):
        ctx = _ctx(dry_run=True)
        req = ClaimWorkItemRequest(item_id=42, worker_id="worker-1")
        result = claim_work_item(ctx, req)
        assert result.success is True
        assert result.data.state == "RUNNING"

    @patch("spine.ops.processing.WorkItemRepository")
    def test_not_found(self, MockRepo):
        repo = MockRepo.return_value
        repo.claim.return_value = None
        ctx = _ctx()
        ctx.conn.commit = MagicMock()
        req = ClaimWorkItemRequest(item_id=99, worker_id="worker-1")
        result = claim_work_item(ctx, req)
        assert result.success is False
        assert "NOT_FOUND" in result.error.code


class TestCompleteWorkItem:
    def test_missing_id(self):
        ctx = _ctx()
        result = complete_work_item(ctx, 0)
        assert result.success is False

    def test_dry_run(self):
        ctx = _ctx(dry_run=True)
        result = complete_work_item(ctx, 42)
        assert result.success is True

    @patch("spine.ops.processing.WorkItemRepository")
    def test_success(self, MockRepo):
        repo = MockRepo.return_value
        ctx = _ctx()
        ctx.conn.commit = MagicMock()
        result = complete_work_item(ctx, 42, execution_id="exec-1")
        assert result.success is True


class TestFailWorkItem:
    def test_missing_id(self):
        ctx = _ctx()
        result = fail_work_item(ctx, 0, "some error")
        assert result.success is False

    def test_dry_run(self):
        ctx = _ctx(dry_run=True)
        result = fail_work_item(ctx, 42, "timeout")
        assert result.success is True

    @patch("spine.ops.processing.WorkItemRepository")
    def test_retry_wait(self, MockRepo):
        repo = MockRepo.return_value
        repo.get_by_id.return_value = {"attempt_count": 1, "max_attempts": 3}
        ctx = _ctx()
        ctx.conn.commit = MagicMock()
        result = fail_work_item(ctx, 42, "timeout")
        assert result.success is True
        repo.fail.assert_called_once()
        # state should be RETRY_WAIT since attempt_count < max_attempts
        call_args = repo.fail.call_args
        assert call_args[1]["new_state"] == "RETRY_WAIT"

    @patch("spine.ops.processing.WorkItemRepository")
    def test_final_failure(self, MockRepo):
        repo = MockRepo.return_value
        repo.get_by_id.return_value = {"attempt_count": 3, "max_attempts": 3}
        ctx = _ctx()
        ctx.conn.commit = MagicMock()
        result = fail_work_item(ctx, 42, "timeout")
        assert result.success is True
        call_args = repo.fail.call_args
        assert call_args[1]["new_state"] == "FAILED"


class TestCancelWorkItem:
    def test_missing_id(self):
        ctx = _ctx()
        result = cancel_work_item(ctx, 0)
        assert result.success is False

    def test_dry_run(self):
        ctx = _ctx(dry_run=True)
        result = cancel_work_item(ctx, 42)
        assert result.success is True

    @patch("spine.ops.processing.WorkItemRepository")
    def test_success(self, MockRepo):
        ctx = _ctx()
        ctx.conn.commit = MagicMock()
        result = cancel_work_item(ctx, 42)
        assert result.success is True


class TestRetryFailedWorkItems:
    @patch("spine.ops.processing.WorkItemRepository")
    def test_dry_run(self, MockRepo):
        repo = MockRepo.return_value
        repo.list_items.return_value = ([], 5)
        ctx = _ctx(dry_run=True)
        result = retry_failed_work_items(ctx, domain="equity")
        assert result.success is True
        assert result.data == 5

    @patch("spine.ops.processing.WorkItemRepository")
    def test_actual_retry(self, MockRepo):
        repo = MockRepo.return_value
        repo.retry_failed.return_value = 3
        ctx = _ctx()
        ctx.conn.commit = MagicMock()
        result = retry_failed_work_items(ctx, domain="equity")
        assert result.success is True
        assert result.data == 3
