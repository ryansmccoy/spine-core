"""
Tests for spine.core.backfill module.

Tests cover:
- BackfillPlan.create factory
- Lifecycle transitions (start, mark_partition_done, mark_partition_failed, cancel)
- progress_pct and remaining_keys properties
- is_resumable logic
- Checkpoint save/restore
- Auto-completion on last partition
- to_dict serialisation
- Edge cases (empty keys, unknown keys)
"""

import pytest
from datetime import UTC, datetime

from spine.core.backfill import BackfillPlan, BackfillReason, BackfillStatus


# =============================================================================
# BackfillPlan creation
# =============================================================================


class TestBackfillPlanCreation:
    """Tests for BackfillPlan.create factory."""

    def test_create_basic(self):
        plan = BackfillPlan.create(
            domain="equity",
            source="polygon",
            partition_keys=["AAPL", "MSFT"],
            reason=BackfillReason.GAP,
        )
        assert plan.domain == "equity"
        assert plan.source == "polygon"
        assert plan.partition_keys == ["AAPL", "MSFT"]
        assert plan.reason == BackfillReason.GAP
        assert plan.status == BackfillStatus.PLANNED
        assert plan.plan_id  # ULID should be generated

    def test_create_with_range(self):
        plan = BackfillPlan.create(
            domain="d",
            source="s",
            partition_keys=["pk1"],
            reason=BackfillReason.CORRECTION,
            range_start="2026-01-01",
            range_end="2026-02-01",
        )
        assert plan.range_start == "2026-01-01"
        assert plan.range_end == "2026-02-01"

    def test_create_with_metadata(self):
        plan = BackfillPlan.create(
            domain="d",
            source="s",
            partition_keys=["pk1"],
            reason=BackfillReason.MANUAL,
            metadata={"ticket": "JIRA-123"},
        )
        assert plan.metadata == {"ticket": "JIRA-123"}

    def test_create_empty_keys_raises(self):
        with pytest.raises(ValueError, match="must not be empty"):
            BackfillPlan.create(
                domain="d",
                source="s",
                partition_keys=[],
                reason=BackfillReason.GAP,
            )

    def test_create_sets_created_at(self):
        plan = BackfillPlan.create(
            domain="d",
            source="s",
            partition_keys=["pk1"],
            reason=BackfillReason.GAP,
        )
        now = datetime.now(UTC)
        assert (now - plan.created_at).total_seconds() < 2


# =============================================================================
# Properties
# =============================================================================


class TestBackfillPlanProperties:
    """Tests for progress_pct, remaining_keys, is_resumable."""

    def test_progress_pct_zero(self):
        plan = BackfillPlan.create(
            domain="d", source="s",
            partition_keys=["a", "b", "c"],
            reason=BackfillReason.GAP,
        )
        assert plan.progress_pct == 0.0

    def test_progress_pct_partial(self):
        plan = BackfillPlan.create(
            domain="d", source="s",
            partition_keys=["a", "b", "c"],
            reason=BackfillReason.GAP,
        )
        plan.start()
        plan.mark_partition_done("a")
        assert plan.progress_pct == 33.33

    def test_progress_pct_with_failures(self):
        plan = BackfillPlan.create(
            domain="d", source="s",
            partition_keys=["a", "b"],
            reason=BackfillReason.GAP,
        )
        plan.start()
        plan.mark_partition_done("a")
        plan.mark_partition_failed("b", "timeout")
        assert plan.progress_pct == 100.0

    def test_remaining_keys(self):
        plan = BackfillPlan.create(
            domain="d", source="s",
            partition_keys=["a", "b", "c"],
            reason=BackfillReason.GAP,
        )
        plan.start()
        plan.mark_partition_done("a")
        assert plan.remaining_keys == ["b", "c"]

    def test_is_resumable_when_running(self):
        plan = BackfillPlan.create(
            domain="d", source="s",
            partition_keys=["a", "b"],
            reason=BackfillReason.GAP,
        )
        plan.start()
        plan.mark_partition_done("a")
        assert plan.is_resumable is True

    def test_is_resumable_when_planned(self):
        plan = BackfillPlan.create(
            domain="d", source="s",
            partition_keys=["a"],
            reason=BackfillReason.GAP,
        )
        assert plan.is_resumable is False

    def test_is_resumable_when_completed(self):
        plan = BackfillPlan.create(
            domain="d", source="s",
            partition_keys=["a"],
            reason=BackfillReason.GAP,
        )
        plan.start()
        plan.mark_partition_done("a")
        assert plan.status == BackfillStatus.COMPLETED
        assert plan.is_resumable is False

    def test_is_resumable_when_failed_with_remaining(self):
        plan = BackfillPlan.create(
            domain="d", source="s",
            partition_keys=["a", "b"],
            reason=BackfillReason.GAP,
        )
        plan.start()
        plan.mark_partition_failed("a", "error")
        # status is still RUNNING (b not done)
        plan.status = BackfillStatus.FAILED
        assert plan.is_resumable is True


# =============================================================================
# Lifecycle transitions
# =============================================================================


