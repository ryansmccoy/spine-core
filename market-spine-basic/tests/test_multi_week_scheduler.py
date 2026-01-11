"""
Tests for multi-week scheduler with revision detection.

Test Coverage:
- Week window calculation
- Week list parsing
- Content hash computation
- Capture ID generation
- Revision detection (metadata + hash)
- Stage readiness checks
- Tier completeness checks
- Integration: Multiple scheduler runs with revision detection
"""

import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from market_spine.app.scheduler import (
    calculate_target_weeks,
    parse_week_list,
    compute_content_hash,
    generate_capture_id,
    check_revision_needed_via_metadata,
    check_revision_needed_via_hash,
    check_stage_ready,
    check_tier_completeness,
    record_anomaly,
    evaluate_readiness,
)


# ===== Unit Tests: Week Calculation =====

def test_calculate_target_weeks_monday():
    """Test week calculation when reference date is Monday."""
    # Monday, January 5, 2026
    reference = date(2026, 1, 5)
    weeks = calculate_target_weeks(4, reference)
    
    # Should get last 4 Fridays
    assert len(weeks) == 4
    assert weeks[0] == date(2026, 1, 2)   # Most recent Friday (Jan 2, not 3)
    assert weeks[1] == date(2025, 12, 26)
    assert weeks[2] == date(2025, 12, 19)
    assert weeks[3] == date(2025, 12, 12)
    
    # All should be Fridays (weekday = 4)
    for week in weeks:
        assert week.weekday() == 4


def test_calculate_target_weeks_friday():
    """Test week calculation when reference date is Friday."""
    # Friday, January 2, 2026
    reference = date(2026, 1, 2)
    weeks = calculate_target_weeks(4, reference)
    
    # Should include today (Friday) as most recent
    assert len(weeks) == 4
    assert weeks[0] == date(2026, 1, 2)   # Today
    assert weeks[1] == date(2025, 12, 26)
    assert weeks[2] == date(2025, 12, 19)
    assert weeks[3] == date(2025, 12, 12)


def test_calculate_target_weeks_default_today():
    """Test week calculation uses today if reference_date not provided."""
    weeks = calculate_target_weeks(2)
    
    # Should get 2 weeks
    assert len(weeks) == 2
    
    # All should be Fridays
    for week in weeks:
        assert week.weekday() == 4
    
    # Most recent Friday should be <= today
    today = date.today()
    assert weeks[0] <= today


def test_parse_week_list_valid():
    """Test parsing valid comma-separated week list."""
    weeks = parse_week_list("2025-12-26,2025-12-19,2025-12-12")
    
    assert len(weeks) == 3
    assert weeks[0] == date(2025, 12, 26)
    assert weeks[1] == date(2025, 12, 19)
    assert weeks[2] == date(2025, 12, 12)


def test_parse_week_list_not_friday():
    """Test parsing rejects non-Friday dates."""
    with pytest.raises(ValueError, match="not a Friday"):
        parse_week_list("2025-12-25")  # Thursday


def test_parse_week_list_invalid_format():
    """Test parsing rejects invalid date format."""
    with pytest.raises(ValueError, match="Invalid date format"):
        parse_week_list("2025/12/26")  # Wrong separator


# ===== Unit Tests: Content Hash =====

def test_compute_content_hash_deterministic():
    """Test content hash is deterministic."""
    content = b"Symbol|Venue|Shares\nAAPL|NASDAQ|1000\n"
    
    hash1 = compute_content_hash(content)
    hash2 = compute_content_hash(content)
    
    assert hash1 == hash2
    assert len(hash1) == 16  # First 16 chars of SHA256


def test_compute_content_hash_different():
    """Test different content produces different hashes."""
    content1 = b"Symbol|Venue|Shares\nAAPL|NASDAQ|1000\n"
    content2 = b"Symbol|Venue|Shares\nAAPL|NASDAQ|2000\n"
    
    hash1 = compute_content_hash(content1)
    hash2 = compute_content_hash(content2)
    
    assert hash1 != hash2


# ===== Unit Tests: Capture ID =====

