"""Tests for core.anomalies module.

Covers:
- AnomalyRecorder: record, resolve, list_unresolved, count_by_severity, has_recent_critical
- Severity and AnomalyCategory enums
- create_recorder convenience function
"""

import sqlite3

import pytest

from spine.core.anomalies import (
    AnomalyCategory,
    AnomalyRecorder,
    Severity,
    create_recorder,
)
from spine.core.schema import create_core_tables


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def conn():
    """In-memory SQLite with core tables created."""
    c = sqlite3.connect(":memory:")
    create_core_tables(c)
    yield c
    c.close()


@pytest.fixture
def recorder(conn):
    return AnomalyRecorder(conn, domain="test.domain")


# ---------------------------------------------------------------------------
# Enum tests
# ---------------------------------------------------------------------------


class TestSeverityEnum:
    def test_values(self):
        assert Severity.DEBUG == "DEBUG"
        assert Severity.INFO == "INFO"
        assert Severity.WARN == "WARN"
        assert Severity.ERROR == "ERROR"
        assert Severity.CRITICAL == "CRITICAL"

    def test_all_members(self):
        assert len(Severity) == 5


class TestAnomalyCategoryEnum:
    def test_values(self):
        assert AnomalyCategory.QUALITY_GATE == "QUALITY_GATE"
        assert AnomalyCategory.NETWORK == "NETWORK"
        assert AnomalyCategory.TIMEOUT == "TIMEOUT"

    def test_all_members(self):
        assert len(AnomalyCategory) >= 8


# ---------------------------------------------------------------------------
# AnomalyRecorder.record
# ---------------------------------------------------------------------------


class TestAnomalyRecorderRecord:
    def test_record_returns_id(self, recorder):
        aid = recorder.record(
            stage="ingest",
            partition_key={"week": "2026-01-09"},
            severity=Severity.ERROR,
            category=AnomalyCategory.QUALITY_GATE,
            message="Null rate exceeds threshold",
        )
        assert isinstance(aid, int)
        assert aid >= 1  # AUTOINCREMENT starts at 1

    def test_record_persists_to_db(self, recorder, conn):
        aid = recorder.record(
            stage="enrich",
            partition_key={"date": "2026-01-15"},
            severity=Severity.WARN,
            category=AnomalyCategory.DATA_QUALITY,
            message="Missing field",
        )
        cursor = conn.execute("SELECT * FROM core_anomalies WHERE id = ?", (aid,))
        row = cursor.fetchone()
        assert row is not None

    def test_record_with_string_severity(self, recorder):
        """record() accepts string severity values."""
        aid = recorder.record(
            stage="fetch",
            partition_key="key-123",
            severity="ERROR",
            category="NETWORK",
            message="Connection timeout",
        )
        assert isinstance(aid, int)

    def test_record_with_metadata(self, recorder, conn):
        aid = recorder.record(
            stage="ingest",
            partition_key={"x": 1},
            severity=Severity.ERROR,
            category=AnomalyCategory.QUALITY_GATE,
            message="Bad data",
            metadata={"null_rate": 0.35, "threshold": 0.25},
        )
        cursor = conn.execute(
            "SELECT details_json FROM core_anomalies WHERE id = ?", (aid,)
        )
        row = cursor.fetchone()
        import json

        meta = json.loads(row[0])
        assert meta["null_rate"] == 0.35

    def test_record_with_execution_id(self, recorder, conn):
        aid = recorder.record(
            stage="ingest",
            partition_key="key",
            severity=Severity.INFO,
            category=AnomalyCategory.STEP_FAILURE,
            message="Step failed",
            execution_id="exec-abc-123",
        )
        cursor = conn.execute(
            "SELECT details_json FROM core_anomalies WHERE id = ?", (aid,)
        )
        import json

        meta = json.loads(cursor.fetchone()[0])
        assert meta["execution_id"] == "exec-abc-123"

    def test_record_with_dict_partition_key(self, recorder, conn):
        import json

        aid = recorder.record(
            stage="s",
            partition_key={"week_ending": "2026-01-09", "source": "finra"},
            severity=Severity.INFO,
            category=AnomalyCategory.UNKNOWN,
            message="test",
        )
        cursor = conn.execute(
            "SELECT partition_key FROM core_anomalies WHERE id = ?", (aid,)
        )
        pk = cursor.fetchone()[0]
        parsed = json.loads(pk)
        assert parsed["source"] == "finra"

    def test_record_with_string_partition_key(self, recorder, conn):
        aid = recorder.record(
            stage="s",
            partition_key="simple-key",
            severity=Severity.DEBUG,
            category=AnomalyCategory.UNKNOWN,
            message="test",
        )
        cursor = conn.execute(
            "SELECT partition_key FROM core_anomalies WHERE id = ?", (aid,)
        )
        assert cursor.fetchone()[0] == "simple-key"


