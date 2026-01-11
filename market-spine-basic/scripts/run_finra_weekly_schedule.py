#!/usr/bin/env python3
"""
FINRA OTC Multi-Week Scheduler with Revision Detection

This script orchestrates scheduled ingestion, normalization, and analytics
for FINRA OTC transparency data across multiple weeks with intelligent
revision detection to skip unchanged data.

Key Features:
- Lookback windows (process last N weeks for FINRA revisions)
- Revision detection (via lastUpdateDate or content hash)
- Non-destructive restatements (capture_id versioning)
- Phased execution (ingest → normalize → calcs)
- Partition-level failure isolation
- Dry-run mode for testing

Usage:
    # Standard weekly run (last 6 weeks)
    python scripts/run_finra_weekly_schedule.py --lookback-weeks 6

    # Backfill specific weeks
    python scripts/run_finra_weekly_schedule.py --weeks 2025-12-15,2025-12-22

    # Dry-run (no database writes)
    python scripts/run_finra_weekly_schedule.py --mode dry-run

    # Force restatement (ignore revision detection)
    python scripts/run_finra_weekly_schedule.py --force --lookback-weeks 4

Exit Codes:
    0 - All weeks processed successfully
    1 - Partial failure (some partitions failed)
    2 - Critical failure (DB down, config invalid)
"""

import argparse
import json
import sqlite3
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

# Add market-spine-basic to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from market_spine.app.scheduler import (
    calculate_target_weeks,
    parse_week_list,
    generate_capture_id,
    check_revision_needed_via_hash,
    check_stage_ready,
    check_tier_completeness,
    record_anomaly,
    evaluate_readiness,
)


EXIT_SUCCESS = 0
EXIT_PARTIAL = 1
EXIT_CRITICAL = 2


def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="FINRA OTC multi-week scheduler with revision detection",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    # Week selection
    week_group = parser.add_mutually_exclusive_group()
    week_group.add_argument(
        "--lookback-weeks",
        type=int,
        default=6,
        help="Number of weeks to process (default: 6)"
    )
    week_group.add_argument(
        "--weeks",
        type=str,
        help="Comma-separated week_ending dates (e.g., 2025-12-15,2025-12-22)"
    )
    
    # Tier selection
    parser.add_argument(
        "--tiers",
        type=str,
        default="NMS_TIER_1,NMS_TIER_2,OTC",
        help="Comma-separated tier names (default: all tiers)"
    )
    
    # Source configuration
    parser.add_argument(
        "--source",
        type=str,
        choices=["api", "file"],
        default="file",  # Default to file for testing
        help="Data source type (default: file)"
    )
    
    # Execution mode
    parser.add_argument(
        "--mode",
        type=str,
        choices=["run", "dry-run"],
        default="run",
        help="Execution mode (default: run)"
    )
    
    # Force restatement
    parser.add_argument(
        "--force",
        action="store_true",
        help="Ignore revision detection, always restate"
    )
    
    # Stage selection
    parser.add_argument(
        "--only-stage",
        type=str,
        choices=["ingest", "normalize", "calc", "all"],
        default="all",
        help="Run only specific stage (default: all)"
    )
    
    # Database path
    parser.add_argument(
        "--db",
        type=str,
        default="data/market_spine.db",
        help="Database path (default: data/market_spine.db)"
    )
    
    # Verbosity
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose output"
    )
    
    return parser.parse_args()


def log(message: str, level: str = "INFO", verbose: bool = False, force_print: bool = False):
    """
    Print log message with level prefix.
    
    Args:
        message: Log message
        level: INFO, WARN, ERROR, CRITICAL
        verbose: Verbose mode enabled
        force_print: Always print (ignores verbose flag)
    """
    if force_print or verbose or level in ["WARN", "ERROR", "CRITICAL"]:
        prefix = f"[{level}]"
        print(f"{prefix:10} {message}")


