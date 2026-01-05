"""
FINRA OTC Scheduler - Multi-week ingestion orchestration with revision detection.

This module provides reusable scheduler entrypoints for FINRA OTC transparency data.
Designed to be called from thin wrapper scripts or cron/k8s jobs.

Key Features:
    - Lookback windows (process last N weeks for FINRA revisions)
    - Revision detection (via lastUpdateDate or content hash)
    - Non-destructive restatements (capture_id versioning)
    - Phased execution (ingest → normalize → calcs)
    - Partition-level failure isolation
    - Dry-run mode for testing
    - Fail-fast mode for CI/CD

Usage:
    from spine.domains.finra.otc_transparency.scheduler import run_finra_schedule
    
    result = run_finra_schedule(
        lookback_weeks=6,
        mode="run",
        db_path="data/market_spine.db",
    )
    
    if result.has_failures:
        sys.exit(1)
"""

import hashlib
import json
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, UTC
from pathlib import Path
from typing import Any
import sqlite3
import logging

log = logging.getLogger(__name__)


# =============================================================================
# Configuration
# =============================================================================

DOMAIN = "finra.otc_transparency"
DEFAULT_TIERS = ["NMS_TIER_1", "NMS_TIER_2", "OTC"]


@dataclass
class FinraScheduleConfig:
    """Configuration for scheduled FINRA ingestion."""
    weeks: list[date] = field(default_factory=list)
    tiers: list[str] = field(default_factory=lambda: DEFAULT_TIERS.copy())
    source_type: str = "file"  # "api" or "file"
    mode: str = "run"  # "run" or "dry-run"
    force: bool = False  # Ignore revision detection
    only_stage: str = "all"  # "ingest", "normalize", "calc", "all"
    fail_fast: bool = False  # Stop on first failure
    db_path: str = "data/market_spine.db"
    verbose: bool = False
    cli_module: str = "market_spine.cli"  # CLI module for subprocess calls


@dataclass
class FinraScheduleResult:
    """Result of scheduled FINRA ingestion."""
    success: list[dict] = field(default_factory=list)  # [{week, tier, stage}]
    failed: list[dict] = field(default_factory=list)   # [{week, tier, stage, error}]
    skipped: list[dict] = field(default_factory=list)  # [{week, tier, reason}]
    duration_seconds: float = 0.0
    anomalies_recorded: int = 0
    
    @property
    def has_failures(self) -> bool:
        """True if any partitions failed."""
        return len(self.failed) > 0
    
    @property
    def all_failed(self) -> bool:
        """True if all partitions failed."""
        return len(self.success) == 0 and len(self.failed) > 0
    
    @property
    def success_count(self) -> int:
        """Number of successful partitions."""
        return len(self.success)
    
    @property
    def failure_count(self) -> int:
        """Number of failed partitions."""
        return len(self.failed)
    
    def as_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "success": self.success,
            "failed": self.failed,
            "skipped": self.skipped,
            "duration_seconds": self.duration_seconds,
            "anomalies_recorded": self.anomalies_recorded,
            "has_failures": self.has_failures,
            "all_failed": self.all_failed,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
        }


# =============================================================================
# Week Calculation Utilities
# =============================================================================

