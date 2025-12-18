"""Tests for ScheduleRepository."""

from datetime import datetime, timedelta, UTC

import pytest

from spine.core.scheduling import ScheduleCreate, ScheduleRepository, ScheduleUpdate


class TestScheduleRepository:
    """Test ScheduleRepository CRUD operations."""

    def test_create_schedule(self, repository):
        """Create a schedule."""
        spec = ScheduleCreate(
            name="test-schedule",
            target_type="workflow",
            target_name="my-workflow",
            cron_expression="0 * * * *",
        )

        schedule = repository.create(spec)

        assert schedule is not None
        assert schedule.id is not None
        assert schedule.name == "test-schedule"
        assert schedule.target_type == "workflow"
        assert schedule.target_name == "my-workflow"
        assert schedule.cron_expression == "0 * * * *"
        assert schedule.enabled == 1
        assert schedule.next_run_at is not None

    def test_get_schedule(self, repository):
        """Get schedule by ID."""
        spec = ScheduleCreate(
            name="get-test",
            target_type="pipeline",
            target_name="my-pipeline",
            schedule_type="interval",
            interval_seconds=300,
        )

        created = repository.create(spec)
        fetched = repository.get(created.id)

        assert fetched is not None
        assert fetched.id == created.id
        assert fetched.name == "get-test"

    def test_get_by_name(self, repository):
        """Get schedule by name."""
        spec = ScheduleCreate(
            name="named-schedule",
            target_type="workflow",
            target_name="test",
            cron_expression="0 0 * * *",
        )

        repository.create(spec)
        fetched = repository.get_by_name("named-schedule")

        assert fetched is not None
        assert fetched.name == "named-schedule"

    def test_get_nonexistent(self, repository):
        """Get nonexistent schedule returns None."""
        result = repository.get("nonexistent-id")
        assert result is None

    def test_update_schedule(self, repository):
        """Update a schedule."""
        spec = ScheduleCreate(
            name="update-test",
            target_type="workflow",
            target_name="test",
            cron_expression="0 0 * * *",
        )

        created = repository.create(spec)
        
        updates = ScheduleUpdate(
            enabled=False,
            cron_expression="0 12 * * *",
        )
        updated = repository.update(created.id, updates)

        assert updated is not None
        assert updated.enabled == 0
        assert updated.cron_expression == "0 12 * * *"
        assert updated.version == 2

    def test_delete_schedule(self, repository):
        """Delete a schedule."""
        spec = ScheduleCreate(
            name="delete-test",
            target_type="workflow",
            target_name="test",
            cron_expression="0 0 * * *",
        )

        created = repository.create(spec)
        assert repository.get(created.id) is not None

        result = repository.delete(created.id)
        assert result is True
        assert repository.get(created.id) is None

    def test_delete_nonexistent(self, repository):
        """Delete nonexistent schedule returns False."""
        result = repository.delete("nonexistent-id")
        assert result is False

    def test_list_enabled(self, repository):
        """List enabled schedules."""
        # Create enabled schedule
        repository.create(ScheduleCreate(
            name="enabled-1",
            target_type="workflow",
            target_name="test",
            cron_expression="0 0 * * *",
            enabled=True,
        ))

        # Create disabled schedule
        repository.create(ScheduleCreate(
            name="disabled-1",
            target_type="workflow",
            target_name="test",
            cron_expression="0 0 * * *",
            enabled=False,
        ))

        enabled = repository.list_enabled()
        assert len(enabled) == 1
        assert enabled[0].name == "enabled-1"

    def test_list_all(self, repository):
        """List all schedules."""
        repository.create(ScheduleCreate(
            name="all-1",
            target_type="workflow",
            target_name="test",
            cron_expression="0 0 * * *",
            enabled=True,
        ))

        repository.create(ScheduleCreate(
            name="all-2",
            target_type="workflow",
            target_name="test",
            cron_expression="0 0 * * *",
            enabled=False,
        ))

        all_schedules = repository.list_all()
        assert len(all_schedules) == 2

    def test_count_enabled(self, repository):
        """Count enabled schedules."""
        repository.create(ScheduleCreate(
            name="count-1",
            target_type="workflow",
            target_name="test",
            cron_expression="0 0 * * *",
            enabled=True,
        ))

        repository.create(ScheduleCreate(
            name="count-2",
            target_type="workflow",
            target_name="test",
            cron_expression="0 0 * * *",
            enabled=True,
        ))

        repository.create(ScheduleCreate(
            name="count-3",
            target_type="workflow",
            target_name="test",
            cron_expression="0 0 * * *",
            enabled=False,
        ))

        count = repository.count_enabled()
        assert count == 2