def fetch_source_data(week_ending: date, tier: str, source_type: str, verbose: bool = False) -> tuple[bytes | None, str | None]:
    """
    Fetch raw data from source (API or file).
    
    Args:
        week_ending: Friday date
        tier: NMS_TIER_1, NMS_TIER_2, or OTC
        source_type: "api" or "file"
        verbose: Enable verbose logging
    
    Returns:
        (content: bytes | None, error: str | None)
    """
    if source_type == "file":
        # Use fixture files for testing
        fixture_path = Path(f"data/fixtures/finra_otc/{tier.lower()}_week_{week_ending.isoformat()}.psv")
        
        if not fixture_path.exists():
            log(f"Fixture file not found: {fixture_path}", "WARN", verbose)
            return (None, f"File not found: {fixture_path}")
        
        try:
            content = fixture_path.read_bytes()
            log(f"Read {len(content)} bytes from {fixture_path}", "DEBUG", verbose)
            return (content, None)
        except Exception as e:
            return (None, f"File read error: {e}")
    
    elif source_type == "api":
        # TODO: Implement FINRA API fetching
        # This would use requests to fetch from finra.org
        log("API source not yet implemented, use --source file", "ERROR", verbose, force_print=True)
        return (None, "API source not implemented")
    
    else:
        return (None, f"Unknown source type: {source_type}")


def process_week_tier_ingest(
    week_ending: date,
    tier: str,
    source_type: str,
    force: bool,
    dry_run: bool,
    run_date: date,
    db_connection,
    verbose: bool = False
) -> tuple[bool, str]:
    """
    Process ingestion for one week/tier partition.
    
    Args:
        week_ending: Friday date
        tier: NMS_TIER_1, NMS_TIER_2, or OTC
        source_type: "api" or "file"
        force: Ignore revision detection
        dry_run: Don't write to database
        run_date: Date of scheduler run (for capture_id)
        db_connection: Database connection
        verbose: Enable verbose logging
    
    Returns:
        (success: bool, message: str)
    """
    log(f"Processing {week_ending.isoformat()} / {tier}", "DEBUG", verbose)
    
    # Fetch source data
    content, error = fetch_source_data(week_ending, tier, source_type, verbose)
    
    if error:
        # Record anomaly
        if not dry_run:
            record_anomaly(
                db_connection,
                domain="finra.otc_transparency",
                severity="ERROR",
                category="SOURCE_UNAVAILABLE",
                message=f"Failed to fetch {week_ending}/{tier}: {error}",
                partition_key={"week_ending": week_ending.isoformat(), "tier": tier},
                stage="RAW"
            )
        return (False, f"Fetch failed: {error}")
    
    # Revision detection (unless --force)
    if not force:
        needs_revision, reason = check_revision_needed_via_hash(
            week_ending, tier, content, db_connection
        )
        
        if not needs_revision:
            log(f"{week_ending.isoformat()} / {tier}: {reason}, skipping", "INFO", verbose)
            
            # Record INFO anomaly for audit trail
            if not dry_run:
                record_anomaly(
                    db_connection,
                    domain="finra.otc_transparency",
                    severity="INFO",
                    category="REVISION_SKIPPED",
                    message=f"Skipped unchanged partition: {reason}",
                    partition_key={"week_ending": week_ending.isoformat(), "tier": tier},
                    stage="RAW"
                )
            
            return (True, f"Skipped (unchanged): {reason}")
        
        log(f"{week_ending.isoformat()} / {tier}: {reason}", "DEBUG", verbose)
    
    # Generate capture_id
    capture_id = generate_capture_id(
        "finra.otc_transparency",
        week_ending,
        tier,
        run_date
    )
    
    if dry_run:
        log(f"[DRY-RUN] Would ingest {week_ending.isoformat()} / {tier} (capture: {capture_id})", "INFO", verbose, force_print=True)
        return (True, f"[DRY-RUN] Would ingest with capture_id: {capture_id}")
    
    # Run ingest pipeline using spine CLI
    try:
        # Create temp file for pipeline (expects file path)
        import tempfile
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.psv', delete=False) as tmp:
            tmp.write(content)
            tmp_path = tmp.name
        
        try:
            # Use subprocess to call spine CLI
            cmd = [
                sys.executable, "-m", "market_spine.cli",
                "run", "run",
                "finra.otc_transparency.ingest_week",
                f"week_ending={week_ending.isoformat()}",
                f"tier={tier}",
                f"file={tmp_path}",
                f"capture_id={capture_id}"
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )
            
            if result.returncode == 0:
                # Parse output for row count (simple heuristic)
                row_count = 0
                for line in result.stdout.split('\n'):
                    if 'rows' in line.lower():
                        import re
                        match = re.search(r'(\d+)\s+rows', line, re.IGNORECASE)
                        if match:
                            row_count = int(match.group(1))
                            break
                
                log(f"{week_ending.isoformat()} / {tier}: ✓ Ingested {row_count} rows", "INFO", verbose, force_print=True)
                return (True, f"Ingested {row_count} rows")
            else:
                error_msg = result.stderr or "Unknown error"
                log(f"{week_ending.isoformat()} / {tier}: ✗ Ingest failed: {error_msg}", "ERROR", verbose, force_print=True)
                
                # Record anomaly
                record_anomaly(
                    db_connection,
                    domain="finra.otc_transparency",
                    severity="ERROR",
                    category="PIPELINE_ERROR",
                    message=f"Ingest failed: {error_msg}",
                    partition_key={"week_ending": week_ending.isoformat(), "tier": tier},
                    stage="RAW",
                    capture_id=capture_id
                )
                
                return (False, f"Ingest failed: {error_msg}")
        
        finally:
            # Clean up temp file
            Path(tmp_path).unlink(missing_ok=True)
    
    except subprocess.TimeoutExpired:
        log(f"{week_ending.isoformat()} / {tier}: ✗ Timeout after 5 minutes", "ERROR", verbose, force_print=True)
        return (False, "Timeout after 5 minutes")
    
    except Exception as e:
        log(f"{week_ending.isoformat()} / {tier}: ✗ Exception: {e}", "ERROR", verbose, force_print=True)
        
        # Record anomaly
        if not dry_run:
            record_anomaly(
                db_connection,
                domain="finra.otc_transparency",
                severity="ERROR",
                category="PIPELINE_ERROR",
                message=f"Ingest exception: {e}",
                partition_key={"week_ending": week_ending.isoformat(), "tier": tier},
                stage="RAW",
                capture_id=capture_id
            )
        
        return (False, f"Exception: {e}")


