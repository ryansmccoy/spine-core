"""Unit tests for spine.execution.dlq module.

Tests DLQManager dead letter queue operations.
"""

import sqlite3
import pytest

from spine.core.schema import CORE_DDL
from spine.execution.dlq import DLQManager


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
def dlq(conn):
    """Create DLQManager instance."""
    return DLQManager(conn, max_retries=3)


class TestAddToDlq:
    """Test adding entries to DLQ."""

    def test_add_creates_entry(self, dlq):
        """Adding creates a DLQ entry."""
        entry = dlq.add_to_dlq(
            execution_id="exec-123",
            pipeline="test.pipeline",
            params={"key": "value"},
            error="Connection error",
        )
        
        assert entry.id is not None
        assert entry.execution_id == "exec-123"
        assert entry.pipeline == "test.pipeline"
        assert entry.error == "Connection error"

    def test_add_uses_default_max_retries(self, dlq):
        """Uses manager's default max_retries."""
        entry = dlq.add_to_dlq(
            execution_id="exec-123",
            pipeline="test.pipeline",
            params={},
            error="Error",
        )
        
        assert entry.max_retries == 3

    def test_add_with_custom_max_retries(self, dlq):
        """Can override max_retries."""
        entry = dlq.add_to_dlq(
            execution_id="exec-123",
            pipeline="test.pipeline",
            params={},
            error="Error",
            max_retries=5,
        )
        
        assert entry.max_retries == 5

    def test_add_preserves_retry_count(self, dlq):
        """Preserves provided retry count."""
        entry = dlq.add_to_dlq(
            execution_id="exec-123",
            pipeline="test.pipeline",
            params={},
            error="Error",
            retry_count=2,
        )
        
        assert entry.retry_count == 2


class TestGet:
    """Test getting DLQ entries."""

    def test_get_existing(self, dlq):
        """Can retrieve existing entry."""
        entry = dlq.add_to_dlq(
            execution_id="exec-123",
            pipeline="test.pipeline",
            params={"key": "value"},
            error="Error",
        )
        
        retrieved = dlq.get(entry.id)
        
        assert retrieved is not None
        assert retrieved.id == entry.id
        assert retrieved.execution_id == "exec-123"

    def test_get_nonexistent(self, dlq):
        """Returns None for nonexistent entry."""
        retrieved = dlq.get("nonexistent-id")
        assert retrieved is None


class TestListUnresolved:
    """Test listing unresolved entries."""

    def test_list_all_unresolved(self, dlq):
        """Lists all unresolved entries."""
        dlq.add_to_dlq("exec-1", "pipeline.a", {}, "Error 1")
        dlq.add_to_dlq("exec-2", "pipeline.b", {}, "Error 2")
        
        unresolved = dlq.list_unresolved()
        
        assert len(unresolved) == 2

    def test_list_excludes_resolved(self, dlq):
        """Excludes resolved entries."""
        entry = dlq.add_to_dlq("exec-1", "pipeline.a", {}, "Error")
        dlq.add_to_dlq("exec-2", "pipeline.b", {}, "Error")
        dlq.resolve(entry.id)
        
        unresolved = dlq.list_unresolved()
        
        assert len(unresolved) == 1

    def test_list_filter_by_pipeline(self, dlq):
        """Filter by pipeline name."""
        dlq.add_to_dlq("exec-1", "pipeline.a", {}, "Error 1")
        dlq.add_to_dlq("exec-2", "pipeline.a", {}, "Error 2")
        dlq.add_to_dlq("exec-3", "pipeline.b", {}, "Error 3")
        
        unresolved = dlq.list_unresolved(pipeline="pipeline.a")
        
        assert len(unresolved) == 2