def test_generate_capture_id_format():
    """Test capture_id has correct format."""
    capture_id = generate_capture_id(
        "finra.otc_transparency",
        date(2025, 12, 26),
        "NMS_TIER_1",
        date(2025, 12, 30)
    )
    
    assert capture_id == "finra.otc_transparency:NMS_TIER_1:2025-12-26:20251230"


def test_generate_capture_id_same_day_replay():
    """Test same run_date produces same capture_id (replay)."""
    run_date = date(2025, 12, 30)
    
    id1 = generate_capture_id("finra.otc_transparency", date(2025, 12, 26), "NMS_TIER_1", run_date)
    id2 = generate_capture_id("finra.otc_transparency", date(2025, 12, 26), "NMS_TIER_1", run_date)
    
    assert id1 == id2


def test_generate_capture_id_different_day_restatement():
    """Test different run_date produces different capture_id (restatement)."""
    id1 = generate_capture_id("finra.otc_transparency", date(2025, 12, 26), "NMS_TIER_1", date(2025, 12, 30))
    id2 = generate_capture_id("finra.otc_transparency", date(2025, 12, 26), "NMS_TIER_1", date(2025, 12, 31))
    
    assert id1 != id2
    assert id1.endswith(":20251230")
    assert id2.endswith(":20251231")


# ===== Integration Tests: Revision Detection =====

@pytest.fixture
def test_db():
    """Create test database with schema."""
    conn = sqlite3.connect(":memory:")
    
    # Create minimal schema (core_manifest + core_anomalies)
    conn.executescript("""
        CREATE TABLE core_manifest (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            domain TEXT NOT NULL,
            stage TEXT NOT NULL,
            partition_key TEXT NOT NULL,
            row_count INTEGER,
            metadata_json TEXT,
            capture_id TEXT,
            captured_at TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        
        CREATE TABLE core_anomalies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            domain TEXT NOT NULL,
            pipeline TEXT,
            partition_key TEXT,
            stage TEXT,
            severity TEXT NOT NULL,
            category TEXT NOT NULL,
            message TEXT NOT NULL,
            details_json TEXT,
            affected_records INTEGER,
            execution_id TEXT,
            capture_id TEXT,
            detected_at TEXT NOT NULL,
            resolved_at TEXT,
            resolution_note TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        
        CREATE TABLE core_data_readiness (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            domain TEXT NOT NULL,
            partition_key TEXT NOT NULL,
            is_ready INTEGER DEFAULT 0,
            ready_for TEXT,
            all_partitions_present INTEGER DEFAULT 0,
            all_stages_complete INTEGER DEFAULT 0,
            no_critical_anomalies INTEGER DEFAULT 0,
            blocking_issues TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(domain, partition_key, ready_for)
        );
    """)
    
    yield conn
    conn.close()


def test_check_revision_needed_via_hash_first_ingest(test_db):
    """Test revision detection on first ingest (no prior capture)."""
    content = b"Symbol|Venue|Shares\nAAPL|NASDAQ|1000\n"
    
    needs_revision, reason = check_revision_needed_via_hash(
        date(2025, 12, 26),
        "NMS_TIER_1",
        content,
        test_db
    )
    
    assert needs_revision is True
    assert "No prior capture" in reason