def process_week_tier_normalize(
    week_ending: date,
    tier: str,
    dry_run: bool,
    db_connection,
    verbose: bool = False
) -> tuple[bool, str]:
    """
    Process normalization for one week/tier partition.
    
    Args:
        week_ending: Friday date
        tier: NMS_TIER_1, NMS_TIER_2, or OTC
        dry_run: Don't write to database
        db_connection: Database connection
        verbose: Enable verbose logging
    
    Returns:
        (success: bool, message: str)
    """
    # Check if RAW stage exists
    if not check_stage_ready(week_ending, tier, "RAW", db_connection):
        log(f"{week_ending.isoformat()} / {tier}: RAW stage missing, skipping normalize", "WARN", verbose)
        return (True, "Skipped (no RAW data)")
    
    if dry_run:
        log(f"[DRY-RUN] Would normalize {week_ending.isoformat()} / {tier}", "INFO", verbose, force_print=True)
        return (True, "[DRY-RUN] Would normalize")
    
    try:
        cmd = [
            sys.executable, "-m", "market_spine.cli",
            "run", "run",
            "finra.otc_transparency.normalize_week",
            f"week_ending={week_ending.isoformat()}",
            f"tier={tier}"
        ]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300
        )
        
        if result.returncode == 0:
            row_count = 0
            for line in result.stdout.split('\n'):
                if 'rows' in line.lower():
                    import re
                    match = re.search(r'(\d+)\s+rows', line, re.IGNORECASE)
                    if match:
                        row_count = int(match.group(1))
                        break
            
            log(f"{week_ending.isoformat()} / {tier}: ✓ Normalized {row_count} rows", "INFO", verbose, force_print=True)
            return (True, f"Normalized {row_count} rows")
        else:
            error_msg = result.stderr or "Unknown error"
            log(f"{week_ending.isoformat()} / {tier}: ✗ Normalize failed: {error_msg}", "ERROR", verbose, force_print=True)
            return (False, f"Normalize failed: {error_msg}")
    
    except subprocess.TimeoutExpired:
        log(f"{week_ending.isoformat()} / {tier}: ✗ Timeout", "ERROR", verbose, force_print=True)
        return (False, "Timeout")
    
    except Exception as e:
        log(f"{week_ending.isoformat()} / {tier}: ✗ Exception: {e}", "ERROR", verbose, force_print=True)
        return (False, f"Exception: {e}")


