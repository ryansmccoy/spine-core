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
    
    log.info("=" * 60)
    log.info("Price Data Scheduler")
    log.info("=" * 60)
    log.info(f"Mode: {args.mode}")
    log.info(f"Source: {source_type or 'auto'}")
    log.info(f"Symbols: {len(symbols)} ({symbols[:5]}{'...' if len(symbols) > 5 else ''})")
    log.info(f"Output size: {args.outputsize}")
    log.info(f"Rate limit: {args.sleep}s between calls")
    log.info(f"Fail-fast: {args.fail_fast}")
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
        db_path=args.db,
    )
    
    # Output result
    if args.json:
        import json
        print(json.dumps(result.as_dict(), indent=2))
    else:
        log.info("=" * 60)
        log.info("SUMMARY")
        log.info("=" * 60)
        log.info(f"Success: {len(result.success)} symbols")
        log.info(f"Failed: {len(result.failed)} symbols")
        log.info(f"Skipped: {len(result.skipped)} symbols")
        log.info(f"Total rows: {result.total_rows}")
        log.info(f"Duration: {result.duration_seconds:.1f}s")
        
        if result.failed:
            log.error("Failed symbols:")
            for f in result.failed:
                log.error(f"  - {f['symbol']}: {f['error']}")
    
    # Determine exit code
    if result.all_failed:
        return EXIT_CRITICAL
    elif result.has_failures:
        return EXIT_PARTIAL
    else:
        return EXIT_SUCCESS


if __name__ == "__main__":
    sys.exit(main())
