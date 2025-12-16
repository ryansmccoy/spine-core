"""Tests for spine.core.quality — Quality check framework + gates."""

from __future__ import annotations

import sqlite3

import pytest

from spine.core.quality import (
    QualityCategory,
    QualityCheck,
    QualityResult,
    QualityRunner,
    QualityStatus,
)


# ── Fixtures ─────────────────────────────────────────────────────────────


@pytest.fixture()
def conn():
    """In-memory SQLite with core_quality table."""
    db = sqlite3.connect(":memory:")
    db.execute("""
        CREATE TABLE core_quality (
            domain TEXT NOT NULL,
            partition_key TEXT NOT NULL,
            check_name TEXT NOT NULL,
            category TEXT NOT NULL,
            status TEXT NOT NULL,
            message TEXT,
            actual_value TEXT,
            expected_value TEXT,
            details_json TEXT,
            execution_id TEXT NOT NULL,
            batch_id TEXT,
            created_at TEXT NOT NULL
        )
    """)
    db.commit()
    yield db
    db.close()


def _pass_check(ctx: dict) -> QualityResult:
    return QualityResult(QualityStatus.PASS, "OK")


def _fail_check(ctx: dict) -> QualityResult:
    return QualityResult(QualityStatus.FAIL, "Bad data", actual_value=-5, expected_value=">=0")


def _warn_check(ctx: dict) -> QualityResult:
    return QualityResult(QualityStatus.WARN, "Above threshold", actual_value=15.0, expected_value=10.0)


# ── QualityStatus ────────────────────────────────────────────────────────


class TestQualityStatus:
    def test_values(self):
        assert QualityStatus.PASS.value == "PASS"
        assert QualityStatus.WARN.value == "WARN"
        assert QualityStatus.FAIL.value == "FAIL"

    def test_is_string_enum(self):
        assert isinstance(QualityStatus.PASS, str)


# ── QualityCategory ─────────────────────────────────────────────────────


class TestQualityCategory:
    def test_values(self):
        assert QualityCategory.INTEGRITY.value == "INTEGRITY"
        assert QualityCategory.COMPLETENESS.value == "COMPLETENESS"
        assert QualityCategory.BUSINESS_RULE.value == "BUSINESS_RULE"


# ── QualityResult ────────────────────────────────────────────────────────


class TestQualityResult:
    def test_defaults(self):
        r = QualityResult(QualityStatus.PASS, "OK")
        assert r.status == QualityStatus.PASS
        assert r.message == "OK"
        assert r.actual_value is None
        assert r.expected_value is None

    def test_with_values(self):
        r = QualityResult(QualityStatus.FAIL, "Bad", actual_value=42, expected_value=100)
        assert r.actual_value == 42
        assert r.expected_value == 100


# ── QualityCheck ─────────────────────────────────────────────────────────


class TestQualityCheck:
    def test_construction(self):
        check = QualityCheck("sum_100", QualityCategory.BUSINESS_RULE, _pass_check)
        assert check.name == "sum_100"
        assert check.category == QualityCategory.BUSINESS_RULE

    def test_check_fn_callable(self):
        check = QualityCheck("test", QualityCategory.INTEGRITY, _pass_check)
        result = check.check_fn({})
        assert result.status == QualityStatus.PASS


# ── QualityRunner ────────────────────────────────────────────────────────