def calculate_target_weeks(lookback_weeks: int, reference_date: date | None = None) -> list[date]:
    """
    Calculate target week_endings (Fridays) for lookback window.
    
    Args:
        lookback_weeks: Number of weeks to look back (including current)
        reference_date: Starting point (default: today)
    
    Returns:
        List of Friday dates in descending order (newest first)
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


# =============================================================================
# Revision Detection
# =============================================================================

def compute_content_hash(content: bytes) -> str:
    """Compute SHA256 hash of raw content for change detection."""
    return hashlib.sha256(content).hexdigest()[:16]


def generate_capture_id(
    week_ending: date,
    tier: str,
    run_date: date | None = None
) -> str:
    """
    Generate deterministic capture_id for partition.
    
    Format: {domain}:{tier}:{week_ending}:{YYYYMMDD}
    """
    if run_date is None:
        run_date = date.today()
    
    return f"{DOMAIN}:{tier}:{week_ending.isoformat()}:{run_date.strftime('%Y%m%d')}"


def check_revision_needed_via_hash(
    week_ending: date,
    tier: str,
    content: bytes,
    conn: sqlite3.Connection
) -> tuple[bool, str]:
    """
    Compare content hash with latest capture (fallback when lastUpdateDate unavailable).
    
    Returns:
        (needs_revision: bool, reason: str)
    """
    new_hash = compute_content_hash(content)
    
    cursor = conn.execute("""
        SELECT json_extract(metadata_json, '$.content_hash') as stored_hash
        FROM core_manifest
        WHERE domain = ?
          AND stage = 'RAW'
          AND json_extract(partition_key, '$.week_ending') = ?
          AND json_extract(partition_key, '$.tier') = ?
        ORDER BY captured_at DESC
        LIMIT 1
    """, (DOMAIN, week_ending.isoformat(), tier))
    
    latest_capture = cursor.fetchone()
    
    if not latest_capture:
        return (True, "No prior capture (first ingest)")
    
    stored_hash = latest_capture[0]
    
    if not stored_hash:
        return (True, "Prior capture has no content_hash metadata")
    
    if new_hash != stored_hash:
        return (True, f"Content changed (hash {new_hash[:8]} != {stored_hash[:8]})")
    else:
        return (False, f"Content identical (hash {new_hash[:8]})")


def check_stage_ready(
    week_ending: date,
    tier: str,
    stage: str,
    conn: sqlite3.Connection
) -> bool:
    """Check if prerequisite stage completed successfully."""
    cursor = conn.execute("""
        SELECT row_count
        FROM core_manifest
        WHERE domain = ?
          AND stage = ?
          AND json_extract(partition_key, '$.week_ending') = ?
          AND json_extract(partition_key, '$.tier') = ?
        ORDER BY captured_at DESC
        LIMIT 1
    """, (DOMAIN, stage, week_ending.isoformat(), tier))
    
    result = cursor.fetchone()
    return result is not None and result[0] > 0


# =============================================================================
# Anomaly Recording
# =============================================================================

def record_anomaly(
    conn: sqlite3.Connection,
    severity: str,
    category: str,
    message: str,
    week_ending: date | None = None,
    tier: str | None = None,
    stage: str | None = None,
    metadata: dict | None = None,
    capture_id: str | None = None,
) -> None:
    """Record an anomaly for FINRA ingestion."""
    anomaly_id = str(uuid.uuid4())
    detected_at = datetime.now(UTC).isoformat()
    
    partition_key = None
    if week_ending or tier:
        partition_key = json.dumps({
            k: v for k, v in [
                ("week_ending", week_ending.isoformat() if week_ending else None),
                ("tier", tier)
            ] if v
        })
    
    conn.execute("""
        INSERT INTO core_anomalies (
            anomaly_id, domain, stage, partition_key,
            severity, category, message,
            detected_at, metadata, resolved_at, capture_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?)
    """, (
        anomaly_id,
        DOMAIN,
        stage,
        partition_key,
        severity,
        category,
        message,
        detected_at,
        json.dumps(metadata) if metadata else None,
        capture_id,
    ))
    conn.commit()


# =============================================================================
# Source Fetching
# =============================================================================

def fetch_source_data(
    week_ending: date,
    tier: str,
    source_type: str,
    data_dir: str = "data/fixtures/finra_otc"
) -> tuple[bytes | None, str | None]:
    """
    Fetch raw data from source (API or file).
    
    Returns:
        (content: bytes | None, error: str | None)
    """
    if source_type == "file":
        # Use fixture files for testing
        fixture_path = Path(data_dir) / f"{tier.lower()}_week_{week_ending.isoformat()}.psv"
        
        if not fixture_path.exists():
            return (None, f"File not found: {fixture_path}")
        
        try:
            content = fixture_path.read_bytes()
            return (content, None)
        except Exception as e:
            return (None, f"File read error: {e}")
    
    elif source_type == "api":
        # TODO: Implement FINRA API fetching
        return (None, "API source not yet implemented")
    
    else:
        return (None, f"Unknown source type: {source_type}")


# =============================================================================
# Pipeline Execution
# =============================================================================

def run_pipeline_via_cli(
    pipeline_name: str,
    params: dict[str, str],
    cli_module: str = "market_spine.cli",
    timeout: int = 300
) -> tuple[bool, str, str]:
    """
    Run a pipeline via subprocess CLI call.
    
    Returns:
        (success: bool, stdout: str, stderr: str)
    """
    cmd = [
        sys.executable, "-m", cli_module,
        "run", "run", pipeline_name
    ]
    
    for key, value in params.items():
        cmd.append(f"{key}={value}")
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        
        return (result.returncode == 0, result.stdout, result.stderr)
    
    except subprocess.TimeoutExpired:
        return (False, "", f"Timeout after {timeout} seconds")
    except Exception as e:
        return (False, "", str(e))


def process_partition_ingest(
    week_ending: date,
    tier: str,
    config: FinraScheduleConfig,
    conn: sqlite3.Connection,
    run_date: date,
) -> tuple[bool, str]:
    """
    Process ingestion for one week/tier partition.
    
    Returns:
        (success: bool, message: str)
    """
    # Fetch source data
    content, error = fetch_source_data(week_ending, tier, config.source_type)
    
    if error:
        if config.mode != "dry-run":
            record_anomaly(
                conn,
                severity="ERROR",
                category="SOURCE_UNAVAILABLE",
                message=f"Failed to fetch {week_ending}/{tier}: {error}",
                week_ending=week_ending,
                tier=tier,
                stage="RAW",
            )
        return (False, f"Fetch failed: {error}")
    
    # Revision detection (unless --force)
    if not config.force:
        needs_revision, reason = check_revision_needed_via_hash(
            week_ending, tier, content, conn
        )
        
        if not needs_revision:
            if config.mode != "dry-run":
                record_anomaly(
                    conn,
                    severity="INFO",
                    category="REVISION_SKIPPED",
                    message=f"Skipped unchanged partition: {reason}",
                    week_ending=week_ending,
                    tier=tier,
                    stage="RAW",
                )
            return (True, f"Skipped (unchanged): {reason}")
    
    # Generate capture_id
    capture_id = generate_capture_id(week_ending, tier, run_date)
    
    if config.mode == "dry-run":
        log.info(f"[DRY-RUN] Would ingest {week_ending.isoformat()}/{tier} (capture: {capture_id})")
        return (True, f"[DRY-RUN] Would ingest with capture_id: {capture_id}")
    
    # Write temp file and run pipeline
    import tempfile
    with tempfile.NamedTemporaryFile(mode='wb', suffix='.psv', delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name
    
    try:
        success, stdout, stderr = run_pipeline_via_cli(
            f"{DOMAIN}.ingest_week",
            {
                "week_ending": week_ending.isoformat(),
                "tier": tier,
                "file": tmp_path,
                "capture_id": capture_id,
            },
            cli_module=config.cli_module,
        )
        
        if success:
            log.info(f"✓ {week_ending.isoformat()}/{tier}: ingested")
            return (True, "Ingested successfully")
        else:
            error_msg = stderr or "Unknown error"
            record_anomaly(
                conn,
                severity="ERROR",
                category="PIPELINE_ERROR",
                message=f"Ingest failed: {error_msg}",
                week_ending=week_ending,
                tier=tier,
                stage="RAW",
                capture_id=capture_id,
            )
            return (False, f"Ingest failed: {error_msg}")
    
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def process_partition_normalize(
    week_ending: date,
    tier: str,
    config: FinraScheduleConfig,
    conn: sqlite3.Connection,
) -> tuple[bool, str]:
    """Process normalization for one week/tier partition."""
    # Check prerequisite
    if not check_stage_ready(week_ending, tier, "RAW", conn):
        return (False, "RAW stage not ready")
    
    if config.mode == "dry-run":
        log.info(f"[DRY-RUN] Would normalize {week_ending.isoformat()}/{tier}")
        return (True, "[DRY-RUN] Would normalize")
    
    success, stdout, stderr = run_pipeline_via_cli(
        f"{DOMAIN}.normalize_week",
        {
            "week_ending": week_ending.isoformat(),
            "tier": tier,
        },
        cli_module=config.cli_module,
    )
    
    if success:
        log.info(f"✓ {week_ending.isoformat()}/{tier}: normalized")
        return (True, "Normalized successfully")
    else:
        error_msg = stderr or "Unknown error"
        record_anomaly(
            conn,
            severity="ERROR",
            category="PIPELINE_ERROR",
            message=f"Normalize failed: {error_msg}",
            week_ending=week_ending,
            tier=tier,
            stage="NORMALIZED",
        )
        return (False, f"Normalize failed: {error_msg}")


def process_partition_calc(
    week_ending: date,
    tier: str,
    config: FinraScheduleConfig,
    conn: sqlite3.Connection,
) -> tuple[bool, str]:
    """Process calculations for one week/tier partition."""
    # Check prerequisite
    if not check_stage_ready(week_ending, tier, "NORMALIZED", conn):
        return (False, "NORMALIZED stage not ready")
    
    if config.mode == "dry-run":
        log.info(f"[DRY-RUN] Would calculate {week_ending.isoformat()}/{tier}")
        return (True, "[DRY-RUN] Would calculate")
    
    success, stdout, stderr = run_pipeline_via_cli(
        f"{DOMAIN}.compute_analytics",
        {
            "week_ending": week_ending.isoformat(),
            "tier": tier,
        },
        cli_module=config.cli_module,
    )
    
    if success:
        log.info(f"✓ {week_ending.isoformat()}/{tier}: calculated")
        return (True, "Calculated successfully")
    else:
        error_msg = stderr or "Unknown error"
        record_anomaly(
            conn,
            severity="ERROR",
            category="PIPELINE_ERROR",
            message=f"Calc failed: {error_msg}",
            week_ending=week_ending,
            tier=tier,
            stage="CALC",
        )
        return (False, f"Calc failed: {error_msg}")


# =============================================================================
# Main Entrypoint
# =============================================================================

def run_finra_schedule(
    lookback_weeks: int | None = None,
    weeks: list[date] | None = None,
    tiers: list[str] | None = None,
    source_type: str = "file",
    mode: str = "run",
    force: bool = False,
    only_stage: str = "all",
    fail_fast: bool = False,
    db_path: str = "data/market_spine.db",
    run_date: date | None = None,
    cli_module: str = "market_spine.cli",
    verbose: bool = False,
) -> FinraScheduleResult:
    """
    Run scheduled FINRA ingestion for multiple weeks and tiers.
    
    This is the main entrypoint for scheduler scripts.
    
    Args:
        lookback_weeks: Number of weeks to process (mutually exclusive with weeks)
        weeks: Specific weeks to process (mutually exclusive with lookback_weeks)
        tiers: List of tiers to process (default: all)
        source_type: "api" or "file"
        mode: "run" or "dry-run"
        force: Ignore revision detection, always restate
        only_stage: "ingest", "normalize", "calc", or "all"
        fail_fast: Stop on first failure
        db_path: Database path
        run_date: Reference date for capture_id generation
        cli_module: Python module for CLI subprocess calls
        verbose: Enable verbose logging
    
    Returns:
        FinraScheduleResult with success/failed/skipped lists
    """
    start_time = time.time()
    run_date = run_date or date.today()
    
    # Determine weeks to process
    if weeks:
        target_weeks = weeks
    elif lookback_weeks:
        target_weeks = calculate_target_weeks(lookback_weeks, run_date)
    else:
        target_weeks = calculate_target_weeks(6, run_date)  # Default: 6 weeks
    
    config = FinraScheduleConfig(
        weeks=target_weeks,
        tiers=tiers or DEFAULT_TIERS.copy(),
        source_type=source_type,
        mode=mode,
        force=force,
        only_stage=only_stage,
        fail_fast=fail_fast,
        db_path=db_path,
        cli_module=cli_module,
        verbose=verbose,
    )
    
    result = FinraScheduleResult()
    
    # Open database connection
    conn = sqlite3.connect(db_path)
    
    try:
        # Process each week/tier combination
        for week_ending in target_weeks:
            for tier in config.tiers:
                partition_id = f"{week_ending.isoformat()}/{tier}"
                
                # Ingest stage
                if config.only_stage in ("all", "ingest"):
                    log.info(f"[INGEST] {partition_id}...")
                    success, msg = process_partition_ingest(
                        week_ending, tier, config, conn, run_date
                    )
                    
                    if success:
                        if "Skipped" in msg:
                            result.skipped.append({
                                "week": week_ending.isoformat(),
                                "tier": tier,
                                "stage": "ingest",
                                "reason": msg,
                            })
                        else:
                            result.success.append({
                                "week": week_ending.isoformat(),
                                "tier": tier,
                                "stage": "ingest",
                            })
                    else:
                        result.failed.append({
                            "week": week_ending.isoformat(),
                            "tier": tier,
                            "stage": "ingest",
                            "error": msg,
                        })
                        result.anomalies_recorded += 1
                        
                        if config.fail_fast:
                            log.error(f"Fail-fast: stopping due to failure on {partition_id}")
                            break
                        continue  # Skip subsequent stages for this partition
                
                # Normalize stage
                if config.only_stage in ("all", "normalize"):
                    log.info(f"[NORMALIZE] {partition_id}...")
                    success, msg = process_partition_normalize(
                        week_ending, tier, config, conn
                    )
                    
                    if success:
                        result.success.append({
                            "week": week_ending.isoformat(),
                            "tier": tier,
                            "stage": "normalize",
                        })
                    else:
                        result.failed.append({
                            "week": week_ending.isoformat(),
                            "tier": tier,
                            "stage": "normalize",
                            "error": msg,
                        })
                        result.anomalies_recorded += 1
                        
                        if config.fail_fast:
                            log.error(f"Fail-fast: stopping due to failure on {partition_id}")
                            break
                        continue  # Skip subsequent stages for this partition
                
                # Calc stage
                if config.only_stage in ("all", "calc"):
                    log.info(f"[CALC] {partition_id}...")
                    success, msg = process_partition_calc(
                        week_ending, tier, config, conn
                    )
                    
                    if success:
                        result.success.append({
                            "week": week_ending.isoformat(),
                            "tier": tier,
                            "stage": "calc",
                        })
                    else:
                        result.failed.append({
                            "week": week_ending.isoformat(),
                            "tier": tier,
                            "stage": "calc",
                            "error": msg,
                        })
                        result.anomalies_recorded += 1
                        
                        if config.fail_fast:
                            log.error(f"Fail-fast: stopping due to failure on {partition_id}")
                            break
            
            # Check fail-fast after inner loop
            if config.fail_fast and result.has_failures:
                break
    
    finally:
        conn.close()
    
    result.duration_seconds = time.time() - start_time
    
    # Log summary
    log.info(
        f"Schedule complete: {result.success_count} success, "
        f"{result.failure_count} failed, {len(result.skipped)} skipped"
    )
    log.info(f"Duration: {result.duration_seconds:.1f}s")
    
    return result
