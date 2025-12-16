"""Tests for spine.core.manifest — Stage-tracking work manifest."""

from __future__ import annotations

import sqlite3

import pytest

from spine.core.manifest import ManifestRow, WorkManifest


# ── Fixtures ─────────────────────────────────────────────────────────────


STAGES = ["ingested", "parsed", "validated", "enriched", "published"]


@pytest.fixture()
def conn():
    """In-memory SQLite with core_manifest table."""
    db = sqlite3.connect(":memory:")
    db.execute("""
        CREATE TABLE core_manifest (
            domain TEXT NOT NULL,
            partition_key TEXT NOT NULL,
            stage TEXT NOT NULL,
            stage_rank INTEGER NOT NULL,
            row_count INTEGER DEFAULT 0,
            metrics_json TEXT,
            execution_id TEXT NOT NULL,
            batch_id TEXT,
            updated_at TEXT NOT NULL,
            UNIQUE(domain, partition_key, stage)
        )
    """)
    db.commit()
    yield db
    db.close()


@pytest.fixture()
def manifest(conn):
    return WorkManifest(conn, domain="otc", stages=STAGES)


# ── ManifestRow ──────────────────────────────────────────────────────────


class TestManifestRow:
    def test_construction(self):
        row = ManifestRow(
            stage="parsed",
            stage_rank=1,
            row_count=100,
            metrics={},
            execution_id="exec-1",
            batch_id=None,
            updated_at="2025-01-01T00:00:00Z",
        )
        assert row.stage == "parsed"
        assert row.stage_rank == 1
        assert row.row_count == 100


# ── WorkManifest.advance_to ──────────────────────────────────────────────


class TestAdvanceTo:
    def test_basic_advance(self, manifest, conn):
        manifest.advance_to("file-001", "ingested", row_count=50, execution_id="e1")

        rows = conn.execute("SELECT stage, stage_rank, row_count FROM core_manifest").fetchall()
        assert len(rows) == 1
        assert rows[0][0] == "ingested"
        assert rows[0][1] == 0  # first stage
        assert rows[0][2] == 50

    def test_upsert_same_stage(self, manifest, conn):
        manifest.advance_to("file-001", "parsed", row_count=100, execution_id="e1")
        manifest.advance_to("file-001", "parsed", row_count=200, execution_id="e2")

        rows = conn.execute("SELECT row_count FROM core_manifest WHERE stage = 'parsed'").fetchall()
        assert len(rows) == 1
        assert rows[0][0] == 200

    def test_unknown_stage_raises(self, manifest):
        with pytest.raises(ValueError, match="Unknown stage"):
            manifest.advance_to("file-001", "BOGUS", execution_id="e1")

    def test_metrics_stored(self, manifest, conn):
        manifest.advance_to("file-001", "parsed", execution_id="e1", elapsed_ms=42)

        metrics_json = conn.execute(
            "SELECT metrics_json FROM core_manifest WHERE stage = 'parsed'"
        ).fetchone()[0]
        assert "42" in metrics_json


# ── WorkManifest.get ─────────────────────────────────────────────────────


class TestGet:
    def test_get_returns_list(self, manifest):
        manifest.advance_to("file-001", "ingested", execution_id="e1")
        manifest.advance_to("file-001", "parsed", execution_id="e1")

        rows = manifest.get("file-001")
        assert len(rows) == 2
        assert isinstance(rows[0], ManifestRow)

    def test_get_ordered_by_rank(self, manifest):
        manifest.advance_to("file-001", "parsed", execution_id="e1")
        manifest.advance_to("file-001", "ingested", execution_id="e1")

        rows = manifest.get("file-001")
        assert rows[0].stage == "ingested"
        assert rows[1].stage == "parsed"

    def test_get_unknown_key(self, manifest):
        rows = manifest.get("nonexistent")
        assert rows == []


# ── WorkManifest.get_latest_stage ────────────────────────────────────────


