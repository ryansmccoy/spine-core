"""Tests for ops error branches — alerts, schedules, processing.

Uses monkeypatch for proper mock isolation (no cross-test state leakage).
Makes `_*_repo(ctx)` itself raise, which triggers the except-handler in
each operation function.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from spine.ops.context import OperationContext


@pytest.fixture()
def ctx():
    return OperationContext(conn=MagicMock(), caller="test")


def _raiser(msg: str = "db"):
    """Return a callable that raises RuntimeError."""
    def _raise(_ctx):
        raise RuntimeError(msg)
    return _raise


# ── Alerts ──────────────────────────────────────────────────────────


class TestAlertsErrorBranches:
    """Each test patches _alert_repo to raise, triggering the except handler."""

    def test_list_channels(self, ctx, monkeypatch):
        monkeypatch.setattr("spine.ops.alerts._alert_repo", _raiser())
        from spine.ops.alerts import list_alert_channels
        from spine.ops.requests import ListAlertChannelsRequest
        r = list_alert_channels(ctx, ListAlertChannelsRequest())
        assert r.success is False

    def test_get_channel(self, ctx, monkeypatch):
        monkeypatch.setattr("spine.ops.alerts._alert_repo", _raiser())
        from spine.ops.alerts import get_alert_channel
        r = get_alert_channel(ctx, "ch1")
        assert r.success is False

    def test_create_channel(self, ctx, monkeypatch):
        monkeypatch.setattr("spine.ops.alerts._alert_repo", _raiser())
        from spine.ops.alerts import create_alert_channel
        from spine.ops.requests import CreateAlertChannelRequest
        r = create_alert_channel(ctx, CreateAlertChannelRequest(name="x", channel_type="email", config={}))
        assert r.success is False

    def test_delete_channel(self, ctx, monkeypatch):
        monkeypatch.setattr("spine.ops.alerts._alert_repo", _raiser())
        from spine.ops.alerts import delete_alert_channel
        r = delete_alert_channel(ctx, "ch1")
        assert r.success is False

    def test_update_channel(self, ctx, monkeypatch):
        monkeypatch.setattr("spine.ops.alerts._alert_repo", _raiser())
        from spine.ops.alerts import update_alert_channel
        r = update_alert_channel(ctx, "ch1", enabled=True)
        assert r.success is False

    def test_list_alerts(self, ctx, monkeypatch):
        monkeypatch.setattr("spine.ops.alerts._alert_repo", _raiser())
        from spine.ops.alerts import list_alerts
        from spine.ops.requests import ListAlertsRequest
        r = list_alerts(ctx, ListAlertsRequest())
        assert r.success is False

    def test_create_alert(self, ctx, monkeypatch):
        monkeypatch.setattr("spine.ops.alerts._alert_repo", _raiser())
        from spine.ops.alerts import create_alert
        from spine.ops.requests import CreateAlertRequest
        r = create_alert(ctx, CreateAlertRequest(severity="high", title="fail", message="fail!"))
        assert r.success is False

    def test_acknowledge_alert(self, ctx, monkeypatch):
        monkeypatch.setattr("spine.ops.alerts._alert_repo", _raiser())
        from spine.ops.alerts import acknowledge_alert
        r = acknowledge_alert(ctx, "a1")
        assert r.success is False

    def test_list_deliveries(self, ctx, monkeypatch):
        monkeypatch.setattr("spine.ops.alerts._alert_repo", _raiser())
        from spine.ops.alerts import list_alert_deliveries
        from spine.ops.requests import ListAlertDeliveriesRequest
        r = list_alert_deliveries(ctx, ListAlertDeliveriesRequest(alert_id="a1"))
        assert r.success is False


# ── Schedules ───────────────────────────────────────────────────────


class TestSchedulesErrorBranches:
    def test_list(self, ctx, monkeypatch):
        monkeypatch.setattr("spine.ops.schedules._sched_repo", _raiser())
        from spine.ops.schedules import list_schedules
        r = list_schedules(ctx)
        assert r.success is False or r.data == []

    def test_get(self, ctx, monkeypatch):
        monkeypatch.setattr("spine.ops.schedules._sched_repo", _raiser())
        from spine.ops.schedules import get_schedule
        from spine.ops.requests import GetScheduleRequest
        r = get_schedule(ctx, GetScheduleRequest(schedule_id="s1"))
        assert r.success is False

    def test_create(self, ctx, monkeypatch):
        monkeypatch.setattr("spine.ops.schedules._sched_repo", _raiser())
        from spine.ops.schedules import create_schedule
        from spine.ops.requests import CreateScheduleRequest
        r = create_schedule(ctx, CreateScheduleRequest(name="j1", target_name="ingest", cron_expression="*/5 * * * *"))
        assert r.success is False

    def test_update(self, ctx, monkeypatch):
        monkeypatch.setattr("spine.ops.schedules._sched_repo", _raiser())
        from spine.ops.schedules import update_schedule
        from spine.ops.requests import UpdateScheduleRequest
        r = update_schedule(ctx, UpdateScheduleRequest(schedule_id="s1"))
        assert r.success is False

    def test_delete(self, ctx, monkeypatch):
        monkeypatch.setattr("spine.ops.schedules._sched_repo", _raiser())
        from spine.ops.schedules import delete_schedule
        from spine.ops.requests import DeleteScheduleRequest
        r = delete_schedule(ctx, DeleteScheduleRequest(schedule_id="s1"))
        assert r.success is False

    def test_calc_deps(self, ctx, monkeypatch):
        monkeypatch.setattr("spine.ops.schedules._calc_dep_repo", _raiser())
        from spine.ops.schedules import list_calc_dependencies
        from spine.ops.requests import ListCalcDependenciesRequest
        r = list_calc_dependencies(ctx, ListCalcDependenciesRequest())
        assert r.data == [] and r.total == 0

    def test_expected(self, ctx, monkeypatch):
        monkeypatch.setattr("spine.ops.schedules._exp_sched_repo", _raiser())
        from spine.ops.schedules import list_expected_schedules
        from spine.ops.requests import ListExpectedSchedulesRequest
        r = list_expected_schedules(ctx, ListExpectedSchedulesRequest())
        assert r.data == [] and r.total == 0

    def test_readiness(self, ctx, monkeypatch):
        monkeypatch.setattr("spine.ops.schedules._readiness_repo", _raiser())
        from spine.ops.schedules import check_data_readiness
        from spine.ops.requests import CheckDataReadinessRequest
        r = check_data_readiness(ctx, CheckDataReadinessRequest(domain="fin"))
        assert r.success is False


# ── Processing ──────────────────────────────────────────────────────


class TestProcessingErrorBranches:
    def test_list_manifests(self, ctx, monkeypatch):
        monkeypatch.setattr("spine.ops.processing._manifest_repo", _raiser())
        from spine.ops.processing import list_manifest_entries
        from spine.ops.requests import ListManifestEntriesRequest
        r = list_manifest_entries(ctx, ListManifestEntriesRequest())
        assert r.data == [] and r.total == 0

    def test_get_manifest(self, ctx, monkeypatch):
        monkeypatch.setattr("spine.ops.processing._manifest_repo", _raiser())
        from spine.ops.processing import get_manifest_entry
        r = get_manifest_entry(ctx, "domain", "pk", "stage")
        assert r.success is False

    def test_list_rejects(self, ctx, monkeypatch):
        monkeypatch.setattr("spine.ops.processing._reject_repo", _raiser())
        from spine.ops.processing import list_rejects
        from spine.ops.requests import ListRejectsRequest
        r = list_rejects(ctx, ListRejectsRequest())
        assert r.data == [] and r.total == 0

    def test_count_rejects(self, ctx, monkeypatch):
        monkeypatch.setattr("spine.ops.processing._reject_repo", _raiser())
        from spine.ops.processing import count_rejects_by_reason
        r = count_rejects_by_reason(ctx)
        assert r.success is False

    def test_list_work_items(self, ctx, monkeypatch):
        monkeypatch.setattr("spine.ops.processing._work_item_repo", _raiser())
        from spine.ops.processing import list_work_items
        from spine.ops.requests import ListWorkItemsRequest
        r = list_work_items(ctx, ListWorkItemsRequest())
        assert r.data == [] and r.total == 0

    def test_claim(self, ctx, monkeypatch):
        monkeypatch.setattr("spine.ops.processing._work_item_repo", _raiser())
        from spine.ops.processing import claim_work_item
        from spine.ops.requests import ClaimWorkItemRequest
        r = claim_work_item(ctx, ClaimWorkItemRequest(item_id=1, worker_id="wk1"))
        assert r.success is False

    def test_complete(self, ctx, monkeypatch):
        monkeypatch.setattr("spine.ops.processing._work_item_repo", _raiser())
        from spine.ops.processing import complete_work_item
        r = complete_work_item(ctx, 1)
        assert r.success is False

    def test_fail(self, ctx, monkeypatch):
        monkeypatch.setattr("spine.ops.processing._work_item_repo", _raiser())
        from spine.ops.processing import fail_work_item
        r = fail_work_item(ctx, 1, "oops")
        assert r.success is False

    def test_cancel(self, ctx, monkeypatch):
        monkeypatch.setattr("spine.ops.processing._work_item_repo", _raiser())
        from spine.ops.processing import cancel_work_item
        r = cancel_work_item(ctx, 1)
        assert r.success is False

    def test_retry_failed(self, ctx, monkeypatch):
        monkeypatch.setattr("spine.ops.processing._work_item_repo", _raiser())
        from spine.ops.processing import retry_failed_work_items
        r = retry_failed_work_items(ctx)
        assert r.success is False
