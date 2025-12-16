"""Tests for spine.core.rejects — Reject sink with DB persistence."""

from __future__ import annotations

import json
import sqlite3

import pytest

from spine.core.rejects import Reject, RejectSink


# ── Fixtures ─────────────────────────────────────────────────────────────


@pytest.fixture()
def conn():
    """In-memory SQLite with core_rejects table."""
    db = sqlite3.connect(":memory:")
    db.execute("""
        CREATE TABLE core_rejects (
            domain TEXT NOT NULL,
            partition_key TEXT NOT NULL,
            stage TEXT NOT NULL,
            reason_code TEXT NOT NULL,
            reason_detail TEXT,
            raw_json TEXT,
            record_key TEXT,
            source_locator TEXT,
            line_number INTEGER,
            execution_id TEXT NOT NULL,
            batch_id TEXT,
            created_at TEXT NOT NULL
        )
    """)
    db.commit()
    yield db
    db.close()


def _make_reject(**overrides) -> Reject:
    defaults = dict(
        stage="parse",
        reason_code="INVALID_DATE",
        reason_detail="Unparseable date field",
        raw_data={"field": "maturity", "value": "2025-13-01"},
        source_locator="file://trades.csv",
        line_number=42,
    )
    defaults.update(overrides)
    return Reject(**defaults)


# ── Reject dataclass ─────────────────────────────────────────────────────


class TestReject:
    def test_construction(self):
        r = _make_reject()
        assert r.stage == "parse"
        assert r.reason_code == "INVALID_DATE"
        assert r.line_number == 42

    def test_defaults_are_none(self):
        r = Reject(stage="parse", reason_code="BAD", reason_detail="detail")
        assert r.raw_data is None
        assert r.source_locator is None
        assert r.line_number is None

    def test_raw_data_is_dict(self):
        r = _make_reject(raw_data={"a": 1})
        assert r.raw_data == {"a": 1}


# ── RejectSink ───────────────────────────────────────────────────────────


class TestRejectSink:
    def test_write_single(self, conn):
        sink = RejectSink(conn, domain="otc", execution_id="exec-1")
        sink.write(_make_reject())

        rows = conn.execute("SELECT * FROM core_rejects").fetchall()
        assert len(rows) == 1

    def test_write_records_correct_values(self, conn):
        sink = RejectSink(conn, domain="otc", execution_id="exec-1", batch_id="b-1")
        sink.write(
            _make_reject(stage="validate", reason_code="NEGATIVE_NOTIONAL"),
            partition_key={"week": "2025-12-26"},
        )

        row = conn.execute(
            "SELECT domain, stage, reason_code, execution_id, batch_id FROM core_rejects"
        ).fetchone()
        assert row[0] == "otc"
        assert row[1] == "validate"
        assert row[2] == "NEGATIVE_NOTIONAL"
        assert row[3] == "exec-1"
        assert row[4] == "b-1"

    def test_write_batch_returns_count(self, conn):
        sink = RejectSink(conn, domain="otc", execution_id="exec-1")
        rejects = [_make_reject(reason_code=f"ERR_{i}") for i in range(5)]
        count = sink.write_batch(rejects)
        assert count == 5

    def test_write_batch_empty(self, conn):
        sink = RejectSink(conn, domain="otc", execution_id="exec-1")
        count = sink.write_batch([])
        assert count == 0

    def test_count_property(self, conn):
        sink = RejectSink(conn, domain="otc", execution_id="exec-1")
        assert sink.count == 0

        sink.write(_make_reject())
        assert sink.count == 1

        sink.write(_make_reject(reason_code="OTHER"))
        assert sink.count == 2

    def test_raw_data_serialized_as_json(self, conn):
        sink = RejectSink(conn, domain="otc", execution_id="exec-1")
        sink.write(_make_reject(raw_data={"k": [1, 2, 3]}))

        raw_json = conn.execute("SELECT raw_json FROM core_rejects").fetchone()[0]
        parsed = json.loads(raw_json)
        assert parsed == {"k": [1, 2, 3]}

    def test_raw_data_none_serializes_safely(self, conn):
        sink = RejectSink(conn, domain="otc", execution_id="exec-1")
        sink.write(_make_reject(raw_data=None))

        raw_json = conn.execute("SELECT raw_json FROM core_rejects").fetchone()[0]
        # Should be None/null or empty string — not crash
        assert raw_json is None or raw_json == "null"

    def test_multiple_writes_accumulate(self, conn):
        sink = RejectSink(conn, domain="otc", execution_id="exec-1")
        for i in range(10):
            sink.write(_make_reject(reason_code=f"ERR_{i}"))
        assert sink.count == 10

        rows = conn.execute("SELECT COUNT(*) FROM core_rejects").fetchone()[0]
        assert rows == 10

    def test_partition_key_none(self, conn):
        """Write succeeds without partition_key."""
        sink = RejectSink(conn, domain="otc", execution_id="exec-1")
        sink.write(_make_reject())
        assert sink.count == 1

    def test_batch_with_partition_key(self, conn):
        sink = RejectSink(conn, domain="otc", execution_id="exec-1")
        rejects = [_make_reject(reason_code=f"ERR_{i}") for i in range(3)]
        count = sink.write_batch(rejects, partition_key={"week": "2025-12-26"})
        assert count == 3
        assert sink.count == 3

    def test_source_locator_stored(self, conn):
        sink = RejectSink(conn, domain="otc", execution_id="exec-1")
        sink.write(_make_reject(source_locator="s3://bucket/key.csv", line_number=99))

        row = conn.execute(
            "SELECT source_locator, line_number FROM core_rejects"
        ).fetchone()
        assert row[0] == "s3://bucket/key.csv"
        assert row[1] == 99