class TestGetLatestStage:
    def test_returns_latest(self, manifest):
        manifest.advance_to("file-001", "ingested", execution_id="e1")
        manifest.advance_to("file-001", "parsed", execution_id="e1")
        manifest.advance_to("file-001", "validated", execution_id="e1")

        assert manifest.get_latest_stage("file-001") == "validated"

    def test_returns_none_when_empty(self, manifest):
        assert manifest.get_latest_stage("nonexistent") is None


# ── WorkManifest.is_at_least ─────────────────────────────────────────────


class TestIsAtLeast:
    def test_true_when_at_stage(self, manifest):
        manifest.advance_to("file-001", "parsed", execution_id="e1")
        assert manifest.is_at_least("file-001", "parsed") is True

    def test_true_when_past_stage(self, manifest):
        manifest.advance_to("file-001", "validated", execution_id="e1")
        assert manifest.is_at_least("file-001", "parsed") is True

    def test_false_when_before_stage(self, manifest):
        manifest.advance_to("file-001", "ingested", execution_id="e1")
        assert manifest.is_at_least("file-001", "parsed") is False

    def test_false_when_no_data(self, manifest):
        assert manifest.is_at_least("nonexistent", "parsed") is False


# ── WorkManifest.is_before ───────────────────────────────────────────────


class TestIsBefore:
    def test_true_when_before(self, manifest):
        manifest.advance_to("file-001", "ingested", execution_id="e1")
        assert manifest.is_before("file-001", "parsed") is True

    def test_false_when_at_stage(self, manifest):
        manifest.advance_to("file-001", "parsed", execution_id="e1")
        assert manifest.is_before("file-001", "parsed") is False

    def test_false_when_past_stage(self, manifest):
        manifest.advance_to("file-001", "validated", execution_id="e1")
        assert manifest.is_before("file-001", "parsed") is False


# ── WorkManifest.has_stage ───────────────────────────────────────────────


class TestHasStage:
    def test_true_when_exists(self, manifest):
        manifest.advance_to("file-001", "parsed", execution_id="e1")
        assert manifest.has_stage("file-001", "parsed") is True

    def test_false_when_not_exists(self, manifest):
        manifest.advance_to("file-001", "parsed", execution_id="e1")
        assert manifest.has_stage("file-001", "validated") is False

    def test_false_when_no_data(self, manifest):
        assert manifest.has_stage("nonexistent", "parsed") is False


# ── WorkManifest.get_stage_metrics ───────────────────────────────────────


class TestGetStageMetrics:
    def test_returns_row(self, manifest):
        manifest.advance_to("file-001", "parsed", execution_id="e1", elapsed_ms=42)
        row = manifest.get_stage_metrics("file-001", "parsed")
        assert isinstance(row, ManifestRow)
        assert row.stage == "parsed"

    def test_returns_none_when_missing(self, manifest):
        assert manifest.get_stage_metrics("file-001", "parsed") is None


# ── on_stage_change hook ─────────────────────────────────────────────────


class TestOnStageChangeHook:
    def test_hook_called_on_advance(self, conn):
        calls = []

        def hook(domain, key, stage, stage_rank, metrics):
            calls.append((domain, key, stage, stage_rank))

        m = WorkManifest(conn, domain="otc", stages=STAGES, on_stage_change=hook)
        m.advance_to("file-001", "parsed", row_count=100, execution_id="e1")

        assert len(calls) == 1
        assert calls[0][0] == "otc"
        assert calls[0][1] == "file-001"
        assert calls[0][2] == "parsed"


# ── Multi-key isolation ──────────────────────────────────────────────────


class TestMultiKeyIsolation:
    def test_keys_are_independent(self, manifest):
        manifest.advance_to("file-001", "validated", execution_id="e1")
        manifest.advance_to("file-002", "ingested", execution_id="e1")

        assert manifest.get_latest_stage("file-001") == "validated"
        assert manifest.get_latest_stage("file-002") == "ingested"
        assert manifest.is_at_least("file-001", "parsed") is True
        assert manifest.is_at_least("file-002", "parsed") is False