# ---------------------------------------------------------------------------
# AnomalyRecorder.resolve
# ---------------------------------------------------------------------------


class TestAnomalyRecorderResolve:
    def test_resolve_sets_resolved_at(self, recorder, conn):
        aid = recorder.record(
            stage="s", partition_key="k", severity=Severity.ERROR,
            category=AnomalyCategory.UNKNOWN, message="err",
        )
        recorder.resolve(aid)

        cursor = conn.execute(
            "SELECT resolved_at FROM core_anomalies WHERE id = ?", (aid,)
        )
        assert cursor.fetchone()[0] is not None

    def test_resolve_with_note(self, recorder, conn):
        aid = recorder.record(
            stage="s", partition_key="k", severity=Severity.ERROR,
            category=AnomalyCategory.UNKNOWN, message="err",
        )
        recorder.resolve(aid, resolution_note="Fixed in rerun")

        cursor = conn.execute(
            "SELECT details_json FROM core_anomalies WHERE id = ?", (aid,)
        )
        import json

        meta = json.loads(cursor.fetchone()[0])
        assert meta["resolution_note"] == "Fixed in rerun"

    def test_resolve_without_note(self, recorder, conn):
        aid = recorder.record(
            stage="s", partition_key="k", severity=Severity.WARN,
            category=AnomalyCategory.UNKNOWN, message="warn",
        )
        recorder.resolve(aid)

        cursor = conn.execute(
            "SELECT resolved_at FROM core_anomalies WHERE id = ?", (aid,)
        )
        assert cursor.fetchone()[0] is not None


# ---------------------------------------------------------------------------
# AnomalyRecorder.list_unresolved
# ---------------------------------------------------------------------------


