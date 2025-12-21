"""Tests for ScheduleRepository — CRUD, cron evaluation, and run management.

Uses in-memory SQLite for full integration testing of the repository layer.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

from spine.core.scheduling.repository import (
    ScheduleCreate,
    ScheduleRepository,
    ScheduleUpdate,
)


# ── Fixtures ─────────────────────────────────────────────────

DDL_CORE_SCHEDULES = """
CREATE TABLE core_schedules (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    target_type TEXT NOT NULL DEFAULT 'operation',
    target_name TEXT NOT NULL DEFAULT '',
    params TEXT,
    schedule_type TEXT NOT NULL DEFAULT 'cron',
    cron_expression TEXT,
    interval_seconds INTEGER,
    run_at TEXT,
    timezone TEXT DEFAULT 'UTC',
    enabled INTEGER DEFAULT 1,
    max_instances INTEGER DEFAULT 1,
    misfire_grace_seconds INTEGER DEFAULT 60,
    last_run_at TEXT,
    next_run_at TEXT,
    last_run_status TEXT,
    created_at TEXT,
    updated_at TEXT,
    created_by TEXT,
    version INTEGER DEFAULT 1
)
"""

DDL_CORE_SCHEDULE_RUNS = """
CREATE TABLE core_schedule_runs (
    id TEXT PRIMARY KEY,
    schedule_id TEXT NOT NULL,
    schedule_name TEXT NOT NULL,
    scheduled_at TEXT,
    started_at TEXT,
    completed_at TEXT,
    status TEXT DEFAULT 'PENDING',
    run_id TEXT,
    execution_id TEXT,
    error TEXT,
    skip_reason TEXT,
    created_at TEXT
)
"""


@pytest.fixture()
def conn():
    """In-memory SQLite connection with schema."""
    c = sqlite3.connect(":memory:")
    c.execute(DDL_CORE_SCHEDULES)
    c.execute(DDL_CORE_SCHEDULE_RUNS)
    c.commit()
    return c


@pytest.fixture()
def repo(conn):
    return ScheduleRepository(conn)


# ── CRUD ─────────────────────────────────────────────────────


class TestCreate:
    def test_create_cron_schedule(self, repo):
        s = repo.create(ScheduleCreate(
            name="daily",
            target_type="workflow",
            target_name="etl",
            cron_expression="0 8 * * *",
        ))
        assert s is not None
        assert s.name == "daily"
        assert s.target_type == "workflow"
        assert s.enabled == 1 or s.enabled is True

    def test_create_interval_schedule(self, repo):
        s = repo.create(ScheduleCreate(
            name="heartbeat",
            target_type="operation",
            target_name="ping",
            schedule_type="interval",
            interval_seconds=30,
        ))
        assert s.interval_seconds == 30
        assert s.next_run_at is not None

    def test_create_date_schedule(self, repo):
        future = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
        s = repo.create(ScheduleCreate(
            name="once",
            target_type="workflow",
            target_name="migration",
            schedule_type="date",
            run_at=future,
        ))
        assert s.schedule_type == "date"

    def test_create_with_params(self, repo):
        s = repo.create(ScheduleCreate(
            name="param-test",
            target_type="operation",
            target_name="export",
            schedule_type="interval",
            interval_seconds=60,
            params={"format": "csv", "bucket": "s3://out"},
        ))
        assert '"format"' in s.params


class TestGet:
    def test_get_by_id(self, repo):
        created = repo.create(ScheduleCreate(
            name="fetch", target_type="operation", target_name="check",
            schedule_type="interval", interval_seconds=60,
        ))
        got = repo.get(created.id)
        assert got is not None
        assert got.name == "fetch"

    def test_get_missing(self, repo):
        assert repo.get("nonexistent") is None

    def test_get_by_name(self, repo):
        repo.create(ScheduleCreate(
            name="named", target_type="operation", target_name="x",
            schedule_type="interval", interval_seconds=60,
        ))
        assert repo.get_by_name("named") is not None
        assert repo.get_by_name("missing") is None


class TestUpdate:
    def test_update_enabled(self, repo):
        s = repo.create(ScheduleCreate(
            name="upd", target_type="operation", target_name="t",
            schedule_type="interval", interval_seconds=60,
        ))
        updated = repo.update(s.id, ScheduleUpdate(enabled=False))
        assert updated.enabled == 0 or updated.enabled is False

    def test_update_cron(self, repo):
        s = repo.create(ScheduleCreate(
            name="cron-upd", target_type="operation", target_name="t",
            cron_expression="0 8 * * *",
        ))
        updated = repo.update(s.id, ScheduleUpdate(cron_expression="0 9 * * *"))
        assert updated.cron_expression == "0 9 * * *"

    def test_update_multiple_fields(self, repo):
        s = repo.create(ScheduleCreate(
            name="multi", target_type="operation", target_name="t",
            schedule_type="interval", interval_seconds=60,
        ))
        updated = repo.update(s.id, ScheduleUpdate(
            timezone="US/Eastern",
            max_instances=3,
            misfire_grace_seconds=120,
            params={"key": "val"},
        ))
        assert updated.timezone == "US/Eastern"
        assert updated.max_instances == 3

    def test_update_no_fields_returns_existing(self, repo):
        s = repo.create(ScheduleCreate(
            name="noop", target_type="operation", target_name="t",
            schedule_type="interval", interval_seconds=60,
        ))
        updated = repo.update(s.id, ScheduleUpdate())
        assert updated.name == "noop"


class TestDelete:
    def test_delete_existing(self, repo):
        s = repo.create(ScheduleCreate(
            name="del", target_type="operation", target_name="t",
            schedule_type="interval", interval_seconds=60,
        ))
        assert repo.delete(s.id) is True
        assert repo.get(s.id) is None

    def test_delete_missing(self, repo):
        assert repo.delete("nonexistent") is False


class TestListAndCount:
    def test_list_enabled(self, repo):
        repo.create(ScheduleCreate(
            name="a", target_type="operation", target_name="t",
            schedule_type="interval", interval_seconds=60, enabled=True,
        ))
        repo.create(ScheduleCreate(
            name="b", target_type="operation", target_name="t",
            schedule_type="interval", interval_seconds=60, enabled=False,
        ))
        assert len(repo.list_enabled()) == 1

    def test_list_all(self, repo):
        repo.create(ScheduleCreate(
            name="a1", target_type="operation", target_name="t",
            schedule_type="interval", interval_seconds=60, enabled=True,
        ))
        repo.create(ScheduleCreate(
            name="b1", target_type="operation", target_name="t",
            schedule_type="interval", interval_seconds=60, enabled=False,
        ))
        assert len(repo.list_all()) == 2

    def test_count_enabled(self, repo):
        repo.create(ScheduleCreate(
            name="c1", target_type="operation", target_name="t",
            schedule_type="interval", interval_seconds=60,
        ))
        assert repo.count_enabled() == 1


# ── Scheduling Operations ────────────────────────────────────


class TestDueSchedules:
    def test_due_schedules(self, repo):
        repo.create(ScheduleCreate(
            name="due", target_type="operation", target_name="t",
            schedule_type="interval", interval_seconds=1,  # next_run very soon
        ))
        # All interval schedules start with next_run in the future,
        # so manually set next_run_at to past
        repo.conn.execute(
            "UPDATE core_schedules SET next_run_at = ?",
            ((datetime.now(UTC) - timedelta(minutes=1)).isoformat(),),
        )
        repo.conn.commit()
        due = repo.get_due_schedules(datetime.now(UTC))
        assert len(due) == 1

    def test_no_due_schedules(self, repo):
        repo.create(ScheduleCreate(
            name="future", target_type="operation", target_name="t",
            schedule_type="interval", interval_seconds=3600,
        ))
        due = repo.get_due_schedules(datetime.now(UTC))
        assert len(due) == 0


class TestComputeNextRun:
    def test_interval_next_run(self, repo):
        from spine.core.models.scheduler import Schedule
        s = Schedule(schedule_type="interval", interval_seconds=30)
        now = datetime.now(UTC)
        result = repo.compute_next_run(s, now)
        assert result == now + timedelta(seconds=30)

    def test_interval_no_seconds(self, repo):
        from spine.core.models.scheduler import Schedule
        s = Schedule(schedule_type="interval", interval_seconds=None)
        assert repo.compute_next_run(s, datetime.now(UTC)) is None

    def test_date_future(self, repo):
        from spine.core.models.scheduler import Schedule
        future = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
        s = Schedule(schedule_type="date", run_at=future)
        result = repo.compute_next_run(s, datetime.now(UTC))
        assert result is not None

    def test_date_past(self, repo):
        from spine.core.models.scheduler import Schedule
        past = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
        s = Schedule(schedule_type="date", run_at=past)
        result = repo.compute_next_run(s, datetime.now(UTC))
        assert result is None

    def test_date_no_run_at(self, repo):
        from spine.core.models.scheduler import Schedule
        s = Schedule(schedule_type="date", run_at=None)
        assert repo.compute_next_run(s, datetime.now(UTC)) is None

    def test_unknown_type(self, repo):
        from spine.core.models.scheduler import Schedule
        s = Schedule(schedule_type="weird")
        assert repo.compute_next_run(s, datetime.now(UTC)) is None

    def test_cron_next_run(self, repo):
        from spine.core.models.scheduler import Schedule
        s = Schedule(schedule_type="cron", cron_expression="0 * * * *")
        now = datetime.now(UTC)
        result = repo.compute_next_run(s, now)
        # Should be next hour mark
        assert result is not None
        assert result > now

    def test_cron_no_expression(self, repo):
        assert repo._compute_cron_next(None, datetime.now(UTC)) is None


# ── Run Management ───────────────────────────────────────────


class TestRunManagement:
    def test_mark_run_started(self, repo):
        s = repo.create(ScheduleCreate(
            name="run-test", target_type="operation", target_name="t",
            schedule_type="interval", interval_seconds=60,
        ))
        run_id = repo.mark_run_started(s.id, "exec-123")
        assert run_id is not None

        # Verify schedule updated
        updated = repo.get(s.id)
        assert updated.last_run_status == "RUNNING"

    def test_mark_run_started_missing_schedule(self, repo):
        with pytest.raises(ValueError, match="Schedule not found"):
            repo.mark_run_started("nonexistent", "r1")

    def test_mark_run_completed(self, repo):
        s = repo.create(ScheduleCreate(
            name="complete-test", target_type="operation", target_name="t",
            schedule_type="interval", interval_seconds=60,
        ))
        repo.mark_run_started(s.id, "exec-456")
        repo.mark_run_completed(s.id, "COMPLETED")

        updated = repo.get(s.id)
        assert updated.last_run_status == "COMPLETED"
        assert updated.next_run_at is not None

    def test_mark_run_completed_with_error(self, repo):
        s = repo.create(ScheduleCreate(
            name="fail-test", target_type="operation", target_name="t",
            schedule_type="interval", interval_seconds=60,
        ))
        repo.mark_run_started(s.id, "exec-789")
        repo.mark_run_completed(s.id, "FAILED", error="timeout")

    def test_mark_run_completed_missing_schedule(self, repo):
        with pytest.raises(ValueError, match="Schedule not found"):
            repo.mark_run_completed("nonexistent", "COMPLETED")

    def test_get_run(self, repo):
        s = repo.create(ScheduleCreate(
            name="get-run", target_type="operation", target_name="t",
            schedule_type="interval", interval_seconds=60,
        ))
        run_id = repo.mark_run_started(s.id, "exec-100")
        run = repo.get_run(run_id)
        assert run is not None
        assert run.status == "RUNNING"

    def test_get_run_missing(self, repo):
        assert repo.get_run("nonexistent") is None

    def test_list_runs(self, repo):
        s = repo.create(ScheduleCreate(
            name="list-runs", target_type="operation", target_name="t",
            schedule_type="interval", interval_seconds=60,
        ))
        repo.mark_run_started(s.id, "a")
        repo.mark_run_completed(s.id, "COMPLETED")
        repo.mark_run_started(s.id, "b")
        runs = repo.list_runs(s.id)
        assert len(runs) == 2

    def test_list_runs_with_status_filter(self, repo):
        s = repo.create(ScheduleCreate(
            name="filter-runs", target_type="operation", target_name="t",
            schedule_type="interval", interval_seconds=60,
        ))
        repo.mark_run_started(s.id, "c")
        repo.mark_run_completed(s.id, "COMPLETED")
        repo.mark_run_started(s.id, "d")
        runs = repo.list_runs(s.id, status="RUNNING")
        assert len(runs) == 1
        assert runs[0].status == "RUNNING"
