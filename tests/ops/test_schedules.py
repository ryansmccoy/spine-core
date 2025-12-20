"""Tests for spine.ops.schedules — schedule, calc dependency, and data readiness operations."""

import pytest

from spine.core.schema_loader import apply_all_schemas
from spine.ops.database import initialize_database
from spine.ops.schedules import (
    check_data_readiness,
    create_schedule,
    delete_schedule,
    get_schedule,
    list_calc_dependencies,
    list_expected_schedules,
    list_schedules,
    update_schedule,
)
from spine.ops.requests import (
    CheckDataReadinessRequest,
    CreateScheduleRequest,
    DeleteScheduleRequest,
    GetScheduleRequest,
    ListCalcDependenciesRequest,
    ListExpectedSchedulesRequest,
    UpdateScheduleRequest,
)


# ------------------------------------------------------------------ #
# Schedule Test Helpers
# ------------------------------------------------------------------ #


def _insert_schedule(
    ctx,
    schedule_id="sched_001",
    name="daily-ingest",
    target_type="pipeline",
    target_name="finance-ingest",
    cron_expression="0 8 * * *",
    interval_seconds=None,
    enabled=1,
):
    """Insert a schedule row."""
    ctx.conn.execute(
        """
        INSERT INTO core_schedules (
            id, name, target_type, target_name, cron_expression,
            interval_seconds, enabled, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
        """,
        (schedule_id, name, target_type, target_name, cron_expression, interval_seconds, enabled),
    )
    ctx.conn.commit()


