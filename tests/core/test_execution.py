"""
Tests for spine.core.execution module.

Tests cover:
- ExecutionContext creation
- Child context creation (lineage)
- Batch ID generation
- Context with batch assignment
"""

import pytest
from datetime import datetime
import uuid

from spine.core.execution import (
    ExecutionContext,
    new_context,
    new_batch_id,
)


class TestExecutionContext:
    """Tests for ExecutionContext dataclass."""

    def test_context_creation_defaults(self):
        """Test ExecutionContext with default values."""
        ctx = ExecutionContext()
        
        assert ctx.execution_id is not None
        assert len(ctx.execution_id) == 36  # UUID format
        assert ctx.batch_id is None
        assert ctx.parent_execution_id is None
        assert ctx.started_at is not None

    def test_context_with_batch_id(self):
        """Test ExecutionContext with explicit batch_id."""
        ctx = ExecutionContext(batch_id="batch_123")
        
        assert ctx.batch_id == "batch_123"

    def test_context_with_parent(self):
        """Test ExecutionContext with parent execution ID."""
        parent_id = str(uuid.uuid4())
        ctx = ExecutionContext(parent_execution_id=parent_id)
        
        assert ctx.parent_execution_id == parent_id

    def test_context_started_at_is_datetime(self):
        """Test that started_at is a datetime instance."""
        from datetime import timezone
        before = datetime.now(timezone.utc)
        ctx = ExecutionContext()
        after = datetime.now(timezone.utc)
        
        assert isinstance(ctx.started_at, datetime)
        # Note: ExecutionContext uses utcnow() which is naive, so we compare
        # just that started_at is a datetime (no timezone comparison)


class TestContextChild:
    """Tests for ExecutionContext.child() method."""

    def test_child_has_new_execution_id(self):
        """Test that child context has a new execution ID."""
        parent = ExecutionContext()
        child = parent.child()
        
        assert child.execution_id != parent.execution_id

    def test_child_references_parent(self):
        """Test that child context references parent execution ID."""
        parent = ExecutionContext()
        child = parent.child()
        
        assert child.parent_execution_id == parent.execution_id

    def test_child_inherits_batch_id(self):
        """Test that child inherits parent's batch_id."""
        parent = ExecutionContext(batch_id="inherited_batch")
        child = parent.child()
        
        assert child.batch_id == "inherited_batch"

    def test_child_has_new_started_at(self):
        """Test that child has its own started_at timestamp."""
        parent = ExecutionContext()
        child = parent.child()
        
        # Child should have its own timestamp (may be same or later)
        assert child.started_at >= parent.started_at

    def test_grandchild_maintains_lineage(self):
        """Test lineage through multiple generations."""
        grandparent = ExecutionContext(batch_id="family_batch")
        parent = grandparent.child()
        child = parent.child()
        
        # Child references parent, not grandparent
        assert child.parent_execution_id == parent.execution_id
        assert child.parent_execution_id != grandparent.execution_id
        
        # Batch ID is preserved through generations
        assert child.batch_id == "family_batch"


class TestContextWithBatch:
    """Tests for ExecutionContext.with_batch() method."""

    def test_with_batch_sets_batch_id(self):
        """Test that with_batch sets the batch_id."""
        ctx = ExecutionContext()
        ctx_with_batch = ctx.with_batch("new_batch_id")
        
        assert ctx_with_batch.batch_id == "new_batch_id"

    def test_with_batch_preserves_execution_id(self):
        """Test that with_batch preserves the execution_id."""
        ctx = ExecutionContext()
        ctx_with_batch = ctx.with_batch("batch")
        
        assert ctx_with_batch.execution_id == ctx.execution_id

    def test_with_batch_preserves_parent_id(self):
        """Test that with_batch preserves the parent_execution_id."""
        ctx = ExecutionContext(parent_execution_id="parent-123")
        ctx_with_batch = ctx.with_batch("batch")
        
        assert ctx_with_batch.parent_execution_id == "parent-123"

    def test_with_batch_preserves_started_at(self):
        """Test that with_batch preserves the started_at."""
        ctx = ExecutionContext()
        ctx_with_batch = ctx.with_batch("batch")
        
        assert ctx_with_batch.started_at == ctx.started_at

    def test_original_context_unchanged(self):
        """Test that with_batch doesn't modify the original context."""
        ctx = ExecutionContext()
        original_batch = ctx.batch_id
        
        ctx.with_batch("new_batch")
        
        assert ctx.batch_id == original_batch


class TestNewContext:
    """Tests for new_context() factory function."""

    def test_new_context_creates_fresh_context(self):
        """Test new_context creates a fresh ExecutionContext."""
        ctx = new_context()
        
        assert isinstance(ctx, ExecutionContext)
        assert ctx.execution_id is not None
        assert ctx.parent_execution_id is None

    def test_new_context_with_batch(self):
        """Test new_context with batch_id parameter."""
        ctx = new_context(batch_id="specified_batch")
        
        assert ctx.batch_id == "specified_batch"

    def test_new_context_generates_unique_ids(self):
        """Test that each call generates a unique execution_id."""
        ctx1 = new_context()
        ctx2 = new_context()
        
        assert ctx1.execution_id != ctx2.execution_id


class TestNewBatchId:
    """Tests for new_batch_id() function."""

    def test_new_batch_id_format(self):
        """Test batch ID format: {prefix}_{timestamp}_{short_uuid}."""
        batch_id = new_batch_id("backfill")
        
        parts = batch_id.split("_")
        assert len(parts) >= 3
        assert parts[0] == "backfill"
        # Second part should be a timestamp
        assert len(parts[1]) == 15  # YYYYMMDDTHHmmss format

    def test_new_batch_id_without_prefix(self):
        """Test batch ID without prefix."""
        batch_id = new_batch_id()
        
        assert batch_id.startswith("batch_")

    def test_new_batch_id_empty_prefix(self):
        """Test batch ID with empty prefix."""
        batch_id = new_batch_id("")
        
        assert batch_id.startswith("batch_")

    def test_new_batch_id_unique(self):
        """Test that batch IDs are unique."""
        ids = [new_batch_id("test") for _ in range(10)]
        
        assert len(set(ids)) == 10  # All unique

    def test_new_batch_id_contains_timestamp(self):
        """Test that batch ID contains a valid timestamp."""
        batch_id = new_batch_id("prefix")
        
        # Extract timestamp part
        parts = batch_id.split("_")
        timestamp_part = parts[1]
        
        # Should be parseable as a timestamp
        try:
            datetime.strptime(timestamp_part, "%Y%m%dT%H%M%S")
        except ValueError:
            pytest.fail(f"Invalid timestamp in batch_id: {timestamp_part}")
