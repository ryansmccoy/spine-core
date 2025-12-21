"""Tests for data retention and purge utilities."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from spine.core.retention import (
    PurgeResult,
    RetentionConfig,
    RetentionReport,
    compute_cutoff,
    get_table_counts,
    purge_all,
    purge_anomalies,
    purge_executions,
    purge_quality,
    purge_rejects,
    purge_table,
    purge_work_items,
)


# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture()
def conn():
    """In-memory SQLite connection with test tables."""
    c = sqlite3.connect(":memory:")
    # Create minimal versions of the core tables
    c.executescript("""
        CREATE TABLE core_executions (
            id TEXT PRIMARY KEY,
            operation TEXT,
            created_at TEXT
        );
        CREATE TABLE core_rejects (
            id INTEGER PRIMARY KEY,
            domain TEXT,
            created_at TEXT
        );
        CREATE TABLE core_quality (
            id INTEGER PRIMARY KEY,
            domain TEXT,
            created_at TEXT
        );
        CREATE TABLE core_anomalies (
            id INTEGER PRIMARY KEY,
            domain TEXT,
            created_at TEXT
        );
        CREATE TABLE core_work_items (
            id INTEGER PRIMARY KEY,
            domain TEXT,
            state TEXT,
            completed_at TEXT
        );
    """)
    yield c
    c.close()


def _insert_old_and_new(conn: sqlite3.Connection, table: str, ts_column: str):
    """Insert 3 old records and 2 new records into a table."""
    old_ts = (datetime.now(timezone.utc) - timedelta(days=100)).strftime("%Y-%m-%dT%H:%M:%S")
    new_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

    if table == "core_executions":
        for i in range(3):
            conn.execute(
                "INSERT INTO core_executions (id, operation, created_at) VALUES (?, ?, ?)",
                (f"old-{i}", "test", old_ts),
            )
        for i in range(2):
            conn.execute(
                "INSERT INTO core_executions (id, operation, created_at) VALUES (?, ?, ?)",
                (f"new-{i}", "test", new_ts),
            )
    elif table == "core_work_items":
        for i in range(3):
            conn.execute(
                "INSERT INTO core_work_items (domain, state, completed_at) VALUES (?, ?, ?)",
                ("test", "COMPLETE", old_ts),
            )
        for i in range(2):
            conn.execute(
                "INSERT INTO core_work_items (domain, state, completed_at) VALUES (?, ?, ?)",
                ("test", "COMPLETE", new_ts),
            )
    else:
        for i in range(3):
            conn.execute(
                f"INSERT INTO {table} (domain, {ts_column}) VALUES (?, ?)",
                ("test", old_ts),
            )
        for i in range(2):
            conn.execute(
                f"INSERT INTO {table} (domain, {ts_column}) VALUES (?, ?)",
                ("test", new_ts),
            )
    conn.commit()


# ── PurgeResult / RetentionReport dataclass tests ────────────────────


class TestDataclasses:
    def test_purge_result_fields(self):
        result = PurgeResult(table="test", deleted=5, cutoff="2025-01-01")
        assert result.table == "test"
        assert result.deleted == 5
        assert result.cutoff == "2025-01-01"

    def test_retention_report_success(self):
        report = RetentionReport()
        assert report.success is True
        assert report.total_deleted == 0

    def test_retention_report_with_errors(self):
        report = RetentionReport(errors={"bad_table": "no such table"})
        assert report.success is False


# ── compute_cutoff tests ─────────────────────────────────────────────


class TestComputeCutoff:
    def test_cutoff_format(self):
        cutoff = compute_cutoff(30)
        # Should be ISO 8601 format
        assert "T" in cutoff
        # Parse should work
        datetime.strptime(cutoff, "%Y-%m-%dT%H:%M:%S")

    def test_cutoff_is_in_past(self):
        cutoff = compute_cutoff(30)
        cutoff_dt = datetime.strptime(cutoff, "%Y-%m-%dT%H:%M:%S")
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        assert cutoff_dt < now


# ── purge_table tests ────────────────────────────────────────────────


class TestPurgeTable:
    def test_purge_deletes_old_records(self, conn):
        _insert_old_and_new(conn, "core_executions", "created_at")
        cutoff = compute_cutoff(90)
        result = purge_table(conn, "core_executions", "created_at", cutoff)
        assert result.deleted == 3
        assert result.table == "core_executions"

        # Verify remaining
        cursor = conn.execute("SELECT COUNT(*) FROM core_executions")
        assert cursor.fetchone()[0] == 2

    def test_purge_with_extra_condition(self, conn):
        # Insert COMPLETE and PENDING items
        old_ts = (datetime.now(timezone.utc) - timedelta(days=100)).strftime("%Y-%m-%dT%H:%M:%S")
        conn.execute(
            "INSERT INTO core_work_items (domain, state, completed_at) VALUES (?, ?, ?)",
            ("test", "COMPLETE", old_ts),
        )
        conn.execute(
            "INSERT INTO core_work_items (domain, state, completed_at) VALUES (?, ?, ?)",
            ("test", "PENDING", old_ts),
        )
        conn.commit()

        cutoff = compute_cutoff(90)
        result = purge_table(
            conn, "core_work_items", "completed_at", cutoff, extra_condition="state = 'COMPLETE'"
        )
        assert result.deleted == 1

        # PENDING should remain
        cursor = conn.execute("SELECT COUNT(*) FROM core_work_items WHERE state = 'PENDING'")
        assert cursor.fetchone()[0] == 1

    def test_purge_empty_table(self, conn):
        cutoff = compute_cutoff(90)
        result = purge_table(conn, "core_executions", "created_at", cutoff)
        assert result.deleted == 0


# ── Individual purge function tests ──────────────────────────────────


class TestPurgeFunctions:
    def test_purge_executions(self, conn):
        _insert_old_and_new(conn, "core_executions", "created_at")
        result = purge_executions(conn, days=90)
        assert result.deleted == 3
        assert result.table == "core_executions"

    def test_purge_rejects(self, conn):
        _insert_old_and_new(conn, "core_rejects", "created_at")
        result = purge_rejects(conn, days=30)
        assert result.deleted == 3

    def test_purge_quality(self, conn):
        _insert_old_and_new(conn, "core_quality", "created_at")
        result = purge_quality(conn, days=90)
        assert result.deleted == 3

    def test_purge_anomalies(self, conn):
        _insert_old_and_new(conn, "core_anomalies", "created_at")
        result = purge_anomalies(conn, days=90)
        assert result.deleted == 3

    def test_purge_work_items(self, conn):
        _insert_old_and_new(conn, "core_work_items", "completed_at")
        result = purge_work_items(conn, days=30)
        assert result.deleted == 3


# ── purge_all tests ──────────────────────────────────────────────────


class TestPurgeAll:
    def test_purge_all_with_defaults(self, conn):
        # Insert data into all tables
        _insert_old_and_new(conn, "core_executions", "created_at")
        _insert_old_and_new(conn, "core_rejects", "created_at")
        _insert_old_and_new(conn, "core_quality", "created_at")
        _insert_old_and_new(conn, "core_anomalies", "created_at")
        _insert_old_and_new(conn, "core_work_items", "completed_at")

        report = purge_all(conn)
        assert report.success is True
        # anomalies have 180-day retention, test data is 100 days old, so not purged
        assert report.total_deleted == 12  # 3 old per table * 4 tables (not anomalies)
        assert len(report.results) == 5

    def test_purge_all_with_custom_config(self, conn):
        _insert_old_and_new(conn, "core_executions", "created_at")

        # Use very long retention so nothing gets purged
        config = RetentionConfig(
            executions=365,
            rejects=365,
            quality=365,
            anomalies=365,
            work_items=365,
        )
        report = purge_all(conn, config=config)
        assert report.success is True
        assert report.total_deleted == 0

    def test_purge_all_handles_missing_table(self, conn):
        # Drop one table
        conn.execute("DROP TABLE core_rejects")
        _insert_old_and_new(conn, "core_executions", "created_at")

        report = purge_all(conn)
        # Should have error for core_rejects but continue with others
        assert "core_rejects" in report.errors
        assert report.success is False
        # Other tables should still be processed
        assert len(report.results) >= 1


# ── get_table_counts tests ───────────────────────────────────────────


class TestGetTableCounts:
    def test_get_counts_empty(self, conn):
        counts = get_table_counts(conn)
        assert counts["core_executions"] == 0
        assert counts["core_rejects"] == 0

    def test_get_counts_with_data(self, conn):
        _insert_old_and_new(conn, "core_executions", "created_at")
        counts = get_table_counts(conn)
        assert counts["core_executions"] == 5

    def test_get_counts_missing_table(self, conn):
        conn.execute("DROP TABLE core_rejects")
        counts = get_table_counts(conn)
        assert counts["core_rejects"] == -1  # Indicates missing table


# ── RetentionConfig tests ────────────────────────────────────────────


class TestRetentionConfig:
    def test_defaults(self):
        config = RetentionConfig()
        assert config.executions == 90
        assert config.rejects == 30
        assert config.quality == 90
        assert config.anomalies == 180
        assert config.work_items == 30

    def test_custom_values(self):
        config = RetentionConfig(executions=7, rejects=7, quality=7, anomalies=7, work_items=7)
        assert config.executions == 7