def process_week_calcs(
    week_ending: date,
    dry_run: bool,
    db_connection,
    verbose: bool = False
) -> tuple[int, int]:
    """
    Process analytics calculations for a week (cross-tier).
    
    Args:
        week_ending: Friday date
        dry_run: Don't write to database
        db_connection: Database connection
        verbose: Enable verbose logging
    
    Returns:
        (success_count: int, failure_count: int)
    """
    # Check if all tiers normalized
    all_present, missing = check_tier_completeness(week_ending, db_connection)
    
    if not all_present:
        log(f"{week_ending.isoformat()}: Missing tiers {missing}, skipping calcs", "WARN", verbose)
        return (0, 0)
    
    calc_pipelines = [
        "finra.otc_transparency.compute_venue_volume",
        "finra.otc_transparency.compute_venue_share",
        "finra.otc_transparency.compute_hhi",
    ]
    
    success_count = 0
    failure_count = 0
    
    for pipeline_name in calc_pipelines:
        if dry_run:
            log(f"[DRY-RUN] Would run {pipeline_name} for {week_ending.isoformat()}", "INFO", verbose, force_print=True)
            success_count += 1
            continue
        
        try:
            cmd = [
                sys.executable, "-m", "market_spine.cli",
                "run", "run",
                pipeline_name,
                f"week_ending={week_ending.isoformat()}"
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300
            )
            
            if result.returncode == 0:
                log(f"{week_ending.isoformat()}: ✓ {pipeline_name.split('.')[-1]}", "INFO", verbose, force_print=True)
                success_count += 1
            else:
                error_msg = result.stderr or "Unknown error"
                log(f"{week_ending.isoformat()}: ✗ {pipeline_name.split('.')[-1]} failed: {error_msg}", "ERROR", verbose, force_print=True)
                failure_count += 1
        
        except subprocess.TimeoutExpired:
            log(f"{week_ending.isoformat()}: ✗ {pipeline_name.split('.')[-1]} timeout", "ERROR", verbose, force_print=True)
            failure_count += 1
        
        except Exception as e:
            log(f"{week_ending.isoformat()}: ✗ {pipeline_name.split('.')[-1]} exception: {e}", "ERROR", verbose, force_print=True)
            failure_count += 1
    
    return (success_count, failure_count)