class TestListAll:
    """Test listing all entries."""

    def test_list_includes_resolved(self, dlq):
        """Can include resolved entries."""
        entry = dlq.add_to_dlq("exec-1", "pipeline.a", {}, "Error")
        dlq.add_to_dlq("exec-2", "pipeline.b", {}, "Error")
        dlq.resolve(entry.id)
        
        all_entries = dlq.list_all(include_resolved=True)
        
        assert len(all_entries) == 2

    def test_list_can_exclude_resolved(self, dlq):
        """Can exclude resolved entries."""
        entry = dlq.add_to_dlq("exec-1", "pipeline.a", {}, "Error")
        dlq.add_to_dlq("exec-2", "pipeline.b", {}, "Error")
        dlq.resolve(entry.id)
        
        active = dlq.list_all(include_resolved=False)
        
        assert len(active) == 1


class TestMarkRetryAttempted:
    """Test marking retry attempts."""

    def test_mark_increments_retry_count(self, dlq):
        """Marking retry increments the count."""
        entry = dlq.add_to_dlq("exec-123", "test", {}, "Error", retry_count=0)
        
        dlq.mark_retry_attempted(entry.id)
        
        updated = dlq.get(entry.id)
        assert updated.retry_count == 1

    def test_mark_sets_last_retry_at(self, dlq):
        """Marking retry sets last_retry_at."""
        entry = dlq.add_to_dlq("exec-123", "test", {}, "Error")
        
        dlq.mark_retry_attempted(entry.id)
        
        updated = dlq.get(entry.id)
        assert updated.last_retry_at is not None


class TestResolve:
    """Test resolving entries."""

    def test_resolve_sets_resolved_at(self, dlq):
        """Resolving sets resolved_at timestamp."""
        entry = dlq.add_to_dlq("exec-123", "test", {}, "Error")
        
        result = dlq.resolve(entry.id)
        
        assert result is True
        resolved = dlq.get(entry.id)
        assert resolved.resolved_at is not None

    def test_resolve_sets_resolved_by(self, dlq):
        """Resolving sets resolved_by."""
        entry = dlq.add_to_dlq("exec-123", "test", {}, "Error")
        
        dlq.resolve(entry.id, resolved_by="admin@example.com")
        
        resolved = dlq.get(entry.id)
        assert resolved.resolved_by == "admin@example.com"

    def test_cannot_resolve_twice(self, dlq):
        """Cannot resolve already-resolved entry."""
        entry = dlq.add_to_dlq("exec-123", "test", {}, "Error")
        
        dlq.resolve(entry.id)
        result = dlq.resolve(entry.id)
        
        assert result is False


class TestCanRetry:
    """Test retry eligibility checking."""

    def test_can_retry_under_limit(self, dlq):
        """Can retry when under limit."""
        entry = dlq.add_to_dlq("exec-123", "test", {}, "Error", retry_count=1, max_retries=3)
        
        assert dlq.can_retry(entry.id) is True

    def test_cannot_retry_at_limit(self, dlq):
        """Cannot retry when at limit."""
        entry = dlq.add_to_dlq("exec-123", "test", {}, "Error", retry_count=3, max_retries=3)
        
        assert dlq.can_retry(entry.id) is False

    def test_cannot_retry_when_resolved(self, dlq):
        """Cannot retry resolved entry."""
        entry = dlq.add_to_dlq("exec-123", "test", {}, "Error", retry_count=0)
        dlq.resolve(entry.id)
        
        assert dlq.can_retry(entry.id) is False


class TestCountUnresolved:
    """Test counting unresolved entries."""

    def test_count_all(self, dlq):
        """Count all unresolved."""
        dlq.add_to_dlq("exec-1", "pipeline.a", {}, "Error")
        dlq.add_to_dlq("exec-2", "pipeline.b", {}, "Error")
        
        assert dlq.count_unresolved() == 2

    def test_count_by_pipeline(self, dlq):
        """Count by pipeline."""
        dlq.add_to_dlq("exec-1", "pipeline.a", {}, "Error")
        dlq.add_to_dlq("exec-2", "pipeline.a", {}, "Error")
        dlq.add_to_dlq("exec-3", "pipeline.b", {}, "Error")
        
        assert dlq.count_unresolved(pipeline="pipeline.a") == 2
        assert dlq.count_unresolved(pipeline="pipeline.b") == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
