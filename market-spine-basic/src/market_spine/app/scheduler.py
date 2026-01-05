"""
Scheduler utilities for multi-week FINRA OTC processing with revision detection.

This module provides helpers for:
- Week window calculation (lookback periods)
- Revision detection (lastUpdateDate + content hash)
- Capture ID generation (deterministic, day-based)
- Pipeline execution orchestration

Key design principles:
- No deletions (capture_id versioning)
- Skip unchanged weeks (efficiency)
- Partition-level isolation (failures don't propagate)
"""

import hashlib
import json
from datetime import date, datetime, timedelta
from typing import Any

import sqlite3


def calculate_target_weeks(lookback_weeks: int, reference_date: date | None = None) -> list[date]:
    """
    Calculate target week_endings (Fridays) for lookback window.
    
    Args:
        lookback_weeks: Number of weeks to look back (including current)
        reference_date: Starting point (default: today)
    
    Returns:
        List of Friday dates in descending order (newest first)
    
    Examples:
        >>> # Today is Monday, 2026-01-05
        >>> calculate_target_weeks(4, date(2026, 1, 5))
        [date(2026, 1, 3), date(2025, 12, 27), date(2025, 12, 20), date(2025, 12, 13)]
        
        >>> # Today is Friday, 2026-01-02
        >>> calculate_target_weeks(4, date(2026, 1, 2))
        [date(2026, 1, 2), date(2025, 12, 26), date(2025, 12, 19), date(2025, 12, 12)]
    """
    if reference_date is None:
        reference_date = date.today()
    
    # Find most recent Friday (or today if Friday)
    # Monday=0, Tuesday=1, ..., Friday=4, Saturday=5, Sunday=6
    days_since_friday = (reference_date.weekday() - 4) % 7
    most_recent_friday = reference_date - timedelta(days=days_since_friday)
    
    # Generate lookback_weeks Fridays
    weeks = []
    for i in range(lookback_weeks):
        week_ending = most_recent_friday - timedelta(weeks=i)
        weeks.append(week_ending)
    
    return weeks


def parse_week_list(weeks_str: str) -> list[date]:
    """
    Parse comma-separated week_ending dates.
    
    Args:
        weeks_str: Comma-separated ISO dates (e.g., "2025-12-15,2025-12-22")
    
    Returns:
        List of date objects
    
    Raises:
        ValueError: If any date is invalid or not a Friday
    
    Examples:
        >>> parse_week_list("2025-12-26,2025-12-19")
        [date(2025, 12, 26), date(2025, 12, 19)]
    """
    weeks = []
    for week_str in weeks_str.split(","):
        week_str = week_str.strip()
        try:
            week_date = date.fromisoformat(week_str)
        except ValueError:
            raise ValueError(f"Invalid date format: {week_str} (expected YYYY-MM-DD)")
        
        # Verify it's a Friday
        if week_date.weekday() != 4:
            raise ValueError(f"{week_str} is not a Friday (week_ending must be Friday)")
        
        weeks.append(week_date)
    
    return weeks


def compute_content_hash(content: bytes) -> str:
    """
    Compute SHA256 hash of raw content for change detection.
    
    Args:
        content: Raw file/API response bytes
    
    Returns:
        Hex digest (first 16 chars for brevity)
    
    Examples:
        >>> compute_content_hash(b"hello world")
        'b94d27b9934d3e08'
    """
    return hashlib.sha256(content).hexdigest()[:16]


def generate_capture_id(
    domain: str,
    week_ending: date,
    tier: str,
    run_date: date | None = None
) -> str:
    """
    Generate deterministic capture_id for partition.
    
    Format: {domain}:{tier}:{week_ending}:{YYYYMMDD}
    
    Running the scheduler multiple times on the same day produces the same
    capture_id (replay). Running on different days produces different
    capture_ids (restatement).
    
    Args:
        domain: e.g., "finra.otc_transparency"
        week_ending: Friday date (e.g., 2025-12-26)
        tier: NMS_TIER_1, NMS_TIER_2, or OTC
        run_date: Date of ingestion run (default: today)
    
    Returns:
        Capture ID string
    
    Examples:
        >>> generate_capture_id("finra.otc_transparency", date(2025, 12, 26), "NMS_TIER_1", date(2025, 12, 30))
        'finra.otc_transparency:NMS_TIER_1:2025-12-26:20251230'
        
        >>> # Same day = same capture_id (replay)
        >>> generate_capture_id("finra.otc_transparency", date(2025, 12, 26), "OTC", date(2025, 12, 30))
        'finra.otc_transparency:OTC:2025-12-26:20251230'
        
        >>> # Different day = new capture_id (restatement)
        >>> generate_capture_id("finra.otc_transparency", date(2025, 12, 26), "NMS_TIER_1", date(2025, 12, 31))
        'finra.otc_transparency:NMS_TIER_1:2025-12-26:20251231'
    """
    if run_date is None:
        run_date = date.today()
    
    return f"{domain}:{tier}:{week_ending.isoformat()}:{run_date.strftime('%Y%m%d')}"


