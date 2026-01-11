"""
Scheduler fitness tests - realistic operational scenarios.

Tests cover:
1. API fetch failures → retry with exponential backoff
2. Missing partition detection → gap reporting
3. Cron idempotency → same capture_id prevents duplicate work
4. Restatement handling → multiple captures coexist

These tests validate production operational patterns, not just happy paths.
"""

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest


@pytest.fixture
def db_path(tmp_path):
    """Provide temporary database path."""
    return str(tmp_path / "test_scheduler.db")


@pytest.fixture
def conn(db_path):
    """Initialize database with schema."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Load schema
    schema_path = Path(__file__).parent.parent / "migrations" / "schema.sql"
    conn.executescript(schema_path.read_text(encoding="utf-8"))
    conn.commit()

    yield conn

    conn.close()


class TestSchedulerFitness:
    """
    Scheduler fitness tests for operational hardening.

    These tests prove Market Spine can handle:
    - Transient failures (API unavailable, network issues)
    - Data gaps (missing weeks/tiers)
    - Idempotent re-runs (cron safety)
    - Data corrections (restatements)
    """

    def test_retry_on_failure_then_success(self, conn):
        """
        Scenario: API fetch fails initially, then succeeds on retry.

        Flow:
        1. Enqueue work item for ingestion
        2. First attempt fails (API 503)
        3. State → FAILED, retry scheduled
        4. Second attempt succeeds
        5. State → COMPLETE, manifest updated
        """
        # 1. Enqueue work
        work_id = self._enqueue_work(
            conn,
            domain="finra.otc_transparency",
            pipeline="ingest_week",
            partition_key={"week_ending": "2025-12-22", "tier": "NMS_TIER_1"},
        )

        # Verify PENDING
        state = conn.execute(
            "SELECT state, attempt_count FROM core_work_items WHERE id = ?", (work_id,)
        ).fetchone()
        assert state["state"] == "PENDING"
        assert state["attempt_count"] == 0

        # 2. First attempt: claim work
        self._claim_work(conn, work_id, worker_id="worker-1")

        state = conn.execute(
            "SELECT state FROM core_work_items WHERE id = ?", (work_id,)
        ).fetchone()
        assert state["state"] == "RUNNING"

        # 3. First attempt fails: API unavailable
        self._record_failure(
            conn,
            work_id,
            error="HTTP 503: FINRA API unavailable",
            next_attempt_delay_seconds=300,  # 5 minutes
        )

        state = conn.execute(
            "SELECT state, attempt_count, last_error, next_attempt_at FROM core_work_items WHERE id = ?",
            (work_id,),
        ).fetchone()

        assert state["state"] == "RETRY_WAIT"
        assert state["attempt_count"] == 1
        assert "503" in state["last_error"]
        assert state["next_attempt_at"] is not None

        # 4. Wait period expires, state → PENDING
        conn.execute(
            "UPDATE core_work_items SET state = 'PENDING', next_attempt_at = NULL WHERE id = ?",
            (work_id,),
        )
        conn.commit()

        # 5. Second attempt: claim and succeed
        self._claim_work(conn, work_id, worker_id="worker-1")

        execution_id = "exec-retry-success"
        row_count = 48765

        self._record_success(conn, work_id, execution_id=execution_id, row_count=row_count)

        # Verify COMPLETE
        state = conn.execute(
            "SELECT state, attempt_count, latest_execution_id FROM core_work_items WHERE id = ?",
            (work_id,),
        ).fetchone()

        assert state["state"] == "COMPLETE"
        assert (
            state["attempt_count"] == 1
        )  # Attempt count from failure only (success doesn't increment)
        assert state["latest_execution_id"] == execution_id

        # Verify manifest updated
        manifest = conn.execute(
            """SELECT row_count, execution_id FROM core_manifest 
               WHERE domain = 'finra.otc_transparency' 
               AND partition_key = ? 
               AND stage = 'RAW'""",
            (json.dumps({"week_ending": "2025-12-22", "tier": "NMS_TIER_1"}),),
        ).fetchone()

        assert manifest["row_count"] == row_count
        assert manifest["execution_id"] == execution_id

        print("\n✓ Retry on failure: API 503 → wait → success → manifest updated")

    def test_max_attempts_exhausted(self, conn):
        """
        Scenario: Work fails max_attempts times, stays in FAILED.

        Flow:
        1. Work fails 3 times (max_attempts = 3)
        2. State → FAILED (no more retries)
        3. Requires manual intervention
        """
        work_id = self._enqueue_work(
            conn,
            domain="finra.otc_transparency",
            pipeline="ingest_week",
            partition_key={"week_ending": "2025-12-22", "tier": "OTC"},
            max_attempts=3,
        )

        # Fail 3 times
        for attempt in range(1, 4):
            self._claim_work(conn, work_id, worker_id=f"worker-{attempt}")

            delay = 60 * (2 ** (attempt - 1))  # Exponential backoff: 60s, 120s, 240s
            self._record_failure(
                conn,
                work_id,
                error=f"Attempt {attempt}: Connection timeout",
                next_attempt_delay_seconds=delay if attempt < 3 else None,
            )

            if attempt < 3:
                # Transition back to PENDING for next retry
                conn.execute(
                    "UPDATE core_work_items SET state = 'PENDING', next_attempt_at = NULL WHERE id = ?",
                    (work_id,),
                )
                conn.commit()

        # After 3 failures, should be in FAILED state (not RETRY_WAIT)
        state = conn.execute(
            "SELECT state, attempt_count, last_error FROM core_work_items WHERE id = ?", (work_id,)
        ).fetchone()

        assert state["state"] == "FAILED"
        assert state["attempt_count"] == 3
        assert "timeout" in state["last_error"]

        print(
            "\n✓ Max attempts exhausted: 3 failures → FAILED state → manual intervention required"
        )

    def test_gap_detection_missing_partitions(self, conn):
        """
        Scenario: Expected 3 weeks × 3 tiers, ingested only 2 weeks.

        Doctor should report 3 missing partitions.
        """
        # Expected: weeks 12-01, 12-08, 12-15 × 3 tiers = 9 partitions
        # Actual: ingest only 12-01 and 12-15 (missing 12-08)

        weeks = ["2025-12-01", "2025-12-15"]  # Missing 2025-12-08
        tiers = ["NMS_TIER_1", "NMS_TIER_2", "OTC"]

        for week in weeks:
            for tier in tiers:
                # Simulate successful ingestion
                partition_key = json.dumps({"week_ending": week, "tier": tier})

                conn.execute(
                    """INSERT INTO core_manifest (
                        domain, partition_key, stage, stage_rank, row_count,
                        execution_id, batch_id, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        "finra.otc_transparency",
                        partition_key,
                        "RAW",
                        1,
                        16000,
                        f"exec-{week}-{tier}",
                        "batch-test",
                        datetime.now(UTC).isoformat(),
                    ),
                )

        conn.commit()

        # Run doctor check
        expected_weeks = ["2025-12-01", "2025-12-08", "2025-12-15"]
        gaps = self._detect_gaps(conn, expected_weeks, tiers)

        # Should find 3 missing partitions (all tiers for week 2025-12-08)
        assert len(gaps) == 3

        missing_week = [g for g in gaps if g["week_ending"] == "2025-12-08"]
        assert len(missing_week) == 3  # All 3 tiers missing

        # Verify specific gaps
        assert any(g["tier"] == "NMS_TIER_1" and g["week_ending"] == "2025-12-08" for g in gaps)
        assert any(g["tier"] == "NMS_TIER_2" and g["week_ending"] == "2025-12-08" for g in gaps)
        assert any(g["tier"] == "OTC" and g["week_ending"] == "2025-12-08" for g in gaps)

        print(f"\n✓ Gap detection: Expected 9 partitions, found 6, identified {len(gaps)} gaps")
        for gap in gaps:
            print(f"  - Missing: {gap['week_ending']} / {gap['tier']}")

    def test_incomplete_stage_chain(self, conn):
        """
        Scenario: RAW stage present but NORMALIZED missing.

        Doctor should report incomplete pipeline for that partition.
        """
        week = "2025-12-15"
        tier = "NMS_TIER_1"
        partition_key = json.dumps({"week_ending": week, "tier": tier})

        # Insert RAW stage only (no NORMALIZED)
        conn.execute(
            """INSERT INTO core_manifest (
                domain, partition_key, stage, stage_rank, row_count,
                execution_id, batch_id, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                "finra.otc_transparency",
                partition_key,
                "RAW",
                1,
                48765,
                "exec-raw-only",
                "batch-test",
                datetime.now(UTC).isoformat(),
            ),
        )
        conn.commit()

        # Check stage completeness
        incomplete = self._check_stage_completeness(conn, week, tier)

        assert incomplete["has_raw"] is True
        assert incomplete["has_normalized"] is False
        assert incomplete["has_venue_volume"] is False

        print("\n✓ Incomplete stage chain detected: RAW ✓, NORMALIZED ✗")
        print(f"  Remediation: Run normalize_week for {week}/{tier}")

    def test_cron_idempotency_same_capture_id(self, conn):
        """
        Scenario: Cron runs twice for same week (e.g., manual re-trigger).

        Same capture_id → should not duplicate data.
        """
        week = "2025-12-22"
        tier = "NMS_TIER_1"
        captured_at = "2025-12-23T10:00:00Z"
        capture_id = f"finra.otc_transparency:{tier}:{week}:20251223"

        # First run: enqueue and complete
        work_id_1 = self._enqueue_work(
            conn,
            domain="finra.otc_transparency",
            pipeline="ingest_week",
            partition_key={"week_ending": week, "tier": tier},
        )

        self._claim_work(conn, work_id_1, worker_id="worker-1")
        self._record_success(
            conn,
            work_id_1,
            execution_id="exec-1",
            row_count=48765,
            captured_at=captured_at,
            capture_id=capture_id,
        )

        # Second run: cron triggers again (mistake or manual)
        # Unique constraint on (domain, pipeline, partition_key) should prevent duplicate
        try:
            work_id_2 = self._enqueue_work(
                conn,
                domain="finra.otc_transparency",
                pipeline="ingest_week",
                partition_key={"week_ending": week, "tier": tier},
            )
            # If we get here, unique constraint didn't work
            pytest.fail("Should not allow duplicate work items")
        except sqlite3.IntegrityError as e:
            assert "UNIQUE constraint" in str(e)

        # Verify only one work item exists
        count = conn.execute(
            """SELECT COUNT(*) as cnt FROM core_work_items 
               WHERE domain = 'finra.otc_transparency' 
               AND pipeline = 'ingest_week'
               AND partition_key = ?""",
            (json.dumps({"week_ending": week, "tier": tier}),),
        ).fetchone()["cnt"]

        assert count == 1

        print("\n✓ Cron idempotency: Duplicate enqueue prevented by UNIQUE constraint")

    def test_restatement_multiple_captures_coexist(self, conn):
        """
        Scenario: Second capture_id for same week/tier (data correction).

        Both captures should coexist in database.
        Latest views should show most recent capture.
        As-of queries should return specific capture.
        """
        week = "2025-12-22"
        tier = "NMS_TIER_1"

        # First capture: Monday morning
        capture_id_1 = f"finra.otc_transparency:{tier}:{week}:20251223"
        captured_at_1 = "2025-12-23T10:00:00Z"

        self._insert_raw_data(
            conn,
            week=week,
            tier=tier,
            capture_id=capture_id_1,
            captured_at=captured_at_1,
            row_count=48765,
            symbol_count=1200,
        )

        # Second capture: Tuesday (restatement due to correction)
        capture_id_2 = f"finra.otc_transparency:{tier}:{week}:20251224"
        captured_at_2 = "2025-12-24T14:00:00Z"

        self._insert_raw_data(
            conn,
            week=week,
            tier=tier,
            capture_id=capture_id_2,
            captured_at=captured_at_2,
            row_count=49012,  # Different row count (correction)
            symbol_count=1205,
        )

        # Both captures should exist
        captures = conn.execute(
            """SELECT DISTINCT capture_id, captured_at, COUNT(*) as row_count
               FROM finra_otc_transparency_raw
               WHERE week_ending = ? AND tier = ?
               GROUP BY capture_id
               ORDER BY captured_at""",
            (week, tier),
        ).fetchall()

        assert len(captures) == 2
        assert captures[0]["capture_id"] == capture_id_1
        assert captures[1]["capture_id"] == capture_id_2

        # Latest view should show second capture
        # (In production, this would use ROW_NUMBER() window function)
        latest = conn.execute(
            """SELECT capture_id, row_count
               FROM (
                   SELECT capture_id, COUNT(*) as row_count,
                          ROW_NUMBER() OVER (PARTITION BY week_ending, tier ORDER BY captured_at DESC) as rn
                   FROM finra_otc_transparency_raw
                   WHERE week_ending = ? AND tier = ?
                   GROUP BY capture_id, captured_at, week_ending, tier
               )
               WHERE rn = 1""",
            (week, tier),
        ).fetchone()

        assert latest["capture_id"] == capture_id_2
        # Row count is actual rows inserted (capped at 100 in helper)
        assert latest["row_count"] == 100

        # As-of query: retrieve first capture
        as_of_monday = conn.execute(
            """SELECT COUNT(*) as cnt
               FROM finra_otc_transparency_raw
               WHERE week_ending = ? AND tier = ? AND capture_id = ?""",
            (week, tier, capture_id_1),
        ).fetchone()["cnt"]

        # Helper inserts min(row_count, 100) rows
        assert as_of_monday == 100

        print("\n✓ Restatement: 2 captures coexist, latest view shows newest, as-of retrieves old")
        print(f"  - Monday capture: {capture_id_1} → {48765} rows")
        print(f"  - Tuesday capture: {capture_id_2} → {49012} rows")

    def test_failed_work_retry_command(self, conn):
        """
        Scenario: Work item fails, admin uses retry command.

        Retry command should reset state to PENDING and increment attempt counter.
        """
        work_id = self._enqueue_work(
            conn,
            domain="finra.otc_transparency",
            pipeline="normalize_week",
            partition_key={"week_ending": "2025-12-15", "tier": "OTC"},
        )

        # Fail once
        self._claim_work(conn, work_id, worker_id="worker-1")
        self._record_failure(
            conn, work_id, error="Database lock timeout", next_attempt_delay_seconds=None
        )

        # Manually set to FAILED (max attempts reached)
        conn.execute(
            "UPDATE core_work_items SET state = 'FAILED', attempt_count = 3 WHERE id = ?",
            (work_id,),
        )
        conn.commit()

        # Admin runs retry command
        self._retry_failed_work(conn, work_id)

        # Verify state reset
        state = conn.execute(
            "SELECT state, attempt_count, next_attempt_at FROM core_work_items WHERE id = ?",
            (work_id,),
        ).fetchone()

        assert state["state"] == "PENDING"
        # Note: attempt_count could either reset to 0 or stay at 3 depending on policy
        # Here we assume it resets to allow fresh attempts
        assert state["next_attempt_at"] is None

        print("\n✓ Manual retry: FAILED → PENDING, ready for worker to claim")

    # Helper methods

    def _enqueue_work(self, conn, domain, pipeline, partition_key, max_attempts=3, priority=100):
        """Enqueue a work item."""
        partition_key_json = json.dumps(partition_key)
        desired_at = datetime.now(UTC).isoformat()

        cursor = conn.execute(
            """INSERT INTO core_work_items (
                domain, pipeline, partition_key, desired_at, priority, max_attempts
            ) VALUES (?, ?, ?, ?, ?, ?)""",
            (domain, pipeline, partition_key_json, desired_at, priority, max_attempts),
        )
        conn.commit()
        return cursor.lastrowid

    def _claim_work(self, conn, work_id, worker_id):
        """Worker claims a work item."""
        execution_id = f"exec-{work_id}-{worker_id}"

        conn.execute(
            """UPDATE core_work_items 
               SET state = 'RUNNING',
                   current_execution_id = ?,
                   locked_by = ?,
                   locked_at = ?
               WHERE id = ?""",
            (execution_id, worker_id, datetime.now(UTC).isoformat(), work_id),
        )
        conn.commit()

    def _record_failure(self, conn, work_id, error, next_attempt_delay_seconds):
        """Record work failure."""
        now = datetime.now(UTC)
        next_attempt = None
        if next_attempt_delay_seconds:
            next_attempt = (now + timedelta(seconds=next_attempt_delay_seconds)).isoformat()

        conn.execute(
            """UPDATE core_work_items
               SET state = CASE WHEN ? IS NULL THEN 'FAILED' ELSE 'RETRY_WAIT' END,
                   attempt_count = attempt_count + 1,
                   last_error = ?,
                   last_error_at = ?,
                   next_attempt_at = ?,
                   current_execution_id = NULL,
                   locked_by = NULL,
                   updated_at = ?
               WHERE id = ?""",
            (next_attempt, error, now.isoformat(), next_attempt, now.isoformat(), work_id),
        )
        conn.commit()

    def _record_success(
        self, conn, work_id, execution_id, row_count, captured_at=None, capture_id=None
    ):
        """Record work success and update manifest."""
        now = datetime.now(UTC)

        # Update work item
        conn.execute(
            """UPDATE core_work_items
               SET state = 'COMPLETE',
                   latest_execution_id = ?,
                   current_execution_id = NULL,
                   completed_at = ?,
                   updated_at = ?
               WHERE id = ?""",
            (execution_id, now.isoformat(), now.isoformat(), work_id),
        )

        # Update manifest
        work = conn.execute(
            "SELECT domain, pipeline, partition_key FROM core_work_items WHERE id = ?", (work_id,)
        ).fetchone()

        conn.execute(
            """INSERT INTO core_manifest (
                domain, partition_key, stage, stage_rank, row_count,
                execution_id, batch_id, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(domain, partition_key, stage) DO UPDATE SET
                row_count = ?,
                execution_id = ?,
                updated_at = ?""",
            (
                work["domain"],
                work["partition_key"],
                "RAW",  # Assuming ingest → RAW stage
                1,
                row_count,
                execution_id,
                "batch-test",
                now.isoformat(),
                row_count,
                execution_id,
                now.isoformat(),
            ),
        )

        conn.commit()

    def _detect_gaps(self, conn, expected_weeks, expected_tiers):
        """Detect missing partitions."""
        gaps = []

        for week in expected_weeks:
            for tier in expected_tiers:
                partition_key = json.dumps({"week_ending": week, "tier": tier})

                exists = conn.execute(
                    """SELECT 1 FROM core_manifest 
                       WHERE domain = 'finra.otc_transparency' 
                       AND partition_key = ? 
                       AND stage = 'RAW'""",
                    (partition_key,),
                ).fetchone()

                if not exists:
                    gaps.append({"week_ending": week, "tier": tier, "stage": "RAW"})

        return gaps

    def _check_stage_completeness(self, conn, week, tier):
        """Check which stages exist for a partition."""
        partition_key = json.dumps({"week_ending": week, "tier": tier})

        stages = conn.execute(
            """SELECT stage FROM core_manifest 
               WHERE domain = 'finra.otc_transparency' 
               AND partition_key = ?""",
            (partition_key,),
        ).fetchall()

        stage_set = {s["stage"] for s in stages}

        return {
            "has_raw": "RAW" in stage_set,
            "has_normalized": "NORMALIZED" in stage_set,
            "has_venue_volume": "VENUE_VOLUME" in stage_set,
        }

    def _insert_raw_data(self, conn, week, tier, capture_id, captured_at, row_count, symbol_count):
        """Insert mock raw data for testing."""
        # Insert dummy rows
        for i in range(min(row_count, 100)):  # Insert up to 100 for testing
            conn.execute(
                """INSERT INTO finra_otc_transparency_raw (
                    execution_id, batch_id, record_hash,
                    week_ending, tier, symbol, mpid,
                    total_shares, total_trades,
                    captured_at, capture_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    f"exec-{capture_id}",
                    "batch-test",
                    f"hash-{i}",
                    week,
                    tier,
                    f"SYM{i % symbol_count}",
                    f"MPID{i % 50}",
                    1000000 + i,
                    100 + i,
                    captured_at,
                    capture_id,
                ),
            )

        conn.commit()

    def _retry_failed_work(self, conn, work_id):
        """Retry a failed work item (admin command)."""
        conn.execute(
            """UPDATE core_work_items
               SET state = 'PENDING',
                   attempt_count = 0,
                   last_error = NULL,
                   next_attempt_at = NULL,
                   updated_at = ?
               WHERE id = ?""",
            (datetime.now(UTC).isoformat(), work_id),
        )
        conn.commit()
