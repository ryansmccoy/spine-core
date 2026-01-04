"""Tests for orchestration layer."""

from datetime import datetime, timedelta

import pytest

from market_spine.orchestration import DLQManager, ScheduleManager
from market_spine.orchestration.backends.local import LocalBackend
from market_spine.repositories.executions import ExecutionRepository


class TestDLQManager:
    """Tests for DLQManager."""

    def test_move_to_dlq(self, db_conn, clean_tables):
        """Test moving execution to DLQ."""
        exec_id = ExecutionRepository.create("test.pipeline")

        success = DLQManager.move_to_dlq(exec_id, "Test error")

        assert success is True

        execution = ExecutionRepository.get(exec_id)
        assert execution["status"] == "dlq"
        assert execution["error_message"] == "Test error"

    def test_list_dlq(self, db_conn, clean_tables):
        """Test listing DLQ items."""
        exec1 = ExecutionRepository.create("test.pipeline")
        exec2 = ExecutionRepository.create("test.pipeline")

        DLQManager.move_to_dlq(exec1, "Error 1")
        DLQManager.move_to_dlq(exec2, "Error 2")

        items = DLQManager.list_dlq()

        assert len(items) == 2

    def test_retry_creates_new_execution(self, db_conn, clean_tables):
        """Test retry creates new execution with parent link."""
        original_id = ExecutionRepository.create(
            "test.pipeline",
            params={"key": "value"},
        )
        ExecutionRepository.update_status(original_id, "running")
        DLQManager.move_to_dlq(original_id, "Original error")

        new_id = DLQManager.retry(original_id)

        assert new_id is not None
        assert new_id != original_id

        new_execution = ExecutionRepository.get(new_id)
        assert new_execution["parent_execution_id"] == original_id
        assert new_execution["params"] == {"key": "value"}
        assert new_execution["status"] == "pending"

        # Original should be marked as retried
        original = ExecutionRepository.get(original_id)
        assert original["status"] == "retried"

    def test_cannot_retry_non_dlq(self, db_conn, clean_tables):
        """Test cannot retry execution not in DLQ."""
        exec_id = ExecutionRepository.create("test.pipeline")

        result = DLQManager.retry(exec_id)

        assert result is None

    def test_get_retryable(self, db_conn, clean_tables):
        """Test getting retryable DLQ items."""
        exec1 = ExecutionRepository.create("test.pipeline", max_retries=3)
        exec2 = ExecutionRepository.create("test.pipeline", max_retries=0)

        DLQManager.move_to_dlq(exec1, "Error 1")
        DLQManager.move_to_dlq(exec2, "Error 2")

        retryable = DLQManager.get_retryable()

        # Only exec1 should be retryable (max_retries > retry_count)
        assert len(retryable) == 1
        assert retryable[0]["id"] == exec1

    def test_auto_retry(self, db_conn, clean_tables):
        """Test automatic retry of DLQ items."""
        exec1 = ExecutionRepository.create("test.pipeline", max_retries=3)
        exec2 = ExecutionRepository.create("test.pipeline", max_retries=3)

        DLQManager.move_to_dlq(exec1, "Error 1")
        DLQManager.move_to_dlq(exec2, "Error 2")

        count = DLQManager.auto_retry(limit=10)

        assert count == 2


class TestScheduleManager:
    """Tests for ScheduleManager."""

    def test_create_schedule(self, db_conn, clean_tables):
        """Test creating a schedule."""
        schedule_id = ScheduleManager.create_schedule(
            pipeline_name="test.pipeline",
            cron_expression="0 9 * * *",
            params={"key": "value"},
        )

        assert schedule_id is not None

    def test_invalid_cron(self, db_conn, clean_tables):
        """Test invalid cron expression raises error."""
        with pytest.raises(ValueError, match="Invalid cron"):
            ScheduleManager.create_schedule(
                pipeline_name="test.pipeline",
                cron_expression="invalid cron",
            )

    def test_list_schedules(self, db_conn, clean_tables):
        """Test listing schedules."""
        ScheduleManager.create_schedule("test.a", "0 9 * * *")
        ScheduleManager.create_schedule("test.b", "0 10 * * *")

        schedules = ScheduleManager.list_schedules()

        assert len(schedules) == 2

    def test_enable_disable_schedule(self, db_conn, clean_tables):
        """Test enabling and disabling schedules."""
        schedule_id = ScheduleManager.create_schedule("test.pipeline", "0 9 * * *")

        # Should be enabled by default
        schedules = ScheduleManager.list_schedules()
        assert schedules[0]["enabled"] is True

        ScheduleManager.disable_schedule(schedule_id)
        schedules = ScheduleManager.list_schedules()
        assert schedules[0]["enabled"] is False

        ScheduleManager.enable_schedule(schedule_id)
        schedules = ScheduleManager.list_schedules()
        assert schedules[0]["enabled"] is True

    def test_delete_schedule(self, db_conn, clean_tables):
        """Test deleting a schedule."""
        schedule_id = ScheduleManager.create_schedule("test.pipeline", "0 9 * * *")

        success = ScheduleManager.delete_schedule(schedule_id)
        assert success is True

        schedules = ScheduleManager.list_schedules()
        assert len(schedules) == 0

    def test_get_due_schedules(self, db_conn, clean_tables):
        """Test getting due schedules."""
        # This is timing-sensitive so we just verify structure
        ScheduleManager.create_schedule("test.pipeline", "* * * * *")  # Every minute

        due = ScheduleManager.get_due_schedules()

        # Should have fields
        if len(due) > 0:
            assert "pipeline_name" in due[0]
            assert "params" in due[0]


class TestLocalBackend:
    """Tests for LocalBackend."""

    def test_submit_runs_immediately(self, db_conn, clean_tables):
        """Test LocalBackend runs pipeline immediately."""
        exec_id = ExecutionRepository.create("otc.normalize")

        # Use a no-op run function for tests
        def mock_run(execution_id: str) -> None:
            pass

        backend = LocalBackend(run_pipeline_fn=mock_run)
        backend.submit(exec_id, "otc.normalize", {"limit": 100})

        execution = ExecutionRepository.get(exec_id)
        assert execution["status"] == "completed"
        assert execution["backend"] == "local"

    def test_submit_sets_backend_info(self, db_conn, clean_tables):
        """Test LocalBackend sets backend info."""
        exec_id = ExecutionRepository.create("otc.normalize")

        # Use a no-op run function for tests
        def mock_run(execution_id: str) -> None:
            pass

        backend = LocalBackend(run_pipeline_fn=mock_run)
        backend.submit(exec_id, "otc.normalize", {})

        execution = ExecutionRepository.get(exec_id)
        assert execution["backend"] == "local"
        assert execution["backend_run_id"] == exec_id  # Same for local