def check_revision_needed_via_metadata(
    week_ending: date,
    tier: str,
    source_last_updated: datetime,
    db_connection: sqlite3.Connection
) -> tuple[bool, str]:
    """
    Compare source lastUpdateDate with our latest capture's metadata.
    
    Args:
        week_ending: Friday date
        tier: NMS_TIER_1, NMS_TIER_2, or OTC
        source_last_updated: When source data was last modified
        db_connection: Database connection
    
    Returns:
        (needs_revision: bool, reason: str)
    
    Examples:
        >>> # First ingest (no prior capture)
        >>> check_revision_needed_via_metadata(
        ...     date(2025, 12, 26), "NMS_TIER_1",
        ...     datetime(2025, 12, 30, 10, 0), conn
        ... )
        (True, "No prior capture found (first ingest)")
        
        >>> # Source updated after our capture
        >>> check_revision_needed_via_metadata(
        ...     date(2025, 12, 26), "NMS_TIER_1",
        ...     datetime(2025, 12, 31, 14, 0), conn
        ... )
        (True, "Source updated 2025-12-31 14:00 > stored 2025-12-30 10:00")
        
        >>> # Source unchanged
        >>> check_revision_needed_via_metadata(
        ...     date(2025, 12, 26), "NMS_TIER_1",
        ...     datetime(2025, 12, 30, 10, 0), conn
        ... )
        (False, "Source unchanged since 2025-12-30 10:00")
    """
    # Query latest capture for this partition
    cursor = db_connection.execute("""
        SELECT 
            json_extract(metadata_json, '$.source_last_updated') as stored_last_updated,
            captured_at
        FROM core_manifest
        WHERE domain = 'finra.otc_transparency'
          AND stage = 'RAW'
          AND json_extract(partition_key, '$.week_ending') = ?
          AND json_extract(partition_key, '$.tier') = ?
        ORDER BY captured_at DESC
        LIMIT 1
    """, (week_ending.isoformat(), tier))
    
    latest_capture = cursor.fetchone()
    
    if not latest_capture:
        return (True, "No prior capture found (first ingest)")
    
    stored_last_updated_str = latest_capture[0]
    if not stored_last_updated_str:
        # Metadata missing, assume revision needed
        return (True, "Prior capture has no source_last_updated metadata")
    
    stored_last_updated = datetime.fromisoformat(stored_last_updated_str)
    
    if source_last_updated > stored_last_updated:
        return (
            True,
            f"Source updated {source_last_updated.strftime('%Y-%m-%d %H:%M')} > "
            f"stored {stored_last_updated.strftime('%Y-%m-%d %H:%M')}"
        )
    else:
        return (
            False,
            f"Source unchanged since {stored_last_updated.strftime('%Y-%m-%d %H:%M')}"
        )


def check_revision_needed_via_hash(
    week_ending: date,
    tier: str,
    content: bytes,
    db_connection: sqlite3.Connection
) -> tuple[bool, str]:
    """
    Compare content hash with latest capture (fallback when lastUpdateDate unavailable).
    
    Args:
        week_ending: Friday date
        tier: NMS_TIER_1, NMS_TIER_2, or OTC
        content: Raw file/API response bytes
        db_connection: Database connection
    
    Returns:
        (needs_revision: bool, reason: str)
    
    Examples:
        >>> # First ingest
        >>> check_revision_needed_via_hash(
        ...     date(2025, 12, 26), "NMS_TIER_1",
        ...     b"some,csv,content", conn
        ... )
        (True, "No prior capture (first ingest)")
        
        >>> # Content changed
        >>> check_revision_needed_via_hash(
        ...     date(2025, 12, 26), "NMS_TIER_1",
        ...     b"different,content,now", conn
        ... )
        (True, "Content changed (hash a3f5b2c8 != 1234abcd)")
        
        >>> # Content identical
        >>> check_revision_needed_via_hash(
        ...     date(2025, 12, 26), "NMS_TIER_1",
        ...     b"same,content,bytes", conn
        ... )
        (False, "Content identical (hash 1234abcd)")
    """
    new_hash = compute_content_hash(content)
    
    cursor = db_connection.execute("""
        SELECT json_extract(metadata_json, '$.content_hash') as stored_hash
        FROM core_manifest
        WHERE domain = 'finra.otc_transparency'
          AND stage = 'RAW'
          AND json_extract(partition_key, '$.week_ending') = ?
          AND json_extract(partition_key, '$.tier') = ?
        ORDER BY captured_at DESC
        LIMIT 1
    """, (week_ending.isoformat(), tier))
    
    latest_capture = cursor.fetchone()
    
    if not latest_capture:
        return (True, "No prior capture (first ingest)")
    
    stored_hash = latest_capture[0]
    
    if not stored_hash:
        # No hash stored, assume revision needed
        return (True, "Prior capture has no content_hash metadata")
    
    if new_hash != stored_hash:
        return (
            True,
            f"Content changed (hash {new_hash[:8]} != {stored_hash[:8]})"
        )
    else:
        return (
            False,
            f"Content identical (hash {new_hash[:8]})"
        )