class TestQualityRunner:
    def test_add_returns_self(self, conn):
        runner = QualityRunner(conn, domain="test", execution_id="exec-1")
        result = runner.add(QualityCheck("c1", QualityCategory.INTEGRITY, _pass_check))
        assert result is runner

    def test_fluent_chaining(self, conn):
        runner = QualityRunner(conn, domain="test", execution_id="exec-1")
        runner.add(
            QualityCheck("c1", QualityCategory.INTEGRITY, _pass_check)
        ).add(
            QualityCheck("c2", QualityCategory.COMPLETENESS, _pass_check)
        )
        assert len(runner.checks) == 2

    def test_run_all_returns_status_dict(self, conn):
        runner = QualityRunner(conn, domain="test", execution_id="exec-1")
        runner.add(QualityCheck("c1", QualityCategory.INTEGRITY, _pass_check))
        runner.add(QualityCheck("c2", QualityCategory.BUSINESS_RULE, _fail_check))

        results = runner.run_all({}, partition_key={"week": "2025-12-26"})

        assert results == {"c1": QualityStatus.PASS, "c2": QualityStatus.FAIL}

    def test_has_failures_false_when_all_pass(self, conn):
        runner = QualityRunner(conn, domain="test", execution_id="exec-1")
        runner.add(QualityCheck("c1", QualityCategory.INTEGRITY, _pass_check))
        runner.run_all({})
        assert runner.has_failures() is False

    def test_has_failures_true_on_fail(self, conn):
        runner = QualityRunner(conn, domain="test", execution_id="exec-1")
        runner.add(QualityCheck("c1", QualityCategory.INTEGRITY, _fail_check))
        runner.run_all({})
        assert runner.has_failures() is True

    def test_has_failures_false_on_warn_only(self, conn):
        runner = QualityRunner(conn, domain="test", execution_id="exec-1")
        runner.add(QualityCheck("c1", QualityCategory.INTEGRITY, _warn_check))
        runner.run_all({})
        assert runner.has_failures() is False

    def test_failures_returns_names(self, conn):
        runner = QualityRunner(conn, domain="test", execution_id="exec-1")
        runner.add(QualityCheck("good", QualityCategory.INTEGRITY, _pass_check))
        runner.add(QualityCheck("bad", QualityCategory.BUSINESS_RULE, _fail_check))
        runner.run_all({})
        assert runner.failures() == ["bad"]

    def test_records_to_database(self, conn):
        runner = QualityRunner(conn, domain="otc", execution_id="exec-1")
        runner.add(QualityCheck("sum_check", QualityCategory.BUSINESS_RULE, _pass_check))
        runner.run_all({}, partition_key={"week": "2025-12-26"})

        rows = conn.execute("SELECT * FROM core_quality").fetchall()
        assert len(rows) == 1

    def test_records_correct_values(self, conn):
        runner = QualityRunner(conn, domain="otc", execution_id="exec-1", batch_id="b-1")
        runner.add(QualityCheck("vol_check", QualityCategory.INTEGRITY, _fail_check))
        runner.run_all({}, partition_key={"week": "2025-12-26"})

        row = conn.execute(
            "SELECT domain, check_name, category, status, message, execution_id, batch_id FROM core_quality"
        ).fetchone()
        assert row[0] == "otc"
        assert row[1] == "vol_check"
        assert row[2] == "INTEGRITY"
        assert row[3] == "FAIL"
        assert row[4] == "Bad data"
        assert row[5] == "exec-1"
        assert row[6] == "b-1"

    def test_run_all_clears_previous_results(self, conn):
        runner = QualityRunner(conn, domain="test", execution_id="exec-1")
        runner.add(QualityCheck("c1", QualityCategory.INTEGRITY, _fail_check))

        runner.run_all({})
        assert runner.has_failures() is True

        # Replace check with passing version
        runner.checks.clear()
        runner.add(QualityCheck("c1", QualityCategory.INTEGRITY, _pass_check))
        runner.run_all({})
        assert runner.has_failures() is False

    def test_no_checks_returns_empty(self, conn):
        runner = QualityRunner(conn, domain="test", execution_id="exec-1")
        results = runner.run_all({})
        assert results == {}
        assert runner.has_failures() is False

    def test_partition_key_none(self, conn):
        """Runs without error when partition_key is None."""
        runner = QualityRunner(conn, domain="test", execution_id="exec-1")
        runner.add(QualityCheck("c1", QualityCategory.INTEGRITY, _pass_check))
        results = runner.run_all({})
        assert results["c1"] == QualityStatus.PASS

    def test_context_passed_to_check_fn(self, conn):
        """Check function receives the context dict."""
        received = {}

        def capture_check(ctx: dict) -> QualityResult:
            received.update(ctx)
            return QualityResult(QualityStatus.PASS, "OK")

        runner = QualityRunner(conn, domain="test", execution_id="exec-1")
        runner.add(QualityCheck("c1", QualityCategory.INTEGRITY, capture_check))
        runner.run_all({"key": "value"})
        assert received == {"key": "value"}
