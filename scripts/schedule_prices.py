#!/usr/bin/env python3
"""
Price Data Scheduler Script (Thin Wrapper).

Thin entrypoint for cron, Kubernetes, OpenShift, or Docker execution.
Business logic lives in spine.domains.market_data.scheduler.

Usage:
    # Standard run with symbols
    python scripts/schedule_prices.py --symbols AAPL,MSFT,GOOGL

    # Load symbols from file
    python scripts/schedule_prices.py --symbols-file symbols.txt

    # Dry-run (no database writes)
    python scripts/schedule_prices.py --symbols AAPL --mode dry-run

    # CI/CD mode (stop on first failure)
    python scripts/schedule_prices.py --symbols AAPL,MSFT --fail-fast

Exit Codes:
    0 - All symbols processed successfully
    1 - Partial failure (some symbols failed)
    2 - All symbols failed or critical error
    3 - Configuration error
"""

import argparse
import logging
import os
import sys
from pathlib import Path

# Add package paths
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "packages" / "spine-domains" / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "packages" / "spine-core" / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "market-spine-basic" / "src"))

EXIT_SUCCESS = 0
EXIT_PARTIAL = 1
EXIT_CRITICAL = 2
EXIT_CONFIG_ERROR = 3


def setup_logging(level: str = "INFO") -> logging.Logger:
    """Configure structured logging."""
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%SZ",
    )
    return logging.getLogger("schedule_prices")


def load_symbols_from_file(filepath: str) -> list[str]:
    """Load symbols from a file (one per line, # for comments)."""
    symbols = []
    with open(filepath, "r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                symbols.append(line.upper())
    return symbols


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Price data scheduler with rate limiting",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    # Symbol selection (mutually exclusive)
    symbol_group = parser.add_mutually_exclusive_group(required=True)
    symbol_group.add_argument(
        "--symbols",
        type=str,
        help="Comma-separated stock symbols (e.g., AAPL,MSFT,GOOGL)"
    )
    symbol_group.add_argument(
        "--symbols-file",
        type=str,
        help="Path to file with symbols (one per line)"
    )
    
    # Source configuration
    parser.add_argument(
        "--source",
        type=str,
        choices=["alpha_vantage", "polygon", "mock"],
        help="Data source (default: from PRICE_SOURCE env)"
    )
    
    # Output size
    parser.add_argument(
        "--outputsize",
        type=str,
        choices=["compact", "full"],
        default="compact",
        help="Data range: compact (~100 days) or full (20 years)"
    )
    
    # Rate limiting
    parser.add_argument(
        "--sleep",
        type=float,
        default=12.0,
        help="Seconds between API calls (default: 12 for 5 req/min)"
    )
    
    # Batch limit
    parser.add_argument(
        "--max-symbols",
        type=int,
        default=25,
        help="Maximum symbols per batch (default: 25)"
    )
    
    # Execution mode
    parser.add_argument(
        "--mode",
        type=str,
        choices=["run", "dry-run"],
        default="run",
        help="Execution mode (default: run)"
    )
    
    # Fail-fast mode
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Stop on first failure (for CI/CD)"
    )
    
    # Database path (with env fallback)
    parser.add_argument(
        "--db",
        type=str,
        default=None,
        help="Database path (default: data/market_spine.db or DATABASE_URL env)"
    )
    
    # Log level
    parser.add_argument(
        "--log-level",
        type=str,
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Log level (default: INFO)"
    )
    
    # Verbosity (legacy, sets log-level to DEBUG)
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose output (sets --log-level DEBUG)"
    )
    
    # JSON output
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output result as JSON (for automation)"
    )
    
    return parser.parse_args()