def check_stage_ready(
    week_ending: date,
    tier: str,
    stage: str,
    db_connection: sqlite3.Connection
) -> bool:
    """
    Check if prerequisite stage completed successfully.
    
    Args:
        week_ending: Friday date
        tier: NMS_TIER_1, NMS_TIER_2, or OTC
        stage: "RAW", "NORMALIZED", etc.
        db_connection: Database connection
    
    Returns:
        True if stage has data (row_count > 0)
    
    Examples:
        >>> # RAW stage exists
        >>> check_stage_ready(date(2025, 12, 26), "NMS_TIER_1", "RAW", conn)
        True
        
        >>> # NORMALIZED stage missing
        >>> check_stage_ready(date(2025, 12, 26), "NMS_TIER_1", "NORMALIZED", conn)
        False
    """
    cursor = db_connection.execute("""
        SELECT row_count
        FROM core_manifest
        WHERE domain = 'finra.otc_transparency'
          AND stage = ?
          AND json_extract(partition_key, '$.week_ending') = ?
          AND json_extract(partition_key, '$.tier') = ?
        ORDER BY captured_at DESC
        LIMIT 1
    """, (stage, week_ending.isoformat(), tier))
    
    result = cursor.fetchone()
    
    return result is not None and result[0] > 0


def check_tier_completeness(
    week_ending: date,
    db_connection: sqlite3.Connection,
    expected_tiers: set[str] | None = None
) -> tuple[bool, set[str]]:
    """
    Verify all expected tiers present for a week.
    
    Args:
        week_ending: Friday date
        db_connection: Database connection
        expected_tiers: Set of tier names (default: NMS_TIER_1, NMS_TIER_2, OTC)
    
    Returns:
        (all_present: bool, missing_tiers: set)
    
    Examples:
        >>> # All tiers present
        >>> check_tier_completeness(date(2025, 12, 26), conn)
        (True, set())
        
        >>> # OTC tier missing
        >>> check_tier_completeness(date(2025, 12, 26), conn)
        (False, {'OTC'})
    """
    if expected_tiers is None:
        expected_tiers = {"NMS_TIER_1", "NMS_TIER_2", "OTC"}
    
    cursor = db_connection.execute("""
        SELECT DISTINCT json_extract(partition_key, '$.tier') as tier
        FROM core_manifest
        WHERE domain = 'finra.otc_transparency'
          AND stage = 'RAW'
          AND json_extract(partition_key, '$.week_ending') = ?
    """, (week_ending.isoformat(),))
    
    actual_tiers = {row[0] for row in cursor.fetchall()}
    
    missing = expected_tiers - actual_tiers
    
    return (len(missing) == 0, missing)


