"""Tests for ExecutionLedger — CRUD for executions and events."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

from spine.execution.ledger import ExecutionLedger
from spine.execution.models import (
    EventType,
    Execution,
    ExecutionStatus,
    TriggerSource,
)


# ── Fixtures ─────────────────────────────────────────────────────────────


@pytest.fixture()
def conn():
    """In-memory SQLite with executions + events tables."""
    db = sqlite3.connect(":memory:")
    db.execute("""
        CREATE TABLE core_executions (
            id TEXT PRIMARY KEY,
            workflow TEXT NOT NULL,
            params TEXT DEFAULT '{}',
            status TEXT NOT NULL DEFAULT 'pending',
            lane TEXT DEFAULT 'default',
            trigger_source TEXT DEFAULT 'api',
            parent_execution_id TEXT,
            created_at TEXT NOT NULL,
            started_at TEXT,
            completed_at TEXT,
            result TEXT,
            error TEXT,
            retry_count INTEGER DEFAULT 0,
            idempotency_key TEXT
        )
    """)
    db.execute("""
        CREATE TABLE core_execution_events (
            id TEXT PRIMARY KEY,
            execution_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            data TEXT DEFAULT '{}'
        )
    """)
    db.commit()
    yield db
    db.close()


@pytest.fixture()
def ledger(conn):
    return ExecutionLedger(conn)


def _make_execution(**kwargs) -> Execution:
    defaults = {
        "workflow": "test.operation",
        "params": {},
        "lane": "default",
        "trigger_source": TriggerSource.API,
    }
    defaults.update(kwargs)
    return Execution.create(**defaults)


# ── Create / Get ─────────────────────────────────────────────────────────


class TestCreateGet:
    def test_create_and_get(self, ledger):
        ex = _make_execution()
        ledger.create_execution(ex)
        found = ledger.get_execution(ex.id)
        assert found is not None
        assert found.id == ex.id
        assert found.workflow == "test.operation"
        assert found.status == ExecutionStatus.PENDING

    def test_get_nonexistent(self, ledger):
        assert ledger.get_execution("no-such-id") is None

    def test_create_records_event(self, ledger):
        ex = _make_execution()
        ledger.create_execution(ex)
        events = ledger.get_events(ex.id)
        assert len(events) >= 1
        assert events[0].event_type == EventType.CREATED

    def test_idempotency_key_lookup(self, ledger):
        ex = _make_execution(idempotency_key="idem-1")
        ledger.create_execution(ex)
        found = ledger.get_by_idempotency_key("idem-1")
        assert found is not None
        assert found.id == ex.id

    def test_idempotency_key_not_found(self, ledger):
        assert ledger.get_by_idempotency_key("nonexistent") is None


# ── Update Status ────────────────────────────────────────────────────────


class TestUpdateStatus:
    def test_update_to_running(self, ledger):
        ex = _make_execution()
        ledger.create_execution(ex)
        ledger.update_status(ex.id, ExecutionStatus.RUNNING)
        found = ledger.get_execution(ex.id)
        assert found.status == ExecutionStatus.RUNNING
        assert found.started_at is not None

    def test_update_to_completed(self, ledger):
        ex = _make_execution()
        ledger.create_execution(ex)
        ledger.update_status(ex.id, ExecutionStatus.RUNNING)
        ledger.update_status(
            ex.id,
            ExecutionStatus.COMPLETED,
            result={"output": "data"},
        )
        found = ledger.get_execution(ex.id)
        assert found.status == ExecutionStatus.COMPLETED
        assert found.completed_at is not None
        assert found.result == {"output": "data"}

    def test_update_to_failed(self, ledger):
        ex = _make_execution()
        ledger.create_execution(ex)
        ledger.update_status(ex.id, ExecutionStatus.RUNNING)
        ledger.update_status(
            ex.id,
            ExecutionStatus.FAILED,
            error="Connection refused",
        )
        found = ledger.get_execution(ex.id)
        assert found.status == ExecutionStatus.FAILED
        assert found.error == "Connection refused"

    def test_update_records_event(self, ledger):
        ex = _make_execution()
        ledger.create_execution(ex)
        ledger.update_status(ex.id, ExecutionStatus.RUNNING)
        events = ledger.get_events(ex.id)
        event_types = [e.event_type for e in events]
        assert EventType.STARTED in event_types


# ── Increment Retry ─────────────────────────────────────────────────────


class TestIncrementRetry:
    def test_increment(self, ledger):
        ex = _make_execution()
        ledger.create_execution(ex)
        count = ledger.increment_retry(ex.id)
        assert count == 1
        count2 = ledger.increment_retry(ex.id)
        assert count2 == 2

    def test_increment_records_event(self, ledger):
        ex = _make_execution()
        ledger.create_execution(ex)
        ledger.increment_retry(ex.id)
        events = ledger.get_events(ex.id)
        event_types = [e.event_type for e in events]
        assert EventType.RETRIED in event_types


# ── List ─────────────────────────────────────────────────────────────────


class TestListExecutions:
    def test_list_all(self, ledger):
        for i in range(3):
            ledger.create_execution(_make_execution())
        results = ledger.list_executions()
        assert len(results) == 3

    def test_list_by_workflow(self, ledger):
        ledger.create_execution(_make_execution(workflow="a.pipe"))
        ledger.create_execution(_make_execution(workflow="b.pipe"))
        results = ledger.list_executions(workflow="a.pipe")
        assert len(results) == 1
        assert results[0].workflow == "a.pipe"

    def test_list_by_status(self, ledger):
        ex1 = _make_execution()
        ex2 = _make_execution()
        ledger.create_execution(ex1)
        ledger.create_execution(ex2)
        ledger.update_status(ex1.id, ExecutionStatus.RUNNING)
        results = ledger.list_executions(status=ExecutionStatus.RUNNING)
        assert len(results) == 1

    def test_list_limit(self, ledger):
        for i in range(5):
            ledger.create_execution(_make_execution())
        results = ledger.list_executions(limit=2)
        assert len(results) == 2

    def test_list_since(self, ledger):
        ex = _make_execution()
        ledger.create_execution(ex)
        # Listing since the future should return nothing
        future = datetime.now(UTC) + timedelta(hours=1)
        results = ledger.list_executions(since=future)
        assert len(results) == 0


# ── Events ───────────────────────────────────────────────────────────────


class TestEvents:
    def test_record_and_get(self, ledger):
        ex = _make_execution()
        ledger.create_execution(ex)
        ledger.record_event(ex.id, EventType.PROGRESS, {"step": 1})
        events = ledger.get_events(ex.id)
        progress_events = [e for e in events if e.event_type == EventType.PROGRESS]
        assert len(progress_events) == 1
        assert progress_events[0].data["step"] == 1

    def test_events_chronological(self, ledger):
        ex = _make_execution()
        ledger.create_execution(ex)
        ledger.record_event(ex.id, EventType.PROGRESS, {"step": 1})
        ledger.record_event(ex.id, EventType.PROGRESS, {"step": 2})
        events = ledger.get_events(ex.id)
        # Should be in chronological order
        timestamps = [e.timestamp for e in events]
        assert timestamps == sorted(timestamps)
