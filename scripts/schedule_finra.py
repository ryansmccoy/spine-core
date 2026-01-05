#!/usr/bin/env python3
"""
FINRA OTC Scheduler Script (Thin Wrapper).

Thin entrypoint for cron, Kubernetes, OpenShift, or Docker execution.
Business logic lives in spine.domains.finra.otc_transparency.scheduler.

Usage:
    # Standard weekly run (last 6 weeks)
    python scripts/schedule_finra.py --lookback-weeks 6

    # Backfill specific weeks
    python scripts/schedule_finra.py --weeks 2025-12-15,2025-12-22

    # Dry-run (no database writes)
    python scripts/schedule_finra.py --mode dry-run

    # Force restatement (ignore revision detection)
    python scripts/schedule_finra.py --force --lookback-weeks 4

    # CI/CD mode (stop on first failure)
    python scripts/schedule_finra.py --fail-fast

Exit Codes:
    0 - All partitions processed successfully
    1 - Partial failure (some partitions failed)
    2 - All partitions failed or critical error
"""

import argparse
import logging
import sys
from datetime import date
from pathlib import Path

# Add package paths
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "packages" / "spine-domains" / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "packages" / "spine-core" / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "market-spine-basic" / "src"))

EXIT_SUCCESS = 0
EXIT_PARTIAL = 1
EXIT_CRITICAL = 2


def setup_logging(level: str = "INFO") -> logging.Logger:
    """Configure structured logging."""
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%SZ",
    )
    return logging.getLogger("schedule_finra")


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="FINRA OTC multi-week scheduler with revision detection",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    # Week selection (mutually exclusive)
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
        default="file",
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
    
    # Fail-fast mode
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Stop on first failure (for CI/CD)"
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
    
    # JSON output
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output result as JSON"
    )
    
    return parser.parse_args()


def main() -> int:
    """Main entrypoint."""
    args = parse_args()
    log_level = "DEBUG" if args.verbose else "INFO"
    log = setup_logging(log_level)
    
    try:
        from spine.domains.finra.otc_transparency.scheduler import (
            run_finra_schedule,
            parse_week_list,
        )
    except ImportError as e:
        log.error(f"Failed to import scheduler module: {e}")
        log.error("Ensure packages/spine-domains is installed or in PYTHONPATH")
        return EXIT_CRITICAL
    
    # Parse weeks if provided
    weeks = None
    lookback_weeks = None
    
    if args.weeks:
        try:
            weeks = parse_week_list(args.weeks)
        except ValueError as e:
            log.error(f"Invalid --weeks: {e}")
            return EXIT_CRITICAL
    else:
        lookback_weeks = args.lookback_weeks
    
    # Parse tiers
    tiers = [t.strip() for t in args.tiers.split(",")]
    
    log.info("=" * 60)
    log.info("FINRA OTC Scheduler")
    log.info("=" * 60)
    log.info(f"Mode: {args.mode}")
    log.info(f"Source: {args.source}")
    log.info(f"Tiers: {tiers}")
    if weeks:
        log.info(f"Weeks: {[w.isoformat() for w in weeks]}")
    else:
        log.info(f"Lookback: {lookback_weeks} weeks")
    log.info(f"Force: {args.force}")
    log.info(f"Fail-fast: {args.fail_fast}")
    log.info("=" * 60)
    
    # Run scheduler
    result = run_finra_schedule(
        lookback_weeks=lookback_weeks,
        weeks=weeks,
        tiers=tiers,
        source_type=args.source,
        mode=args.mode,
        force=args.force,
        only_stage=args.only_stage,
        fail_fast=args.fail_fast,
        db_path=args.db,
        verbose=args.verbose,
    )
    
    # Output result
    if args.json:
        import json
        print(json.dumps(result.as_dict(), indent=2))
    else:
        log.info("=" * 60)
        log.info("SUMMARY")
        log.info("=" * 60)
        log.info(f"Success: {result.success_count}")
        log.info(f"Failed: {result.failure_count}")
        log.info(f"Skipped: {len(result.skipped)}")
        log.info(f"Duration: {result.duration_seconds:.1f}s")
        
        if result.failed:
            log.error("Failed partitions:")
            for f in result.failed:
                log.error(f"  - {f['week']}/{f['tier']}/{f['stage']}: {f['error']}")
    
    # Determine exit code
    if result.all_failed:
        return EXIT_CRITICAL
    elif result.has_failures:
        return EXIT_PARTIAL
    else:
        return EXIT_SUCCESS


if __name__ == "__main__":
    sys.exit(main())