class TestScheduleRepositoryDueSchedules:
    """Tests for get_due_schedules and cron evaluation."""

    def test_get_due_schedules_none_due(self, repository):
        """No schedules due returns empty list."""
        # Create schedule with next_run in future
        repository.create(ScheduleCreate(
            name="future-schedule",
            target_type="workflow",
            target_name="test",
            schedule_type="interval",
            interval_seconds=3600,  # 1 hour from now
        ))

        now = datetime.now(UTC)
        due = repository.get_due_schedules(now)
        
        assert len(due) == 0

    def test_get_due_schedules_with_due(self, db_conn, repository):
        """Due schedules are returned."""
        # Create schedule
        schedule = repository.create(ScheduleCreate(
            name="due-schedule",
            target_type="workflow",
            target_name="test",
            schedule_type="interval",
            interval_seconds=3600,
        ))

        # Manually set next_run_at to past
        past = datetime.now(UTC) - timedelta(hours=1)
        db_conn.execute(
            "UPDATE core_schedules SET next_run_at = ? WHERE id = ?",
            (past.isoformat(), schedule.id),
        )
        db_conn.commit()

        now = datetime.now(UTC)
        due = repository.get_due_schedules(now)

        assert len(due) == 1
        assert due[0].name == "due-schedule"

    def test_disabled_schedules_not_due(self, db_conn, repository):
        """Disabled schedules are not returned as due."""
        schedule = repository.create(ScheduleCreate(
            name="disabled-schedule",
            target_type="workflow",
            target_name="test",
            cron_expression="* * * * *",
            enabled=False,
        ))

        # Set past next_run
        past = datetime.now(UTC) - timedelta(hours=1)
        db_conn.execute(
            "UPDATE core_schedules SET next_run_at = ? WHERE id = ?",
            (past.isoformat(), schedule.id),
        )
        db_conn.commit()

        now = datetime.now(UTC)
        due = repository.get_due_schedules(now)

        assert len(due) == 0


class TestScheduleRepositoryCronEvaluation:
    """Tests for cron expression evaluation."""

    def test_compute_next_run_interval(self, repository):
        """Compute next run for interval schedule."""
        schedule = repository.create(ScheduleCreate(
            name="interval-test",
            target_type="workflow",
            target_name="test",
            schedule_type="interval",
            interval_seconds=300,
        ))

        now = datetime.now(UTC)
        next_run = repository.compute_next_run(schedule, now)

        assert next_run is not None
        expected = now + timedelta(seconds=300)
        # Allow 1 second tolerance
        assert abs((next_run - expected).total_seconds()) < 1

    def test_compute_next_run_cron(self, repository):
        """Compute next run for cron schedule."""
        schedule = repository.create(ScheduleCreate(
            name="cron-test",
            target_type="workflow",
            target_name="test",
            schedule_type="cron",
            cron_expression="0 * * * *",  # Every hour
        ))

        now = datetime.now(UTC)
        next_run = repository.compute_next_run(schedule, now)

        assert next_run is not None
        # Should be at the top of an hour
        assert next_run.minute == 0
        assert next_run > now


class TestScheduleRepositoryRuns:
    """Tests for schedule run tracking."""

    def test_mark_run_started(self, repository):
        """Mark schedule run started."""
        schedule = repository.create(ScheduleCreate(
            name="run-test",
            target_type="workflow",
            target_name="test",
            cron_expression="0 0 * * *",
        ))

        schedule_run_id = repository.mark_run_started(schedule.id, "workflow-run-123")

        assert schedule_run_id is not None

        # Check schedule was updated
        updated = repository.get(schedule.id)
        assert updated.last_run_at is not None
        assert updated.last_run_status == "RUNNING"

    def test_mark_run_completed(self, repository):
        """Mark schedule run completed."""
        schedule = repository.create(ScheduleCreate(
            name="complete-test",
            target_type="workflow",
            target_name="test",
            schedule_type="interval",
            interval_seconds=300,
        ))

        repository.mark_run_started(schedule.id, "workflow-run-456")
        repository.mark_run_completed(schedule.id, "COMPLETED")

        updated = repository.get(schedule.id)
        assert updated.last_run_status == "COMPLETED"
        assert updated.next_run_at is not None

    def test_mark_run_failed(self, repository):
        """Mark schedule run failed with error."""
        schedule = repository.create(ScheduleCreate(
            name="fail-test",
            target_type="workflow",
            target_name="test",
            cron_expression="0 0 * * *",
        ))

        repository.mark_run_started(schedule.id, "workflow-run-789")
        repository.mark_run_completed(schedule.id, "FAILED", error="Connection timeout")

        updated = repository.get(schedule.id)
        assert updated.last_run_status == "FAILED"

    def test_list_runs(self, repository):
        """List schedule runs."""
        schedule = repository.create(ScheduleCreate(
            name="list-runs-test",
            target_type="workflow",
            target_name="test",
            cron_expression="0 0 * * *",
        ))

        # Create some runs
        repository.mark_run_started(schedule.id, "run-1")
        repository.mark_run_completed(schedule.id, "COMPLETED")

        repository.mark_run_started(schedule.id, "run-2")
        repository.mark_run_completed(schedule.id, "FAILED")

        runs = repository.list_runs(schedule.id)

        assert len(runs) >= 2