class TestAnomalyRecorderListUnresolved:
    def test_list_returns_unresolved_only(self, recorder):
        aid1 = recorder.record(
            stage="s", partition_key="k", severity=Severity.ERROR,
            category=AnomalyCategory.UNKNOWN, message="open",
        )
        aid2 = recorder.record(
            stage="s", partition_key="k", severity=Severity.WARN,
            category=AnomalyCategory.UNKNOWN, message="resolved",
        )
        recorder.resolve(aid2)

        results = recorder.list_unresolved()
        assert len(results) == 1
        assert results[0]["id"] == aid1

    def test_list_filter_by_severity(self, recorder):
        recorder.record(
            stage="s", partition_key="k", severity=Severity.ERROR,
            category=AnomalyCategory.UNKNOWN, message="error",
        )
        recorder.record(
            stage="s", partition_key="k", severity=Severity.WARN,
            category=AnomalyCategory.UNKNOWN, message="warn",
        )

        results = recorder.list_unresolved(severity=Severity.ERROR)
        assert len(results) == 1
        assert results[0]["severity"] == "ERROR"

    def test_list_filter_by_category(self, recorder):
        recorder.record(
            stage="s", partition_key="k", severity=Severity.ERROR,
            category=AnomalyCategory.NETWORK, message="net",
        )
        recorder.record(
            stage="s", partition_key="k", severity=Severity.ERROR,
            category=AnomalyCategory.QUALITY_GATE, message="qual",
        )

        results = recorder.list_unresolved(category=AnomalyCategory.NETWORK)
        assert len(results) == 1
        assert results[0]["category"] == "NETWORK"

    def test_list_filter_by_stage(self, recorder):
        recorder.record(
            stage="ingest", partition_key="k", severity=Severity.WARN,
            category=AnomalyCategory.UNKNOWN, message="ingest err",
        )
        recorder.record(
            stage="enrich", partition_key="k", severity=Severity.WARN,
            category=AnomalyCategory.UNKNOWN, message="enrich err",
        )

        results = recorder.list_unresolved(stage="ingest")
        assert len(results) == 1
        assert results[0]["message"] == "ingest err"

    def test_list_respects_limit(self, recorder):
        for i in range(10):
            recorder.record(
                stage="s", partition_key="k", severity=Severity.WARN,
                category=AnomalyCategory.UNKNOWN, message=f"msg {i}",
            )

        results = recorder.list_unresolved(limit=3)
        assert len(results) == 3

    def test_list_empty_when_all_resolved(self, recorder):
        aid = recorder.record(
            stage="s", partition_key="k", severity=Severity.ERROR,
            category=AnomalyCategory.UNKNOWN, message="err",
        )
        recorder.resolve(aid)
        results = recorder.list_unresolved()
        assert len(results) == 0

    def test_list_only_returns_own_domain(self, conn):
        r1 = AnomalyRecorder(conn, domain="domain_a")
        r2 = AnomalyRecorder(conn, domain="domain_b")

        r1.record(
            stage="s", partition_key="k", severity=Severity.ERROR,
            category=AnomalyCategory.UNKNOWN, message="a's anomaly",
        )
        r2.record(
            stage="s", partition_key="k", severity=Severity.ERROR,
            category=AnomalyCategory.UNKNOWN, message="b's anomaly",
        )

        a_results = r1.list_unresolved()
        assert len(a_results) == 1
        assert a_results[0]["message"] == "a's anomaly"


# ---------------------------------------------------------------------------
# AnomalyRecorder.count_by_severity
# ---------------------------------------------------------------------------


class TestCountBySeverity:
    def test_count_grouped_correctly(self, recorder):
        recorder.record(stage="s", partition_key="k", severity=Severity.ERROR,
                        category=AnomalyCategory.UNKNOWN, message="e1")
        recorder.record(stage="s", partition_key="k", severity=Severity.ERROR,
                        category=AnomalyCategory.UNKNOWN, message="e2")
        recorder.record(stage="s", partition_key="k", severity=Severity.WARN,
                        category=AnomalyCategory.UNKNOWN, message="w1")

        counts = recorder.count_by_severity(since_hours=24)
        assert counts.get("ERROR", 0) == 2
        assert counts.get("WARN", 0) == 1


# ---------------------------------------------------------------------------
# AnomalyRecorder.has_recent_critical
# ---------------------------------------------------------------------------


class TestHasRecentCritical:
    def test_returns_true_with_critical(self, recorder):
        recorder.record(stage="s", partition_key="k", severity=Severity.CRITICAL,
                        category=AnomalyCategory.UNKNOWN, message="critical!")
        assert recorder.has_recent_critical(since_hours=1) is True

    def test_returns_false_without_critical(self, recorder):
        recorder.record(stage="s", partition_key="k", severity=Severity.ERROR,
                        category=AnomalyCategory.UNKNOWN, message="just error")
        assert recorder.has_recent_critical(since_hours=1) is False

    def test_returns_false_when_critical_resolved(self, recorder):
        aid = recorder.record(stage="s", partition_key="k", severity=Severity.CRITICAL,
                              category=AnomalyCategory.UNKNOWN, message="critical!")
        recorder.resolve(aid)
        assert recorder.has_recent_critical(since_hours=1) is False


# ---------------------------------------------------------------------------
# create_recorder
# ---------------------------------------------------------------------------


class TestCreateRecorder:
    def test_returns_anomaly_recorder(self, conn):
        r = create_recorder(conn, "test.domain")
        assert isinstance(r, AnomalyRecorder)
        assert r.domain == "test.domain"