def _insert_calc_dependency(
    ctx,
    dep_id=1,
    calc_domain="finance",
    calc_pipeline="ratios",
    calc_table="silver_ratios",
    depends_on_domain="finance",
    depends_on_table="silver_balances",
    dependency_type="REQUIRED",
):
    """Insert a calculation dependency row."""
    ctx.conn.execute(
        """
        INSERT INTO core_calc_dependencies (
            id, calc_domain, calc_pipeline, calc_table,
            depends_on_domain, depends_on_table, dependency_type, description
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (dep_id, calc_domain, calc_pipeline, calc_table,
         depends_on_domain, depends_on_table, dependency_type, "Test dependency"),
    )
    ctx.conn.commit()


def _insert_expected_schedule(
    ctx,
    sched_id=1,
    domain="finance",
    pipeline="ingest",
    schedule_type="DAILY",
    cron_expression="0 8 * * *",
    expected_delay_hours=2,
    preliminary_hours=12,
    is_active=1,
):
    """Insert an expected schedule row."""
    ctx.conn.execute(
        """
        INSERT INTO core_expected_schedules (
            id, domain, pipeline, schedule_type, cron_expression,
            partition_template, expected_delay_hours, preliminary_hours, is_active
        ) VALUES (?, ?, ?, ?, ?, '{}', ?, ?, ?)
        """,
        (sched_id, domain, pipeline, schedule_type, cron_expression,
         expected_delay_hours, preliminary_hours, is_active),
    )
    ctx.conn.commit()


def _insert_data_readiness(
    ctx,
    readiness_id=1,
    domain="finance",
    partition_key="2026-01",
    is_ready=1,
    ready_for="analytics",
    all_partitions_present=1,
    all_stages_complete=1,
    no_critical_anomalies=1,
    dependencies_current=1,
    blocking_issues="[]",
):
    """Insert a data readiness row."""
    ctx.conn.execute(
        """
        INSERT INTO core_data_readiness (
            id, domain, partition_key, is_ready, ready_for,
            all_partitions_present, all_stages_complete, no_critical_anomalies,
            dependencies_current, blocking_issues, certified_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        """,
        (readiness_id, domain, partition_key, is_ready, ready_for,
         all_partitions_present, all_stages_complete, no_critical_anomalies,
         dependencies_current, blocking_issues),
    )
    ctx.conn.commit()


# ------------------------------------------------------------------ #
# List Schedules Tests
# ------------------------------------------------------------------ #


class TestListSchedules:
    def test_empty(self, ctx):
        initialize_database(ctx)
        result = list_schedules(ctx)
        assert result.success is True
        assert result.data == []
        assert result.total == 0

    def test_with_data(self, ctx):
        initialize_database(ctx)
        _insert_schedule(ctx)
        result = list_schedules(ctx)
        assert result.success is True
        assert result.total == 1
        assert len(result.data) == 1
        assert result.data[0].name == "daily-ingest"
        assert result.data[0].target_name == "finance-ingest"

    def test_multiple_schedules(self, ctx):
        initialize_database(ctx)
        _insert_schedule(ctx, schedule_id="sched_001", name="schedule-1")
        _insert_schedule(ctx, schedule_id="sched_002", name="schedule-2")
        _insert_schedule(ctx, schedule_id="sched_003", name="schedule-3")

        result = list_schedules(ctx)
        assert result.success is True
        assert result.total == 3


# ------------------------------------------------------------------ #
# Get Schedule Tests
# ------------------------------------------------------------------ #


class TestGetSchedule:
    def test_not_found(self, ctx):
        initialize_database(ctx)
        result = get_schedule(ctx, GetScheduleRequest(schedule_id="nonexistent"))
        assert result.success is False
        assert result.error.code == "NOT_FOUND"

    def test_found(self, ctx):
        initialize_database(ctx)
        _insert_schedule(ctx, schedule_id="sched_001", name="daily-ingest")
        result = get_schedule(ctx, GetScheduleRequest(schedule_id="sched_001"))
        assert result.success is True
        assert result.data.name == "daily-ingest"
        assert result.data.target_name == "finance-ingest"

    def test_validation_missing_id(self, ctx):
        initialize_database(ctx)
        result = get_schedule(ctx, GetScheduleRequest(schedule_id=""))
        assert result.success is False
        assert result.error.code == "VALIDATION_FAILED"


# ------------------------------------------------------------------ #
# Create Schedule Tests
# ------------------------------------------------------------------ #


class TestCreateSchedule:
    def test_validation_missing_target(self, ctx):
        initialize_database(ctx)
        result = create_schedule(ctx, CreateScheduleRequest(target_name="", cron_expression="0 8 * * *"))
        assert result.success is False
        assert result.error.code == "VALIDATION_FAILED"

    def test_validation_missing_schedule_expression(self, ctx):
        initialize_database(ctx)
        result = create_schedule(ctx, CreateScheduleRequest(target_name="my-pipeline"))
        assert result.success is False
        assert result.error.code == "VALIDATION_FAILED"

    def test_create_with_cron(self, ctx):
        initialize_database(ctx)
        result = create_schedule(ctx, CreateScheduleRequest(
            name="test-schedule",
            target_type="pipeline",
            target_name="my-pipeline",
            cron_expression="0 9 * * *",
        ))
        assert result.success is True
        assert result.data.name == "test-schedule"
        assert result.data.cron_expression == "0 9 * * *"

    def test_create_with_interval(self, ctx):
        initialize_database(ctx)
        result = create_schedule(ctx, CreateScheduleRequest(
            name="interval-schedule",
            target_type="workflow",
            target_name="my-workflow",
            interval_seconds=3600,
        ))
        assert result.success is True
        assert result.data.interval_seconds == 3600

    def test_dry_run(self, dry_ctx):
        initialize_database(dry_ctx)
        result = create_schedule(dry_ctx, CreateScheduleRequest(
            name="dry-run-schedule",
            target_name="my-pipeline",
            cron_expression="0 8 * * *",
        ))
        assert result.success is True
        # Should return a preview without creating


# ------------------------------------------------------------------ #
# Update Schedule Tests
# ------------------------------------------------------------------ #


class TestUpdateSchedule:
    def test_validation_missing_id(self, ctx):
        initialize_database(ctx)
        result = update_schedule(ctx, UpdateScheduleRequest(schedule_id=""))
        assert result.success is False
        assert result.error.code == "VALIDATION_FAILED"

    def test_validation_no_fields(self, ctx):
        initialize_database(ctx)
        result = update_schedule(ctx, UpdateScheduleRequest(schedule_id="sched_001"))
        assert result.success is False
        assert result.error.code == "VALIDATION_FAILED"

    def test_update_cron(self, ctx):
        initialize_database(ctx)
        _insert_schedule(ctx, schedule_id="sched_001", cron_expression="0 8 * * *")
        result = update_schedule(ctx, UpdateScheduleRequest(
            schedule_id="sched_001",
            cron_expression="0 9 * * *",
        ))
        assert result.success is True
        assert result.data.cron_expression == "0 9 * * *"

    def test_update_enabled(self, ctx):
        initialize_database(ctx)
        _insert_schedule(ctx, schedule_id="sched_001", enabled=1)
        result = update_schedule(ctx, UpdateScheduleRequest(
            schedule_id="sched_001",
            enabled=False,
        ))
        assert result.success is True
        assert result.data.enabled is False

    def test_dry_run(self, dry_ctx):
        apply_all_schemas(dry_ctx.conn)
        _insert_schedule(dry_ctx, schedule_id="sched_001")
        result = update_schedule(dry_ctx, UpdateScheduleRequest(
            schedule_id="sched_001",
            name="new-name",
        ))
        assert result.success is True


# ------------------------------------------------------------------ #
# Delete Schedule Tests
# ------------------------------------------------------------------ #


class TestDeleteSchedule:
    def test_validation_missing_id(self, ctx):
        initialize_database(ctx)
        result = delete_schedule(ctx, DeleteScheduleRequest(schedule_id=""))
        assert result.success is False
        assert result.error.code == "VALIDATION_FAILED"

    def test_delete_existing(self, ctx):
        initialize_database(ctx)
        _insert_schedule(ctx, schedule_id="sched_001")
        result = delete_schedule(ctx, DeleteScheduleRequest(schedule_id="sched_001"))
        assert result.success is True

        # Verify deleted
        get_result = get_schedule(ctx, GetScheduleRequest(schedule_id="sched_001"))
        assert get_result.success is False

    def test_dry_run(self, dry_ctx):
        apply_all_schemas(dry_ctx.conn)
        _insert_schedule(dry_ctx, schedule_id="sched_001")
        result = delete_schedule(dry_ctx, DeleteScheduleRequest(schedule_id="sched_001"))
        assert result.success is True
        # Dry run should not actually delete


# ------------------------------------------------------------------ #
# Calculation Dependencies Tests
# ------------------------------------------------------------------ #


class TestListCalcDependencies:
    def test_empty(self, ctx):
        initialize_database(ctx)
        result = list_calc_dependencies(ctx, ListCalcDependenciesRequest())
        assert result.success is True
        assert result.data == []
        assert result.total == 0

    def test_with_data(self, ctx):
        initialize_database(ctx)
        _insert_calc_dependency(ctx)
        result = list_calc_dependencies(ctx, ListCalcDependenciesRequest())
        assert result.success is True
        assert result.total == 1
        assert result.data[0].calc_domain == "finance"
        assert result.data[0].calc_pipeline == "ratios"

    def test_filter_by_calc_domain(self, ctx):
        initialize_database(ctx)
        _insert_calc_dependency(ctx, dep_id=1, calc_domain="finance")
        _insert_calc_dependency(ctx, dep_id=2, calc_domain="ops")

        result = list_calc_dependencies(ctx, ListCalcDependenciesRequest(calc_domain="ops"))
        assert result.success is True
        assert result.total == 1
        assert result.data[0].calc_domain == "ops"

    def test_filter_by_pipeline(self, ctx):
        initialize_database(ctx)
        _insert_calc_dependency(ctx, dep_id=1, calc_pipeline="ratios")
        _insert_calc_dependency(ctx, dep_id=2, calc_pipeline="aggregates")

        result = list_calc_dependencies(ctx, ListCalcDependenciesRequest(calc_pipeline="aggregates"))
        assert result.success is True
        assert result.total == 1
        assert result.data[0].calc_pipeline == "aggregates"

    def test_pagination(self, ctx):
        initialize_database(ctx)
        for i in range(5):
            _insert_calc_dependency(ctx, dep_id=i + 1, calc_pipeline=f"pipeline-{i}")

        result = list_calc_dependencies(ctx, ListCalcDependenciesRequest(limit=2, offset=0))
        assert result.success is True
        assert result.total == 5
        assert len(result.data) == 2
        assert result.has_more is True


# ------------------------------------------------------------------ #
# Expected Schedules Tests
# ------------------------------------------------------------------ #


class TestListExpectedSchedules:
    def test_empty(self, ctx):
        initialize_database(ctx)
        result = list_expected_schedules(ctx, ListExpectedSchedulesRequest())
        assert result.success is True
        assert result.data == []
        assert result.total == 0

    def test_with_data(self, ctx):
        initialize_database(ctx)
        _insert_expected_schedule(ctx)
        result = list_expected_schedules(ctx, ListExpectedSchedulesRequest())
        assert result.success is True
        assert result.total == 1
        assert result.data[0].domain == "finance"
        assert result.data[0].workflow == "ingest"

    def test_filter_by_domain(self, ctx):
        initialize_database(ctx)
        _insert_expected_schedule(ctx, sched_id=1, domain="finance")
        _insert_expected_schedule(ctx, sched_id=2, domain="ops")

        result = list_expected_schedules(ctx, ListExpectedSchedulesRequest(domain="ops"))
        assert result.success is True
        assert result.total == 1
        assert result.data[0].domain == "ops"

    def test_filter_by_schedule_type(self, ctx):
        initialize_database(ctx)
        _insert_expected_schedule(ctx, sched_id=1, schedule_type="DAILY")
        _insert_expected_schedule(ctx, sched_id=2, schedule_type="WEEKLY")

        result = list_expected_schedules(ctx, ListExpectedSchedulesRequest(schedule_type="WEEKLY"))
        assert result.success is True
        assert result.total == 1
        assert result.data[0].schedule_type == "WEEKLY"

    def test_filter_by_active(self, ctx):
        initialize_database(ctx)
        _insert_expected_schedule(ctx, sched_id=1, is_active=1)
        _insert_expected_schedule(ctx, sched_id=2, is_active=0)

        result = list_expected_schedules(ctx, ListExpectedSchedulesRequest(is_active=True))
        assert result.success is True
        assert result.total == 1
        assert result.data[0].is_active is True

    def test_pagination(self, ctx):
        initialize_database(ctx)
        for i in range(5):
            _insert_expected_schedule(ctx, sched_id=i + 1, pipeline=f"pipeline-{i}")

        result = list_expected_schedules(ctx, ListExpectedSchedulesRequest(limit=2, offset=0))
        assert result.success is True
        assert result.total == 5
        assert len(result.data) == 2
        assert result.has_more is True


# ------------------------------------------------------------------ #
# Data Readiness Tests
# ------------------------------------------------------------------ #


class TestCheckDataReadiness:
    def test_validation_missing_domain(self, ctx):
        initialize_database(ctx)
        result = check_data_readiness(ctx, CheckDataReadinessRequest(domain=""))
        assert result.success is False
        assert result.error.code == "VALIDATION_FAILED"

    def test_empty(self, ctx):
        initialize_database(ctx)
        result = check_data_readiness(ctx, CheckDataReadinessRequest(domain="finance"))
        assert result.success is True
        assert result.data == []
        assert result.total == 0

    def test_with_data(self, ctx):
        initialize_database(ctx)
        _insert_data_readiness(ctx)
        result = check_data_readiness(ctx, CheckDataReadinessRequest(domain="finance"))
        assert result.success is True
        assert result.total == 1
        assert result.data[0].domain == "finance"
        assert result.data[0].is_ready is True

    def test_filter_by_partition(self, ctx):
        initialize_database(ctx)
        _insert_data_readiness(ctx, readiness_id=1, partition_key="2026-01")
        _insert_data_readiness(ctx, readiness_id=2, partition_key="2026-02")

        result = check_data_readiness(ctx, CheckDataReadinessRequest(
            domain="finance",
            partition_key="2026-02",
        ))
        assert result.success is True
        assert result.total == 1
        assert result.data[0].partition_key == "2026-02"

    def test_filter_by_ready_for(self, ctx):
        initialize_database(ctx)
        _insert_data_readiness(ctx, readiness_id=1, ready_for="analytics")
        _insert_data_readiness(ctx, readiness_id=2, ready_for="reporting", partition_key="2026-02")

        result = check_data_readiness(ctx, CheckDataReadinessRequest(
            domain="finance",
            ready_for="reporting",
        ))
        assert result.success is True
        assert result.total == 1
        assert result.data[0].ready_for == "reporting"

    def test_blocking_issues_parsed(self, ctx):
        initialize_database(ctx)
        _insert_data_readiness(
            ctx,
            blocking_issues='["Missing partition 2026-01-15", "Anomaly in revenue"]',
        )
        result = check_data_readiness(ctx, CheckDataReadinessRequest(domain="finance"))
        assert result.success is True
        assert result.total == 1
        assert len(result.data[0].blocking_issues) == 2
        assert "Missing partition" in result.data[0].blocking_issues[0]

    def test_not_ready(self, ctx):
        initialize_database(ctx)
        _insert_data_readiness(
            ctx,
            is_ready=0,
            all_stages_complete=0,
            no_critical_anomalies=0,
        )
        result = check_data_readiness(ctx, CheckDataReadinessRequest(domain="finance"))
        assert result.success is True
        assert result.data[0].is_ready is False
        assert result.data[0].all_stages_complete is False
        assert result.data[0].no_critical_anomalies is False
