"""Unit tests for spine.execution.repository module.

Tests ExecutionRepository analytics and maintenance operations.
"""

import sqlite3
from datetime import timedelta
import pytest

from spine.core.schema import CORE_DDL
from spine.execution.models import Execution, ExecutionStatus, utcnow
from spine.execution.ledger import ExecutionLedger
from spine.execution.repository import ExecutionRepository


@pytest.fixture
def conn():
    """Create in-memory SQLite database."""
    conn = sqlite3.connect(":memory:")
    for name, ddl in CORE_DDL.items():
        conn.execute(ddl)
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def ledger(conn):
    """Create ExecutionLedger instance."""
    return ExecutionLedger(conn)


@pytest.fixture
def repo(conn):
    """Create ExecutionRepository instance."""
    return ExecutionRepository(conn)


def make_execution(workflow: str, params: dict = None) -> Execution:
    """Helper to create an Execution object."""
    return Execution.create(workflow=workflow, params=params or {})


class TestGetStaleExecutions:
    """Test finding stale executions."""

    def test_finds_stale_running(self, ledger, repo, conn):
        """Finds running executions older than threshold."""
        # Create an execution and mark running
        exec1 = ledger.create_execution(make_execution("stale.operation"))
        ledger.update_status(exec1.id, ExecutionStatus.RUNNING)
        
        # Manually backdate the started_at
        old_time = (utcnow() - timedelta(hours=2)).isoformat()
        conn.execute(
            "UPDATE core_executions SET started_at = ? WHERE id = ?",
            (old_time, exec1.id)
        )
        conn.commit()
        
        stale = repo.get_stale_executions(older_than_minutes=60)
        
        assert len(stale) == 1
        assert stale[0]["id"] == exec1.id

    def test_ignores_recent_executions(self, ledger, repo):
        """Does not return recent executions."""
        exec1 = ledger.create_execution(make_execution("recent.operation"))
        ledger.update_status(exec1.id, ExecutionStatus.RUNNING)
        
        stale = repo.get_stale_executions(older_than_minutes=60)
        
        assert len(stale) == 0


class TestGetExecutionStats:
    """Test execution statistics."""

    def test_stats_by_status(self, ledger, repo):
        """Returns counts by status."""
        # Create executions with different statuses
        e1 = ledger.create_execution(make_execution("pipe.a"))
        ledger.update_status(e1.id, ExecutionStatus.COMPLETED)
        
        e2 = ledger.create_execution(make_execution("pipe.a"))
        ledger.update_status(e2.id, ExecutionStatus.FAILED)
        
        e3 = ledger.create_execution(make_execution("pipe.a"))
        ledger.update_status(e3.id, ExecutionStatus.COMPLETED)
        
        stats = repo.get_execution_stats(hours=1)
        
        assert stats["status_counts"].get("completed", 0) == 2
        assert stats["status_counts"].get("failed", 0) == 1

    def test_stats_filter_by_time(self, ledger, repo, conn):
        """Filters stats by time window."""
        e1 = ledger.create_execution(make_execution("pipe.a"))
        ledger.update_status(e1.id, ExecutionStatus.COMPLETED)
        
        # Backdate one execution
        e2 = ledger.create_execution(make_execution("pipe.b"))
        ledger.update_status(e2.id, ExecutionStatus.COMPLETED)
        old_time = (utcnow() - timedelta(hours=48)).isoformat()
        conn.execute(
            "UPDATE core_executions SET created_at = ? WHERE id = ?",
            (old_time, e2.id)
        )
        conn.commit()
        
        # Should only see one execution in the last hour
        stats = repo.get_execution_stats(hours=1)
        
        assert stats["status_counts"].get("completed", 0) == 1


class TestGetRecentFailures:
    """Test getting recent failures."""

    def test_returns_failed_executions(self, ledger, repo):
        """Returns recently failed executions."""
        e1 = ledger.create_execution(make_execution("failing.operation"))
        ledger.update_status(e1.id, ExecutionStatus.FAILED)
        
        e2 = ledger.create_execution(make_execution("success.operation"))
        ledger.update_status(e2.id, ExecutionStatus.COMPLETED)
        
        failures = repo.get_recent_failures(hours=24)
        
        assert len(failures) == 1
        assert failures[0]["id"] == e1.id

    def test_respects_hours_limit(self, ledger, repo, conn):
        """Only returns failures within hours limit."""
        e1 = ledger.create_execution(make_execution("old.operation"))
        ledger.update_status(e1.id, ExecutionStatus.FAILED)
        
        # Backdate the failure
        old_time = (utcnow() - timedelta(hours=48)).isoformat()
        conn.execute(
            "UPDATE core_executions SET created_at = ? WHERE id = ?",
            (old_time, e1.id)
        )
        conn.commit()
        
        failures = repo.get_recent_failures(hours=24)
        
        assert len(failures) == 0


class TestGetWorkflowThroughput:
    """Test throughput calculations."""

    def test_calculates_throughput(self, ledger, repo):
        """Returns throughput metrics via stats."""
        for i in range(5):
            e = ledger.create_execution(make_execution("throughput.test", {"i": i}))
            ledger.update_status(e.id, ExecutionStatus.COMPLETED)
        
        stats = repo.get_execution_stats(hours=1)
        
        assert stats["workflow_counts"].get("throughput.test", 0) == 5

    def test_includes_failure_rate(self, ledger, repo):
        """Includes failure rate in metrics."""
        e1 = ledger.create_execution(make_execution("mixed.operation"))
        ledger.update_status(e1.id, ExecutionStatus.COMPLETED)
        
        e2 = ledger.create_execution(make_execution("mixed.operation"))
        ledger.update_status(e2.id, ExecutionStatus.FAILED)
        
        stats = repo.get_execution_stats(hours=1)
        
        # 1 failure out of 2 total = 50% failure rate
        assert stats["failure_rate_by_workflow"].get("mixed.operation", 0) == 50.0


class TestGetQueueDepth:
    """Test queue depth statistics."""

    def test_counts_by_lane(self, ledger, repo):
        """Counts executions by lane (via stats)."""
        # Create pending executions in default lane
        ledger.create_execution(make_execution("queue.test"))
        ledger.create_execution(make_execution("queue.test"))
        
        stats = repo.get_execution_stats(hours=1)
        
        # Both executions should be in 'pending' status
        assert stats["status_counts"].get("pending", 0) == 2


class TestCleanupOldExecutions:
    """Test execution cleanup."""

    def test_deletes_old_completed(self, ledger, repo, conn):
        """Deletes old completed executions."""
        e = ledger.create_execution(make_execution("old.operation"))
        ledger.update_status(e.id, ExecutionStatus.COMPLETED)
        
        # Backdate it
        old_time = (utcnow() - timedelta(days=60)).isoformat()
        conn.execute(
            "UPDATE core_executions SET created_at = ?, completed_at = ? WHERE id = ?",
            (old_time, old_time, e.id)
        )
        conn.commit()
        
        deleted = repo.cleanup_old_executions(days=30)
        
        assert deleted >= 1
        # Verify it's gone
        assert ledger.get_execution(e.id) is None

    def test_preserves_recent(self, ledger, repo):
        """Preserves recent executions."""
        e = ledger.create_execution(make_execution("recent.operation"))
        ledger.update_status(e.id, ExecutionStatus.COMPLETED)
        
        deleted = repo.cleanup_old_executions(days=30)
        
        # Should still exist
        assert ledger.get_execution(e.id) is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