def main() -> int:
    """Main entrypoint."""
    args = parse_args()
    log_level = "DEBUG" if args.verbose else args.log_level
    log = setup_logging(log_level)
    
    try:
        from spine.domains.market_data.scheduler import run_price_schedule
    except ImportError as e:
        log.error(f"Failed to import scheduler module: {e}")
        log.error("Ensure packages/spine-domains is installed or in PYTHONPATH")
        return EXIT_CRITICAL
    
    # Parse symbols
    if args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(",")]
    else:
        try:
            symbols = load_symbols_from_file(args.symbols_file)
        except FileNotFoundError:
            log.error(f"Symbols file not found: {args.symbols_file}")
            return EXIT_CONFIG_ERROR
        except Exception as e:
            log.error(f"Failed to read symbols file: {e}")
            return EXIT_CONFIG_ERROR
    
    if not symbols:
        log.error("No symbols provided")
        return EXIT_CONFIG_ERROR
    
    # Determine source
    source_type = args.source or os.environ.get("PRICE_SOURCE")
    
    # Resolve database path (CLI > env > default)
    db_path = args.db or os.environ.get("DATABASE_URL", "data/market_spine.db")
    
    log.info("=" * 60)
    log.info("Price Data Scheduler")
    log.info("=" * 60)
    log.info(f"Mode: {args.mode}")
    log.info(f"Source: {source_type or 'auto'}")
    log.info(f"Symbols: {len(symbols)} ({symbols[:5]}{'...' if len(symbols) > 5 else ''})")
    log.info(f"Output size: {args.outputsize}")
    log.info(f"Rate limit: {args.sleep}s between calls")
    log.info(f"Fail-fast: {args.fail_fast}")
    log.info(f"Database: {db_path}")
    log.info("=" * 60)
    
    # Run scheduler
    result = run_price_schedule(
        symbols=symbols,
        mode=args.mode,
        source_type=source_type,
        outputsize=args.outputsize,
        sleep_between=args.sleep,
        max_symbols=args.max_symbols,
        fail_fast=args.fail_fast,
        db_path=db_path,
    )
    
    # Output result
    if args.json:
        # Use SchedulerResult.to_json() if available, fallback to as_dict()
        if hasattr(result, 'to_json'):
            print(result.to_json(indent=2))
        else:
            import json
            print(json.dumps(result.as_dict(), indent=2, default=str))
    else:
        log.info("=" * 60)
        log.info("SUMMARY")
        log.info("=" * 60)
        
        # Handle both SchedulerResult and legacy result
        if hasattr(result, 'stats'):
            log.info(f"Attempted: {result.stats.attempted}")
            log.info(f"Succeeded: {result.stats.succeeded}")
            log.info(f"Failed: {result.stats.failed}")
            log.info(f"Skipped: {result.stats.skipped}")
        else:
            log.info(f"Success: {len(result.success)} symbols")
            log.info(f"Failed: {len(result.failed)} symbols")
            log.info(f"Skipped: {len(result.skipped)} symbols")
            log.info(f"Total rows: {result.total_rows}")
        
        if hasattr(result, 'warnings') and result.warnings:
            for warn in result.warnings:
                log.warning(warn)
        
        # Show failures
        if hasattr(result, 'runs'):
            failed_runs = [r for r in result.runs if r.status.value == "failed"]
            if failed_runs:
                log.error("Failed symbols:")
                for r in failed_runs:
                    log.error(f"  - {r.partition_key}: {r.error}")
        elif hasattr(result, 'failed') and result.failed:
            log.error("Failed symbols:")
            for f in result.failed:
                log.error(f"  - {f['symbol']}: {f['error']}")
    
    # Use SchedulerResult.exit_code if available
    if hasattr(result, 'exit_code'):
        return result.exit_code
    
    # Legacy exit code determination
    if hasattr(result, 'all_failed') and result.all_failed:
        return EXIT_CRITICAL
    elif hasattr(result, 'has_failures') and result.has_failures:
        return EXIT_PARTIAL
    else:
        return EXIT_SUCCESS


if __name__ == "__main__":
    sys.exit(main())