def test_check_revision_needed_via_hash_content_changed(test_db):
    """Test revision detection when content changed."""
    week_ending = date(2025, 12, 26)
    tier = "NMS_TIER_1"
    
    # Insert prior capture with content hash
    old_content = b"Symbol|Venue|Shares\nAAPL|NASDAQ|1000\n"
    old_hash = compute_content_hash(old_content)
    
    test_db.execute("""
        INSERT INTO core_manifest (domain, stage, partition_key, row_count, metadata_json, captured_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        "finra.otc_transparency",
        "RAW",
        '{"week_ending": "2025-12-26", "tier": "NMS_TIER_1"}',
        100,
        f'{{"content_hash": "{old_hash}"}}',
        "2025-12-30T10:00:00"
    ))
    test_db.commit()
    
    # New content (different)
    new_content = b"Symbol|Venue|Shares\nAAPL|NASDAQ|2000\n"
    
    needs_revision, reason = check_revision_needed_via_hash(
        week_ending, tier, new_content, test_db
    )
    
    assert needs_revision is True
    assert "Content changed" in reason


def test_check_revision_needed_via_hash_content_identical(test_db):
    """Test revision detection when content unchanged."""
    week_ending = date(2025, 12, 26)
    tier = "NMS_TIER_1"
    
    # Insert prior capture
    content = b"Symbol|Venue|Shares\nAAPL|NASDAQ|1000\n"
    content_hash = compute_content_hash(content)
    
    test_db.execute("""
        INSERT INTO core_manifest (domain, stage, partition_key, row_count, metadata_json, captured_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        "finra.otc_transparency",
        "RAW",
        '{"week_ending": "2025-12-26", "tier": "NMS_TIER_1"}',
        100,
        f'{{"content_hash": "{content_hash}"}}',
        "2025-12-30T10:00:00"
    ))
    test_db.commit()
    
    # Same content
    needs_revision, reason = check_revision_needed_via_hash(
        week_ending, tier, content, test_db
    )
    
    assert needs_revision is False
    assert "Content identical" in reason


def test_check_revision_needed_via_metadata_source_updated(test_db):
    """Test revision detection via metadata when source updated."""
    week_ending = date(2025, 12, 26)
    tier = "NMS_TIER_1"
    
    # Insert prior capture with old source_last_updated
    test_db.execute("""
        INSERT INTO core_manifest (domain, stage, partition_key, row_count, metadata_json, captured_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        "finra.otc_transparency",
        "RAW",
        '{"week_ending": "2025-12-26", "tier": "NMS_TIER_1"}',
        100,
        '{"source_last_updated": "2025-12-30T10:00:00"}',
        "2025-12-30T10:00:00"
    ))
    test_db.commit()
    
    # Source updated later
    source_last_updated = datetime(2025, 12, 31, 14, 0)
    
    needs_revision, reason = check_revision_needed_via_metadata(
        week_ending, tier, source_last_updated, test_db
    )
    
    assert needs_revision is True
    assert "Source updated" in reason
    assert "2025-12-31 14:00" in reason


def test_check_revision_needed_via_metadata_source_unchanged(test_db):
    """Test revision detection via metadata when source unchanged."""
    week_ending = date(2025, 12, 26)
    tier = "NMS_TIER_1"
    
    # Insert prior capture
    test_db.execute("""
        INSERT INTO core_manifest (domain, stage, partition_key, row_count, metadata_json, captured_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        "finra.otc_transparency",
        "RAW",
        '{"week_ending": "2025-12-26", "tier": "NMS_TIER_1"}',
        100,
        '{"source_last_updated": "2025-12-30T10:00:00"}',
        "2025-12-30T10:00:00"
    ))
    test_db.commit()
    
    # Source unchanged
    source_last_updated = datetime(2025, 12, 30, 10, 0)
    
    needs_revision, reason = check_revision_needed_via_metadata(
        week_ending, tier, source_last_updated, test_db
    )
    
    assert needs_revision is False
    assert "Source unchanged" in reason


# ===== Integration Tests: Stage/Tier Checks =====

def test_check_stage_ready_exists(test_db):
    """Test stage readiness check when stage has data."""
    # Insert RAW stage
    test_db.execute("""
        INSERT INTO core_manifest (domain, stage, partition_key, row_count, captured_at)
        VALUES (?, ?, ?, ?, ?)
    """, (
        "finra.otc_transparency",
        "RAW",
        '{"week_ending": "2025-12-26", "tier": "NMS_TIER_1"}',
        1000,
        "2025-12-30T10:00:00"
    ))
    test_db.commit()
    
    ready = check_stage_ready(date(2025, 12, 26), "NMS_TIER_1", "RAW", test_db)
    assert ready is True


def test_check_stage_ready_missing(test_db):
    """Test stage readiness check when stage missing."""
    ready = check_stage_ready(date(2025, 12, 26), "NMS_TIER_1", "RAW", test_db)
    assert ready is False