class TestBackfillPlanLifecycle:
    """Tests for start, mark_partition_done/failed, cancel."""

    def test_start_from_planned(self):
        plan = BackfillPlan.create(
            domain="d", source="s",
            partition_keys=["a"],
            reason=BackfillReason.GAP,
        )
        plan.start()
        assert plan.status == BackfillStatus.RUNNING
        assert plan.started_at is not None

    def test_start_from_failed(self):
        """FAILED plans can be restarted (resumed)."""
        plan = BackfillPlan.create(
            domain="d", source="s",
            partition_keys=["a", "b"],
            reason=BackfillReason.GAP,
        )
        plan.status = BackfillStatus.FAILED
        plan.start()
        assert plan.status == BackfillStatus.RUNNING

    def test_start_from_completed_raises(self):
        plan = BackfillPlan.create(
            domain="d", source="s",
            partition_keys=["a"],
            reason=BackfillReason.GAP,
        )
        plan.status = BackfillStatus.COMPLETED
        with pytest.raises(ValueError, match="Cannot start"):
            plan.start()

    def test_mark_partition_done_auto_completes(self):
        plan = BackfillPlan.create(
            domain="d", source="s",
            partition_keys=["a"],
            reason=BackfillReason.GAP,
        )
        plan.start()
        plan.mark_partition_done("a")
        assert plan.status == BackfillStatus.COMPLETED
        assert plan.completed_at is not None

    def test_mark_partition_done_unknown_key_raises(self):
        plan = BackfillPlan.create(
            domain="d", source="s",
            partition_keys=["a"],
            reason=BackfillReason.GAP,
        )
        with pytest.raises(ValueError, match="Unknown partition_key"):
            plan.mark_partition_done("UNKNOWN")

    def test_mark_partition_done_idempotent(self):
        plan = BackfillPlan.create(
            domain="d", source="s",
            partition_keys=["a", "b"],
            reason=BackfillReason.GAP,
        )
        plan.start()
        plan.mark_partition_done("a")
        plan.mark_partition_done("a")  # no-op
        assert plan.completed_keys.count("a") == 1

    def test_mark_partition_failed_all_auto_fails(self):
        plan = BackfillPlan.create(
            domain="d", source="s",
            partition_keys=["a"],
            reason=BackfillReason.GAP,
        )
        plan.start()
        plan.mark_partition_failed("a", "oops")
        assert plan.status == BackfillStatus.FAILED
        assert plan.completed_at is not None
        assert plan.failed_keys == {"a": "oops"}

    def test_mark_partition_failed_unknown_key_raises(self):
        plan = BackfillPlan.create(
            domain="d", source="s",
            partition_keys=["a"],
            reason=BackfillReason.GAP,
        )
        with pytest.raises(ValueError, match="Unknown partition_key"):
            plan.mark_partition_failed("UNKNOWN", "err")

    def test_cancel(self):
        plan = BackfillPlan.create(
            domain="d", source="s",
            partition_keys=["a", "b"],
            reason=BackfillReason.GAP,
        )
        plan.start()
        plan.cancel()
        assert plan.status == BackfillStatus.CANCELLED
        assert plan.completed_at is not None

    def test_checkpoint_save(self):
        plan = BackfillPlan.create(
            domain="d", source="s",
            partition_keys=["a"],
            reason=BackfillReason.GAP,
        )
        plan.start()
        plan.save_checkpoint("offset=42")
        assert plan.checkpoint == "offset=42"


# =============================================================================
# Serialisation
# =============================================================================


class TestBackfillPlanSerialization:
    """Tests for to_dict serialisation."""

    def test_to_dict_returns_all_fields(self):
        plan = BackfillPlan.create(
            domain="equity",
            source="polygon",
            partition_keys=["AAPL", "MSFT"],
            reason=BackfillReason.GAP,
            range_start="2026-01-01",
            range_end="2026-02-01",
            created_by="test",
        )
        d = plan.to_dict()
        assert d["domain"] == "equity"
        assert d["source"] == "polygon"
        assert d["partition_keys_json"] == ["AAPL", "MSFT"]
        assert d["reason"] == "gap"
        assert d["status"] == "planned"
        assert d["range_start"] == "2026-01-01"
        assert d["range_end"] == "2026-02-01"
        assert d["created_by"] == "test"
        assert d["plan_id"]
        assert d["created_at"]

    def test_to_dict_after_progress(self):
        plan = BackfillPlan.create(
            domain="d", source="s",
            partition_keys=["a", "b"],
            reason=BackfillReason.CORRECTION,
        )
        plan.start()
        plan.mark_partition_done("a")
        plan.save_checkpoint("page=2")
        d = plan.to_dict()
        assert d["completed_keys_json"] == ["a"]
        assert d["checkpoint"] == "page=2"
        assert d["started_at"] is not None


# =============================================================================
# Enum coverage
# =============================================================================


class TestBackfillEnums:
    """Tests for BackfillStatus and BackfillReason enums."""

    def test_all_statuses(self):
        expected = {"planned", "running", "completed", "failed", "cancelled"}
        actual = {s.value for s in BackfillStatus}
        assert actual == expected

    def test_all_reasons(self):
        expected = {"gap", "correction", "quality_failure", "schema_change", "manual"}
        actual = {r.value for r in BackfillReason}
        assert actual == expected

    def test_reason_string_comparison(self):
        assert BackfillReason.GAP == "gap"
        assert BackfillReason.MANUAL == "manual"
