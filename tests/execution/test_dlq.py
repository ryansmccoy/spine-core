"""Tests for DLQManager — dead letter queue for failed executions."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest

from spine.execution.dlq import DLQManager
from spine.execution.models import DeadLetter


# ── Fixtures ─────────────────────────────────────────────────────────────


@pytest.fixture()
def conn():
    """In-memory SQLite with dead_letters table."""
    db = sqlite3.connect(":memory:")
    db.execute("""
        CREATE TABLE core_dead_letters (
            id TEXT PRIMARY KEY,
            execution_id TEXT NOT NULL,
            workflow TEXT NOT NULL,
            params TEXT DEFAULT '{}',
            error TEXT NOT NULL,
            retry_count INTEGER DEFAULT 0,
            max_retries INTEGER DEFAULT 3,
            created_at TEXT NOT NULL,
            last_retry_at TEXT,
            resolved_at TEXT,
            resolved_by TEXT
        )
    """)
    db.commit()
    yield db
    db.close()


@pytest.fixture()
def dlq(conn):
    return DLQManager(conn, max_retries=3)


# ── Add ──────────────────────────────────────────────────────────────────


class TestAddToDLQ:
    def test_add_returns_dead_letter(self, dlq):
        entry = dlq.add_to_dlq(
            execution_id="e1",
            workflow="test.operation",
            params={"k": "v"},
            error="boom",
        )
        assert isinstance(entry, DeadLetter)
        assert entry.execution_id == "e1"
        assert entry.error == "boom"
        assert entry.retry_count == 0
        assert entry.max_retries == 3

    def test_add_custom_max_retries(self, dlq):
        entry = dlq.add_to_dlq(
            execution_id="e1",
            workflow="p",
            params={},
            error="err",
            max_retries=10,
        )
        assert entry.max_retries == 10

    def test_add_with_retry_count(self, dlq):
        entry = dlq.add_to_dlq(
            execution_id="e1",
            workflow="p",
            params={},
            error="err",
            retry_count=2,
        )
        assert entry.retry_count == 2


# ── Get ──────────────────────────────────────────────────────────────────


class TestGet:
    def test_get_existing(self, dlq):
        entry = dlq.add_to_dlq("e1", "p", {}, "err")
        found = dlq.get(entry.id)
        assert found is not None
        assert found.id == entry.id
        assert found.execution_id == "e1"

    def test_get_nonexistent(self, dlq):
        assert dlq.get("no-such-id") is None


# ── List ─────────────────────────────────────────────────────────────────


class TestList:
    def test_list_unresolved(self, dlq):
        dlq.add_to_dlq("e1", "p1", {}, "err1")
        dlq.add_to_dlq("e2", "p2", {}, "err2")
        entries = dlq.list_unresolved()
        assert len(entries) == 2

    def test_list_unresolved_excludes_resolved(self, dlq):
        entry = dlq.add_to_dlq("e1", "p1", {}, "err1")
        dlq.resolve(entry.id)
        entries = dlq.list_unresolved()
        assert len(entries) == 0

    def test_list_unresolved_filter_operation(self, dlq):
        dlq.add_to_dlq("e1", "a.pipe", {}, "err1")
        dlq.add_to_dlq("e2", "b.pipe", {}, "err2")
        entries = dlq.list_unresolved(workflow="a.pipe")
        assert len(entries) == 1
        assert entries[0].execution_id == "e1"

    def test_list_all(self, dlq):
        entry = dlq.add_to_dlq("e1", "p1", {}, "err1")
        dlq.add_to_dlq("e2", "p2", {}, "err2")
        dlq.resolve(entry.id)
        all_entries = dlq.list_all()
        assert len(all_entries) == 2

    def test_list_all_exclude_resolved(self, dlq):
        entry = dlq.add_to_dlq("e1", "p1", {}, "err1")
        dlq.add_to_dlq("e2", "p2", {}, "err2")
        dlq.resolve(entry.id)
        entries = dlq.list_all(include_resolved=False)
        assert len(entries) == 1

    def test_list_limit(self, dlq):
        for i in range(5):
            dlq.add_to_dlq(f"e{i}", "p", {}, "err")
        entries = dlq.list_unresolved(limit=2)
        assert len(entries) == 2


# ── Retry ────────────────────────────────────────────────────────────────


class TestRetry:
    def test_mark_retry_attempted(self, dlq):
        entry = dlq.add_to_dlq("e1", "p", {}, "err")
        assert dlq.mark_retry_attempted(entry.id) is True
        updated = dlq.get(entry.id)
        assert updated.retry_count == 1
        assert updated.last_retry_at is not None

    def test_retry_nonexistent(self, dlq):
        assert dlq.mark_retry_attempted("no-id") is False

    def test_can_retry(self, dlq):
        entry = dlq.add_to_dlq("e1", "p", {}, "err", max_retries=2)
        assert dlq.can_retry(entry.id) is True
        dlq.mark_retry_attempted(entry.id)
        dlq.mark_retry_attempted(entry.id)
        assert dlq.can_retry(entry.id) is False

    def test_can_retry_resolved(self, dlq):
        entry = dlq.add_to_dlq("e1", "p", {}, "err")
        dlq.resolve(entry.id)
        assert dlq.can_retry(entry.id) is False

    def test_can_retry_nonexistent(self, dlq):
        assert dlq.can_retry("no-id") is False


# ── Resolve ──────────────────────────────────────────────────────────────


class TestResolve:
    def test_resolve(self, dlq):
        entry = dlq.add_to_dlq("e1", "p", {}, "err")
        assert dlq.resolve(entry.id, resolved_by="admin") is True
        resolved = dlq.get(entry.id)
        assert resolved.resolved_at is not None
        assert resolved.resolved_by == "admin"

    def test_resolve_already_resolved(self, dlq):
        entry = dlq.add_to_dlq("e1", "p", {}, "err")
        dlq.resolve(entry.id)
        assert dlq.resolve(entry.id) is False

    def test_resolve_nonexistent(self, dlq):
        assert dlq.resolve("no-id") is False


# ── Count / Cleanup ─────────────────────────────────────────────────────


class TestCountAndCleanup:
    def test_count_unresolved(self, dlq):
        dlq.add_to_dlq("e1", "p1", {}, "err")
        dlq.add_to_dlq("e2", "p2", {}, "err")
        assert dlq.count_unresolved() == 2

    def test_count_unresolved_by_operation(self, dlq):
        dlq.add_to_dlq("e1", "a.pipe", {}, "err")
        dlq.add_to_dlq("e2", "b.pipe", {}, "err")
        assert dlq.count_unresolved(workflow="a.pipe") == 1

    def test_cleanup_resolved(self, dlq):
        entry = dlq.add_to_dlq("e1", "p", {}, "err")
        dlq.resolve(entry.id)
        # Default 90 days — entry is too new to clean
        assert dlq.cleanup_resolved(days=90) == 0
        # Force old timestamp
        past = datetime.now(UTC) - timedelta(days=91)
        with patch("spine.execution.dlq.utcnow", return_value=past):
            old_entry = dlq.add_to_dlq("e2", "p", {}, "err")
            dlq.resolve(old_entry.id)
        # Now cleanup should find the old resolved one
        assert dlq.cleanup_resolved(days=90) >= 1