def test_check_tier_completeness_all_present(test_db):
    """Test tier completeness when all 3 tiers present."""
    week_ending = date(2025, 12, 26)
    
    # Insert all 3 tiers
    for tier in ["NMS_TIER_1", "NMS_TIER_2", "OTC"]:
        test_db.execute("""
            INSERT INTO core_manifest (domain, stage, partition_key, row_count, captured_at)
            VALUES (?, ?, ?, ?, ?)
        """, (
            "finra.otc_transparency",
            "RAW",
            f'{{"week_ending": "2025-12-26", "tier": "{tier}"}}',
            1000,
            "2025-12-30T10:00:00"
        ))
    test_db.commit()
    
    all_present, missing = check_tier_completeness(week_ending, test_db)
    
    assert all_present is True
    assert len(missing) == 0


def test_check_tier_completeness_missing_one(test_db):
    """Test tier completeness when one tier missing."""
    week_ending = date(2025, 12, 26)
    
    # Insert only 2 tiers
    for tier in ["NMS_TIER_1", "NMS_TIER_2"]:
        test_db.execute("""
            INSERT INTO core_manifest (domain, stage, partition_key, row_count, captured_at)
            VALUES (?, ?, ?, ?, ?)
        """, (
            "finra.otc_transparency",
            "RAW",
            f'{{"week_ending": "2025-12-26", "tier": "{tier}"}}',
            1000,
            "2025-12-30T10:00:00"
        ))
    test_db.commit()
    
    all_present, missing = check_tier_completeness(week_ending, test_db)
    
    assert all_present is False
    assert missing == {"OTC"}


# ===== Integration Tests: Anomaly Recording =====

def test_record_anomaly_basic(test_db):
    """Test recording basic anomaly."""
    anomaly_id = record_anomaly(
        test_db,
        domain="finra.otc_transparency",
        severity="ERROR",
        category="SOURCE_UNAVAILABLE",
        message="API fetch failed (HTTP 503)",
        partition_key={"week_ending": "2025-12-26", "tier": "OTC"}
    )
    
    assert anomaly_id > 0
    
    # Verify record
    row = test_db.execute("""
        SELECT severity, category, message, partition_key
        FROM core_anomalies WHERE id = ?
    """, (anomaly_id,)).fetchone()
    
    assert row[0] == "ERROR"
    assert row[1] == "SOURCE_UNAVAILABLE"
    assert row[2] == "API fetch failed (HTTP 503)"
    assert '"week_ending": "2025-12-26"' in row[3]


# ===== Integration Tests: Readiness Evaluation =====

def test_evaluate_readiness_all_criteria_met(test_db):
    """Test readiness evaluation when all criteria met."""
    week_ending = date(2025, 12, 26)
    
    # Insert all 3 tiers with RAW + NORMALIZED
    for tier in ["NMS_TIER_1", "NMS_TIER_2", "OTC"]:
        for stage in ["RAW", "NORMALIZED"]:
            test_db.execute("""
                INSERT INTO core_manifest (domain, stage, partition_key, row_count, captured_at)
                VALUES (?, ?, ?, ?, ?)
            """, (
                "finra.otc_transparency",
                stage,
                f'{{"week_ending": "2025-12-26", "tier": "{tier}"}}',
                1000,
                "2025-12-30T10:00:00"
            ))
    test_db.commit()
    
    is_ready, blocking_issues = evaluate_readiness(week_ending, test_db)
    
    assert is_ready is True
    assert len(blocking_issues) == 0
    
    # Verify readiness record
    row = test_db.execute("""
        SELECT is_ready, all_partitions_present, all_stages_complete, no_critical_anomalies
        FROM core_data_readiness
        WHERE domain = 'finra.otc_transparency'
    """).fetchone()
    
    assert row[0] == 1  # is_ready
    assert row[1] == 1  # all_partitions_present
    assert row[2] == 1  # all_stages_complete
    assert row[3] == 1  # no_critical_anomalies