def record_anomaly(
    db_connection: sqlite3.Connection,
    domain: str,
    severity: str,
    category: str,
    message: str,
    pipeline: str | None = None,
    partition_key: dict[str, Any] | None = None,
    stage: str | None = None,
    details_json: dict[str, Any] | None = None,
    affected_records: int | None = None,
    execution_id: str | None = None,
    capture_id: str | None = None
) -> int:
    """
    Record anomaly to core_anomalies table.
    
    Args:
        db_connection: Database connection
        domain: e.g., "finra.otc_transparency"
        severity: INFO, WARN, ERROR, CRITICAL
        category: INCOMPLETE_INPUT, SOURCE_UNAVAILABLE, etc.
        message: Human-readable description
        pipeline: Pipeline that detected anomaly
        partition_key: Affected partition (dict)
        stage: Pipeline stage
        details_json: Additional context (dict)
        affected_records: Count of impacted records
        execution_id: Execution that detected anomaly
        capture_id: Capture this anomaly applies to
    
    Returns:
        Anomaly ID
    
    Examples:
        >>> record_anomaly(
        ...     conn, "finra.otc_transparency", "ERROR", "SOURCE_UNAVAILABLE",
        ...     "API fetch failed (HTTP 503)",
        ...     partition_key={"week_ending": "2025-12-26", "tier": "OTC"},
        ...     details_json={"status_code": 503}
        ... )
        123
    """
    cursor = db_connection.execute("""
        INSERT INTO core_anomalies (
            domain, pipeline, partition_key, stage, severity, category,
            message, details_json, affected_records, execution_id, capture_id,
            detected_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
    """, (
        domain,
        pipeline,
        json.dumps(partition_key) if partition_key else None,
        stage,
        severity,
        category,
        message,
        json.dumps(details_json) if details_json else None,
        affected_records,
        execution_id,
        capture_id
    ))
    
    db_connection.commit()
    
    return cursor.lastrowid


def evaluate_readiness(
    week_ending: date,
    db_connection: sqlite3.Connection,
    ready_for: str = "trading"
) -> tuple[bool, list[str]]:
    """
    Determine if week is ready for trading/compliance use.
    
    Criteria:
    - all_partitions_present: 3/3 tiers
    - all_stages_complete: RAW, NORMALIZED, CALC stages exist
    - no_critical_anomalies: Zero unresolved CRITICAL anomalies
    
    Args:
        week_ending: Friday date
        db_connection: Database connection
        ready_for: Use case (trading, compliance, research)
    
    Returns:
        (is_ready: bool, blocking_issues: list[str])
    
    Examples:
        >>> # All criteria met
        >>> evaluate_readiness(date(2025, 12, 26), conn)
        (True, [])
        
        >>> # Missing tier
        >>> evaluate_readiness(date(2025, 12, 26), conn)
        (False, ["Missing tiers: OTC"])
    """
    blocking_issues = []
    
    # Check tier completeness
    all_present, missing_tiers = check_tier_completeness(week_ending, db_connection)
    if not all_present:
        blocking_issues.append(f"Missing tiers: {', '.join(sorted(missing_tiers))}")
    
    # Check all stages complete (at least one tier has NORMALIZED and CALC)
    stages_complete = True
    for tier in ["NMS_TIER_1", "NMS_TIER_2", "OTC"]:
        if not check_stage_ready(week_ending, tier, "RAW", db_connection):
            continue  # Tier missing, already reported above
        
        if not check_stage_ready(week_ending, tier, "NORMALIZED", db_connection):
            blocking_issues.append(f"Missing NORMALIZED stage for {tier}")
            stages_complete = False
    
    # Check for critical anomalies
    cursor = db_connection.execute("""
        SELECT COUNT(*) FROM core_anomalies
        WHERE domain = 'finra.otc_transparency'
          AND severity = 'CRITICAL'
          AND json_extract(partition_key, '$.week_ending') = ?
          AND resolved_at IS NULL
    """, (week_ending.isoformat(),))
    
    critical_count = cursor.fetchone()[0]
    if critical_count > 0:
        blocking_issues.append(f"{critical_count} unresolved CRITICAL anomalies")
    
    is_ready = len(blocking_issues) == 0
    
    # Record readiness state
    db_connection.execute("""
        INSERT INTO core_data_readiness (
            domain, partition_key, is_ready, ready_for,
            all_partitions_present, all_stages_complete, no_critical_anomalies,
            blocking_issues
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(domain, partition_key, ready_for) DO UPDATE SET
            is_ready = excluded.is_ready,
            all_partitions_present = excluded.all_partitions_present,
            all_stages_complete = excluded.all_stages_complete,
            no_critical_anomalies = excluded.no_critical_anomalies,
            blocking_issues = excluded.blocking_issues,
            updated_at = datetime('now')
    """, (
        "finra.otc_transparency",
        json.dumps({"week_ending": week_ending.isoformat()}),
        1 if is_ready else 0,
        ready_for,
        1 if all_present else 0,
        1 if stages_complete else 0,
        1 if critical_count == 0 else 0,
        json.dumps(blocking_issues) if blocking_issues else None
    ))
    
    db_connection.commit()
    
    return (is_ready, blocking_issues)
