"""Tests for spine.ops.processing — manifest, rejects, and work item operations."""

import pytest

from spine.core.schema_loader import apply_all_schemas
from spine.ops.database import initialize_database
from spine.ops.processing import (
    claim_work_item,
    cancel_work_item,
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


# ------------------------------------------------------------------ #
# Manifest Test Helpers
# ------------------------------------------------------------------ #


def _insert_manifest(
    ctx,
    domain="finance",
    partition_key="2026-01",
    stage="bronze",
    stage_rank=1,
    row_count=1000,
    execution_id="exec_001",
):
    """Insert a manifest entry row."""
    ctx.conn.execute(
        """
        INSERT INTO core_manifest (
            domain, partition_key, stage, stage_rank, row_count,
            execution_id, batch_id, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
        """,
        (domain, partition_key, stage, stage_rank, row_count, execution_id, "batch_001"),
    )
    ctx.conn.commit()


def _insert_reject(
    ctx,
    domain="finance",
    partition_key="2026-01",
    stage="bronze",
    reason_code="INVALID_DATE",
    reason_detail="Date field is null",
    execution_id="exec_001",
):
    """Insert a reject row."""
    ctx.conn.execute(
        """
        INSERT INTO core_rejects (
            domain, partition_key, stage, reason_code, reason_detail,
            record_key, source_locator, line_number, execution_id, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        """,
        (domain, partition_key, stage, reason_code, reason_detail,
         "rec_001", "file://data.csv", 42, execution_id),
    )
    ctx.conn.commit()


def _insert_work_item(
    ctx,
    item_id=1,
    domain="finance",
    workflow="ingest",
    partition_key="2026-01",
    state="PENDING",
    priority=100,
):
    """Insert a work item row."""
    ctx.conn.execute(
        """
        INSERT INTO core_work_items (
            id, domain, workflow, partition_key, state, priority,
            attempt_count, max_attempts, created_at, updated_at, desired_at
        ) VALUES (?, ?, ?, ?, ?, ?, 0, 3, datetime('now'), datetime('now'), datetime('now'))
        """,
        (item_id, domain, workflow, partition_key, state, priority),
    )
    ctx.conn.commit()


# ------------------------------------------------------------------ #
# List Manifest Entries Tests
# ------------------------------------------------------------------ #


class TestListManifestEntries:
    def test_empty(self, ctx):
        initialize_database(ctx)
        result = list_manifest_entries(ctx, ListManifestEntriesRequest())
        assert result.success is True
        assert result.data == []
        assert result.total == 0

    def test_with_data(self, ctx):
        initialize_database(ctx)
        _insert_manifest(ctx)
        result = list_manifest_entries(ctx, ListManifestEntriesRequest())
        assert result.success is True
        assert result.total == 1
        assert len(result.data) == 1
        assert result.data[0].domain == "finance"
        assert result.data[0].partition_key == "2026-01"
        assert result.data[0].stage == "bronze"

    def test_filter_by_domain(self, ctx):
        initialize_database(ctx)
        _insert_manifest(ctx, domain="finance")
        _insert_manifest(ctx, domain="ops", partition_key="2026-02")

        result = list_manifest_entries(ctx, ListManifestEntriesRequest(domain="ops"))
        assert result.success is True
        assert result.total == 1
        assert result.data[0].domain == "ops"

    def test_filter_by_stage(self, ctx):
        initialize_database(ctx)
        _insert_manifest(ctx, stage="bronze")
        _insert_manifest(ctx, stage="silver", partition_key="2026-02")

        result = list_manifest_entries(ctx, ListManifestEntriesRequest(stage="silver"))
        assert result.success is True
        assert result.total == 1
        assert result.data[0].stage == "silver"

    def test_pagination(self, ctx):
        initialize_database(ctx)
        for i in range(5):
            _insert_manifest(ctx, partition_key=f"2026-0{i+1}")

        result = list_manifest_entries(ctx, ListManifestEntriesRequest(limit=2, offset=0))
        assert result.success is True
        assert result.total == 5
        assert len(result.data) == 2
        assert result.has_more is True


class TestGetManifestEntry:
    def test_not_found(self, ctx):
        initialize_database(ctx)
        result = get_manifest_entry(ctx, "nonexistent", "2026-01", "bronze")
        assert result.success is False
        assert result.error.code == "NOT_FOUND"

    def test_found(self, ctx):
        initialize_database(ctx)
        _insert_manifest(ctx)
        result = get_manifest_entry(ctx, "finance", "2026-01", "bronze")
        assert result.success is True
        assert result.data.domain == "finance"
        assert result.data.partition_key == "2026-01"
        assert result.data.stage == "bronze"

    def test_validation_missing_params(self, ctx):
        initialize_database(ctx)
        result = get_manifest_entry(ctx, "", "2026-01", "bronze")
        assert result.success is False
        assert result.error.code == "VALIDATION_FAILED"


# ------------------------------------------------------------------ #
# List Rejects Tests
# ------------------------------------------------------------------ #


class TestListRejects:
    def test_empty(self, ctx):
        initialize_database(ctx)
        result = list_rejects(ctx, ListRejectsRequest())
        assert result.success is True
        assert result.data == []
        assert result.total == 0

    def test_with_data(self, ctx):
        initialize_database(ctx)
        _insert_reject(ctx)
        result = list_rejects(ctx, ListRejectsRequest())
        assert result.success is True
        assert result.total == 1
        assert len(result.data) == 1
        assert result.data[0].domain == "finance"
        assert result.data[0].reason_code == "INVALID_DATE"

    def test_filter_by_domain(self, ctx):
        initialize_database(ctx)
        _insert_reject(ctx, domain="finance")
        _insert_reject(ctx, domain="ops", partition_key="2026-02")

        result = list_rejects(ctx, ListRejectsRequest(domain="ops"))
        assert result.success is True
        assert result.total == 1
        assert result.data[0].domain == "ops"

    def test_filter_by_reason_code(self, ctx):
        initialize_database(ctx)
        _insert_reject(ctx, reason_code="INVALID_DATE")
        _insert_reject(ctx, reason_code="NULL_REQUIRED", partition_key="2026-02")

        result = list_rejects(ctx, ListRejectsRequest(reason_code="NULL_REQUIRED"))
        assert result.success is True
        assert result.total == 1
        assert result.data[0].reason_code == "NULL_REQUIRED"

    def test_pagination(self, ctx):
        initialize_database(ctx)
        for i in range(5):
            _insert_reject(ctx, partition_key=f"2026-0{i+1}")

        result = list_rejects(ctx, ListRejectsRequest(limit=2, offset=0))
        assert result.success is True
        assert result.total == 5
        assert len(result.data) == 2
        assert result.has_more is True


class TestCountRejectsByReason:
    def test_empty(self, ctx):
        initialize_database(ctx)
        result = count_rejects_by_reason(ctx)
        assert result.success is True
        assert result.data == []

    def test_with_data(self, ctx):
        initialize_database(ctx)
        _insert_reject(ctx, reason_code="INVALID_DATE", partition_key="2026-01")
        _insert_reject(ctx, reason_code="INVALID_DATE", partition_key="2026-02")
        _insert_reject(ctx, reason_code="NULL_REQUIRED", partition_key="2026-03")

        result = count_rejects_by_reason(ctx)
        assert result.success is True
        assert len(result.data) == 2
        # Find INVALID_DATE count
        invalid_date = next((r for r in result.data if r["reason_code"] == "INVALID_DATE"), None)
        assert invalid_date is not None
        assert invalid_date["count"] == 2

    def test_filter_by_domain(self, ctx):
        initialize_database(ctx)
        _insert_reject(ctx, domain="finance", reason_code="INVALID_DATE", partition_key="2026-01")
        _insert_reject(ctx, domain="ops", reason_code="NULL_REQUIRED", partition_key="2026-02")

        result = count_rejects_by_reason(ctx, domain="finance")
        assert result.success is True
        assert len(result.data) == 1
        assert result.data[0]["reason_code"] == "INVALID_DATE"


# ------------------------------------------------------------------ #
# List Work Items Tests
# ------------------------------------------------------------------ #


class TestListWorkItems:
    def test_empty(self, ctx):
        initialize_database(ctx)
        result = list_work_items(ctx, ListWorkItemsRequest())
        assert result.success is True
        assert result.data == []
        assert result.total == 0

    def test_with_data(self, ctx):
        initialize_database(ctx)
        _insert_work_item(ctx)
        result = list_work_items(ctx, ListWorkItemsRequest())
        assert result.success is True
        assert result.total == 1
        assert len(result.data) == 1
        assert result.data[0].domain == "finance"
        assert result.data[0].workflow == "ingest"
        assert result.data[0].state == "PENDING"

    def test_filter_by_state(self, ctx):
        initialize_database(ctx)
        _insert_work_item(ctx, item_id=1, state="PENDING")
        _insert_work_item(ctx, item_id=2, state="RUNNING", partition_key="2026-02")

        result = list_work_items(ctx, ListWorkItemsRequest(state="RUNNING"))
        assert result.success is True
        assert result.total == 1
        assert result.data[0].state == "RUNNING"

    def test_filter_by_workflow(self, ctx):
        initialize_database(ctx)
        _insert_work_item(ctx, item_id=1, workflow="ingest")
        _insert_work_item(ctx, item_id=2, workflow="transform", partition_key="2026-02")

        result = list_work_items(ctx, ListWorkItemsRequest(workflow="transform"))
        assert result.success is True
        assert result.total == 1
        assert result.data[0].workflow == "transform"

    def test_pagination(self, ctx):
        initialize_database(ctx)
        for i in range(5):
            _insert_work_item(ctx, item_id=i + 1, partition_key=f"2026-0{i+1}")

        result = list_work_items(ctx, ListWorkItemsRequest(limit=2, offset=0))
        assert result.success is True
        assert result.total == 5
        assert len(result.data) == 2
        assert result.has_more is True


# ------------------------------------------------------------------ #
# Claim Work Item Tests
# ------------------------------------------------------------------ #


class TestClaimWorkItem:
    def test_validation_missing_params(self, ctx):
        initialize_database(ctx)
        result = claim_work_item(ctx, ClaimWorkItemRequest(item_id=0, worker_id=""))
        assert result.success is False
        assert result.error.code == "VALIDATION_FAILED"

    def test_not_found(self, ctx):
        initialize_database(ctx)
        result = claim_work_item(ctx, ClaimWorkItemRequest(item_id=999, worker_id="worker_1"))
        assert result.success is False
        assert result.error.code == "NOT_FOUND"

    def test_claim_pending_item(self, ctx):
        initialize_database(ctx)
        _insert_work_item(ctx, item_id=1, state="PENDING")
        result = claim_work_item(ctx, ClaimWorkItemRequest(item_id=1, worker_id="worker_1"))
        assert result.success is True
        assert result.data.state == "RUNNING"
        assert result.data.locked_by == "worker_1"

    def test_dry_run(self, dry_ctx):
        apply_all_schemas(dry_ctx.conn)
        _insert_work_item(dry_ctx, item_id=1, state="PENDING")
        result = claim_work_item(dry_ctx, ClaimWorkItemRequest(item_id=1, worker_id="worker_1"))
        assert result.success is True
        # Dry run should return mock summary without modifying DB
        assert result.data.state == "RUNNING"


# ------------------------------------------------------------------ #
# Complete Work Item Tests
# ------------------------------------------------------------------ #


class TestCompleteWorkItem:
    def test_validation_missing_param(self, ctx):
        initialize_database(ctx)
        result = complete_work_item(ctx, item_id=0)
        assert result.success is False
        assert result.error.code == "VALIDATION_FAILED"

    def test_complete_running_item(self, ctx):
        initialize_database(ctx)
        _insert_work_item(ctx, item_id=1, state="RUNNING")
        result = complete_work_item(ctx, item_id=1, execution_id="exec_001")
        assert result.success is True

    def test_dry_run(self, dry_ctx):
        apply_all_schemas(dry_ctx.conn)
        _insert_work_item(dry_ctx, item_id=1, state="RUNNING")
        result = complete_work_item(dry_ctx, item_id=1)
        assert result.success is True


# ------------------------------------------------------------------ #
# Fail Work Item Tests
# ------------------------------------------------------------------ #


class TestFailWorkItem:
    def test_validation_missing_param(self, ctx):
        initialize_database(ctx)
        result = fail_work_item(ctx, item_id=0, error="test error")
        assert result.success is False
        assert result.error.code == "VALIDATION_FAILED"

    def test_not_found(self, ctx):
        initialize_database(ctx)
        result = fail_work_item(ctx, item_id=999, error="test error")
        assert result.success is False
        assert result.error.code == "NOT_FOUND"

    def test_fail_running_item(self, ctx):
        initialize_database(ctx)
        _insert_work_item(ctx, item_id=1, state="RUNNING")
        result = fail_work_item(ctx, item_id=1, error="Something went wrong")
        assert result.success is True

    def test_dry_run(self, dry_ctx):
        apply_all_schemas(dry_ctx.conn)
        _insert_work_item(dry_ctx, item_id=1, state="RUNNING")
        result = fail_work_item(dry_ctx, item_id=1, error="test error")
        assert result.success is True


# ------------------------------------------------------------------ #
# Cancel Work Item Tests
# ------------------------------------------------------------------ #


class TestCancelWorkItem:
    def test_validation_missing_param(self, ctx):
        initialize_database(ctx)
        result = cancel_work_item(ctx, item_id=0)
        assert result.success is False
        assert result.error.code == "VALIDATION_FAILED"

    def test_cancel_pending_item(self, ctx):
        initialize_database(ctx)
        _insert_work_item(ctx, item_id=1, state="PENDING")
        result = cancel_work_item(ctx, item_id=1)
        assert result.success is True

    def test_dry_run(self, dry_ctx):
        apply_all_schemas(dry_ctx.conn)
        _insert_work_item(dry_ctx, item_id=1, state="PENDING")
        result = cancel_work_item(dry_ctx, item_id=1)
        assert result.success is True


# ------------------------------------------------------------------ #
# Retry Failed Work Items Tests
# ------------------------------------------------------------------ #


class TestRetryFailedWorkItems:
    def test_no_failed_items(self, ctx):
        initialize_database(ctx)
        _insert_work_item(ctx, item_id=1, state="PENDING")
        result = retry_failed_work_items(ctx)
        assert result.success is True
        assert result.data == 0

    def test_retry_failed_items(self, ctx):
        initialize_database(ctx)
        _insert_work_item(ctx, item_id=1, state="FAILED")
        _insert_work_item(ctx, item_id=2, state="FAILED", partition_key="2026-02")
        result = retry_failed_work_items(ctx)
        assert result.success is True
        assert result.data == 2

    def test_filter_by_domain(self, ctx):
        initialize_database(ctx)
        _insert_work_item(ctx, item_id=1, domain="finance", state="FAILED")
        _insert_work_item(ctx, item_id=2, domain="ops", state="FAILED", partition_key="2026-02")
        result = retry_failed_work_items(ctx, domain="finance")
        assert result.success is True
        assert result.data == 1

    def test_dry_run(self, dry_ctx):
        apply_all_schemas(dry_ctx.conn)
        _insert_work_item(dry_ctx, item_id=1, state="FAILED")
        _insert_work_item(dry_ctx, item_id=2, state="FAILED", partition_key="2026-02")
        result = retry_failed_work_items(dry_ctx)
        assert result.success is True
        # Dry run should return count without modifying
        assert result.data == 2