def main():
    """Main scheduler execution."""
    args = parse_args()
    
    # Determine target weeks
    if args.weeks:
        try:
            target_weeks = parse_week_list(args.weeks)
            log(f"Manual week selection: {[w.isoformat() for w in target_weeks]}", "INFO", args.verbose, force_print=True)
        except ValueError as e:
            log(f"Invalid --weeks argument: {e}", "CRITICAL", args.verbose, force_print=True)
            return EXIT_CRITICAL
    else:
        target_weeks = calculate_target_weeks(args.lookback_weeks)
        log(f"Lookback {args.lookback_weeks} weeks: {[w.isoformat() for w in target_weeks]}", "INFO", args.verbose, force_print=True)
    
    # Parse tiers
    tiers = [t.strip() for t in args.tiers.split(",")]
    log(f"Target tiers: {tiers}", "INFO", args.verbose, force_print=True)
    
    # Connect to database
    try:
        db_path = Path(args.db)
        if not db_path.exists() and not args.mode == "dry-run":
            log(f"Database not found: {db_path}", "CRITICAL", args.verbose, force_print=True)
            return EXIT_CRITICAL
        
        db_connection = sqlite3.connect(str(db_path))
        log(f"Connected to database: {db_path}", "DEBUG", args.verbose)
    except Exception as e:
        log(f"Database connection failed: {e}", "CRITICAL", args.verbose, force_print=True)
        return EXIT_CRITICAL
    
    run_date = date.today()
    dry_run = args.mode == "dry-run"
    
    # Statistics
    stats = {
        "total_partitions": len(target_weeks) * len(tiers),
        "ingested": 0,
        "skipped": 0,
        "ingest_failed": 0,
        "normalized": 0,
        "normalize_failed": 0,
        "calcs_success": 0,
        "calcs_failed": 0,
        "weeks_ready": 0,
        "weeks_not_ready": 0
    }
    
    # Phase 1: Ingestion
    if args.only_stage in ["ingest", "all"]:
        log("=== Phase 1: Ingestion ===", "INFO", args.verbose, force_print=True)
        
        for week_ending in target_weeks:
            for tier in tiers:
                success, message = process_week_tier_ingest(
                    week_ending, tier, args.source, args.force, dry_run,
                    run_date, db_connection, args.verbose
                )
                
                if success:
                    if "Skipped" in message:
                        stats["skipped"] += 1
                    else:
                        stats["ingested"] += 1
                else:
                    stats["ingest_failed"] += 1
    
    # Phase 2: Normalization
    if args.only_stage in ["normalize", "all"]:
        log("=== Phase 2: Normalization ===", "INFO", args.verbose, force_print=True)
        
        for week_ending in target_weeks:
            for tier in tiers:
                success, message = process_week_tier_normalize(
                    week_ending, tier, dry_run, db_connection, args.verbose
                )
                
                if success and "Skipped" not in message and "DRY-RUN" not in message:
                    stats["normalized"] += 1
                elif not success:
                    stats["normalize_failed"] += 1
    
    # Phase 3: Analytics
    if args.only_stage in ["calc", "all"]:
        log("=== Phase 3: Analytics ===", "INFO", args.verbose, force_print=True)
        
        for week_ending in target_weeks:
            success_count, failure_count = process_week_calcs(
                week_ending, dry_run, db_connection, args.verbose
            )
            stats["calcs_success"] += success_count
            stats["calcs_failed"] += failure_count
    
    # Phase 4: Readiness Evaluation
    if not dry_run and args.only_stage == "all":
        log("=== Phase 4: Readiness Evaluation ===", "INFO", args.verbose, force_print=True)
        
        for week_ending in target_weeks:
            is_ready, blocking_issues = evaluate_readiness(week_ending, db_connection, "trading")
            
            if is_ready:
                log(f"{week_ending.isoformat()}: ✓ Ready for trading", "INFO", args.verbose, force_print=True)
                stats["weeks_ready"] += 1
            else:
                log(f"{week_ending.isoformat()}: ✗ NOT READY - {', '.join(blocking_issues)}", "WARN", args.verbose, force_print=True)
                stats["weeks_not_ready"] += 1
    
    # Print summary
    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)
    print(f"Weeks processed:      {len(target_weeks)}")
    print(f"Total partitions:     {stats['total_partitions']} ({len(target_weeks)} weeks × {len(tiers)} tiers)")
    print(f"")
    print(f"Ingestion:")
    print(f"  Ingested:           {stats['ingested']}")
    print(f"  Skipped (unchanged): {stats['skipped']}")
    print(f"  Failed:             {stats['ingest_failed']}")
    print(f"")
    print(f"Normalization:")
    print(f"  Normalized:         {stats['normalized']}")
    print(f"  Failed:             {stats['normalize_failed']}")
    print(f"")
    print(f"Analytics:")
    print(f"  Calculations OK:    {stats['calcs_success']}")
    print(f"  Calculations failed: {stats['calcs_failed']}")
    print(f"")
    if not dry_run and args.only_stage == "all":
        print(f"Readiness:")
        print(f"  Weeks ready:        {stats['weeks_ready']}")
        print(f"  Weeks not ready:    {stats['weeks_not_ready']}")
    print("="*70)
    
    # Determine exit code
    if stats["ingest_failed"] > 0 or stats["normalize_failed"] > 0 or stats["calcs_failed"] > 0:
        log("Exiting with partial failure (exit code 1)", "WARN", args.verbose, force_print=True)
        return EXIT_PARTIAL
    else:
        log("Exiting successfully (exit code 0)", "INFO", args.verbose, force_print=True)
        return EXIT_SUCCESS


if __name__ == "__main__":
    sys.exit(main())