def test_evaluate_readiness_missing_tier(test_db):
    """Test readiness evaluation when tier missing."""
    week_ending = date(2025, 12, 26)
    
    # Insert only 2 tiers
    for tier in ["NMS_TIER_1", "NMS_TIER_2"]:
        test_db.execute("""
            INSERT INTO core_manifest (domain, stage, partition_key, row_count, captured_at)
            VALUES (?, ?, ?, ?, ?)
        """, (
            "finra.otc_transparency",
            "RAW",
            f'{{"week_ending": "2025-12-26", "tier": "{tier}"}}',
            1000,
            "2025-12-30T10:00:00"
        ))
    test_db.commit()
    
    is_ready, blocking_issues = evaluate_readiness(week_ending, test_db)
    
    assert is_ready is False
    assert len(blocking_issues) > 0
    assert "Missing tiers: OTC" in blocking_issues[0]


def test_evaluate_readiness_critical_anomaly(test_db):
    """Test readiness evaluation blocked by critical anomaly."""
    week_ending = date(2025, 12, 26)
    
    # Insert all 3 tiers (complete)
    for tier in ["NMS_TIER_1", "NMS_TIER_2", "OTC"]:
        for stage in ["RAW", "NORMALIZED"]:
            test_db.execute("""
                INSERT INTO core_manifest (domain, stage, partition_key, row_count, captured_at)
                VALUES (?, ?, ?, ?, ?)
            """, (
                "finra.otc_transparency",
                stage,
                f'{{"week_ending": "2025-12-26", "tier": "{tier}"}}',
                1000,
                "2025-12-30T10:00:00"
            ))
    
    # Insert CRITICAL anomaly
    test_db.execute("""
        INSERT INTO core_anomalies (domain, severity, category, message, partition_key, detected_at)
        VALUES (?, ?, ?, ?, ?, datetime('now'))
    """, (
        "finra.otc_transparency",
        "CRITICAL",
        "BUSINESS_RULE",
        "Zero-volume trades detected",
        '{"week_ending": "2025-12-26"}'
    ))
    test_db.commit()
    
    is_ready, blocking_issues = evaluate_readiness(week_ending, test_db)
    
    assert is_ready is False
    assert any("CRITICAL anomalies" in issue for issue in blocking_issues)


# ===== Integration Test: Multi-Run Scheduler Simulation =====

def test_scheduler_multi_run_revision_detection(test_db):
    """
    Integration test: Simulate multiple scheduler runs with revision detection.
    
    Scenario:
    - Monday run: Ingest 3 weeks, all new (first ingest)
    - Tuesday run (same day): Skip all (unchanged content)
    - Wednesday run: Week 1 changed, re-ingest only that week
    - Verify: Multiple captures exist, latest views work
    """
    
    # === Monday Run (2025-12-30) ===
    run_date_monday = date(2025, 12, 30)
    weeks = [date(2025, 12, 26), date(2025, 12, 19), date(2025, 12, 12)]
    
    monday_content = {
        weeks[0]: b"Symbol|Venue|Shares\nAAPL|NASDAQ|1000\n",
        weeks[1]: b"Symbol|Venue|Shares\nMSFT|NYSE|2000\n",
        weeks[2]: b"Symbol|Venue|Shares\nGOOG|NASDAQ|3000\n",
    }
    
    # Ingest all weeks (first time)
    for week_ending in weeks:
        content = monday_content[week_ending]
        
        # Check revision needed (should be True - first ingest)
        needs_revision, reason = check_revision_needed_via_hash(
            week_ending, "NMS_TIER_1", content, test_db
        )
        assert needs_revision is True
        assert "No prior capture" in reason
        
        # Simulate ingest: insert manifest
        capture_id = generate_capture_id("finra.otc_transparency", week_ending, "NMS_TIER_1", run_date_monday)
        content_hash = compute_content_hash(content)
        
        test_db.execute("""
            INSERT INTO core_manifest (domain, stage, partition_key, row_count, metadata_json, capture_id, captured_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            "finra.otc_transparency",
            "RAW",
            f'{{"week_ending": "{week_ending.isoformat()}", "tier": "NMS_TIER_1"}}',
            100,
            f'{{"content_hash": "{content_hash}"}}',
            capture_id,
            "2025-12-30T10:00:00"
        ))
    test_db.commit()
    
    # === Tuesday Run (same day, 2025-12-30) ===
    # Content unchanged, should skip all
    for week_ending in weeks:
        content = monday_content[week_ending]
        
        needs_revision, reason = check_revision_needed_via_hash(
            week_ending, "NMS_TIER_1", content, test_db
        )
        
        assert needs_revision is False
        assert "Content identical" in reason
    
    # === Wednesday Run (2025-12-31) ===
    run_date_wednesday = date(2025, 12, 31)
    
    # Week 1 content changed
    wednesday_content_week1 = b"Symbol|Venue|Shares\nAAPL|NASDAQ|1500\n"  # Changed shares
    
    # Week 1: Should detect change
    needs_revision, reason = check_revision_needed_via_hash(
        weeks[0], "NMS_TIER_1", wednesday_content_week1, test_db
    )
    assert needs_revision is True
    assert "Content changed" in reason
    
    # Ingest week 1 with new capture_id
    capture_id_wed = generate_capture_id("finra.otc_transparency", weeks[0], "NMS_TIER_1", run_date_wednesday)
    content_hash_wed = compute_content_hash(wednesday_content_week1)
    
    test_db.execute("""
        INSERT INTO core_manifest (domain, stage, partition_key, row_count, metadata_json, capture_id, captured_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        "finra.otc_transparency",
        "RAW",
        f'{{"week_ending": "{weeks[0].isoformat()}", "tier": "NMS_TIER_1"}}',
        150,  # More rows
        f'{{"content_hash": "{content_hash_wed}"}}',
        capture_id_wed,
        "2025-12-31T10:00:00"
    ))
    test_db.commit()
    
    # Weeks 2-3: Should skip (unchanged)
    for week_ending in weeks[1:]:
        content = monday_content[week_ending]
        needs_revision, reason = check_revision_needed_via_hash(
            week_ending, "NMS_TIER_1", content, test_db
        )
        assert needs_revision is False
    
    # === Verify Database State ===
    
    # Week 1 should have 2 captures (Monday + Wednesday)
    rows = test_db.execute("""
        SELECT capture_id, row_count, captured_at
        FROM core_manifest
        WHERE domain = 'finra.otc_transparency'
          AND json_extract(partition_key, '$.week_ending') = ?
        ORDER BY captured_at
    """, (weeks[0].isoformat(),)).fetchall()
    
    assert len(rows) == 2
    assert rows[0][1] == 100  # Monday: 100 rows
    assert rows[1][1] == 150  # Wednesday: 150 rows
    assert ":20251230" in rows[0][0]  # Monday capture_id
    assert ":20251231" in rows[1][0]  # Wednesday capture_id
    
    # Weeks 2-3 should have 1 capture each (Monday only)
    for week_ending in weeks[1:]:
        rows = test_db.execute("""
            SELECT COUNT(*) FROM core_manifest
            WHERE domain = 'finra.otc_transparency'
              AND json_extract(partition_key, '$.week_ending') = ?
        """, (week_ending.isoformat(),)).fetchone()
        
        assert rows[0] == 1  # Only Monday capture
    
    # Latest query for week 1 should return Wednesday data (150 rows)
    latest = test_db.execute("""
        SELECT row_count FROM core_manifest
        WHERE domain = 'finra.otc_transparency'
          AND json_extract(partition_key, '$.week_ending') = ?
        ORDER BY captured_at DESC
        LIMIT 1
    """, (weeks[0].isoformat(),)).fetchone()
    
    assert latest[0] == 150  # Wednesday capture


# ===== Test: Scheduler Script Integration (would need fixture data) =====

@pytest.mark.skip(reason="Requires fixture data files and full app context")
def test_scheduler_script_end_to_end():
    """
    End-to-end test of run_finra_weekly_schedule.py script.
    
    This would:
    1. Create fixture data files
    2. Run scheduler with --lookback-weeks 3
    3. Verify ingestion succeeded
    4. Re-run scheduler (should skip unchanged)
    5. Modify one fixture file
    6. Re-run scheduler (should restate only changed week)
    """
    pass
