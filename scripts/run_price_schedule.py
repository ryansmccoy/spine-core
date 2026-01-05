#!/usr/bin/env python3
"""
Price Data Scheduler Script.

Scheduler-friendly script for batch price ingestion.
Designed to run on cron, OpenShift, Kubernetes, or Docker.

Usage:
    python scripts/run_price_schedule.py --symbols AAPL,MSFT,GOOGL --mode run
    python scripts/run_price_schedule.py --symbols-file symbols.txt --lookback-days 30
    python scripts/run_price_schedule.py --symbols AAPL --mode dry-run

Features:
    - Idempotent: re-fetching produces new capture_id if content differs
    - Rate-limit aware: configurable delays between symbols
    - Append-only: never deletes old data (as-of semantics preserved)
    - Clear logging: success/failure/skipped counts for monitoring

Exit Codes:
    0 - All symbols succeeded
    1 - Some symbols failed (partial success)
    2 - All symbols failed
    3 - Configuration error
"""

import argparse
import json
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, UTC
from pathlib import Path
from typing import Any

# Add project paths
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "packages" / "spine-domains" / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "packages" / "spine-core" / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "market-spine-basic" / "src"))


# =============================================================================
# Configuration
# =============================================================================

@dataclass
class ScheduleConfig:
    """Configuration for scheduled price ingestion."""
    symbols: list[str] = field(default_factory=list)
    source_type: str | None = None
    outputsize: str = "compact"
    lookback_days: int = 100  # compact = ~100 days
    sleep_between: float = 12.0  # seconds between API calls (5 req/min = 12s)
    max_symbols_per_batch: int = 25  # Alpha Vantage daily limit
    mode: str = "run"  # "run" or "dry-run"
    db_path: str | None = None
    log_level: str = "INFO"


@dataclass
class ScheduleResult:
    """Result of scheduled ingestion run."""
    success: list[str] = field(default_factory=list)
    failed: list[dict] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    total_rows: int = 0
    new_captures: int = 0
    duration_seconds: float = 0.0
    anomalies_recorded: int = 0


# =============================================================================
# Logging Setup
# =============================================================================

def setup_logging(level: str = "INFO") -> logging.Logger:
    """Configure structured logging."""
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%SZ",
    )
    return logging.getLogger("price_schedule")


# =============================================================================
# Main Logic
# =============================================================================

def load_symbols_from_file(filepath: str) -> list[str]:
    """Load symbols from a file (one per line, # for comments)."""
    symbols = []
    with open(filepath, "r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                symbols.append(line.upper())
    return symbols


def run_schedule(config: ScheduleConfig, logger: logging.Logger) -> ScheduleResult:
    """
    Run the scheduled price ingestion.
    
    Idempotent and revision-friendly:
    - Re-fetching produces new capture_id when content differs
    - Old data is never deleted (append-only)
    """
    from spine.domains.market_data.sources import create_source, FetchResult
    from spine.domains.market_data.pipelines import ensure_schema, calculate_changes
    from spine.framework.db import get_connection
    
    result = ScheduleResult()
    start_time = time.time()
    
    # Validate symbols
    symbols = config.symbols[:config.max_symbols_per_batch]
    if len(config.symbols) > config.max_symbols_per_batch:
        logger.warning(
            f"Truncating symbol list from {len(config.symbols)} to {config.max_symbols_per_batch} "
            f"(max_symbols_per_batch limit)"
        )
    
    if not symbols:
        logger.error("No symbols to process")
        return result
    
    logger.info(f"Starting price schedule: {len(symbols)} symbols, mode={config.mode}")
    
    # Initialize
    if config.mode == "dry-run":
        logger.info("DRY-RUN mode: no data will be written")
    
    try:
        conn = get_connection()
        ensure_schema(conn)
        source = create_source(source_type=config.source_type)
        source_name = type(source).__name__.replace("Source", "").lower()
    except Exception as e:
        logger.error(f"Initialization failed: {e}")
        return result
    
    logger.info(f"Source: {source_name}, outputsize: {config.outputsize}")
    
    # Process each symbol
    for i, symbol in enumerate(symbols):
        if i > 0:
            logger.debug(f"Sleeping {config.sleep_between}s between requests...")
            time.sleep(config.sleep_between)
        
        logger.info(f"[{i+1}/{len(symbols)}] Processing {symbol}...")
        
        try:
            fetch_result: FetchResult = source.fetch({
                "symbol": symbol,
                "outputsize": config.outputsize,
            })
        except Exception as e:
            logger.error(f"  Fetch error for {symbol}: {e}")
            result.failed.append({"symbol": symbol, "error": str(e)})
            result.anomalies_recorded += 1
            continue
        
        # Handle anomalies
        if fetch_result.anomalies:
            messages = [f"{a['category']}: {a['message']}" for a in fetch_result.anomalies]
            logger.warning(f"  Anomalies for {symbol}: {messages}")
            result.failed.append({"symbol": symbol, "error": "; ".join(messages)})
            result.anomalies_recorded += len(fetch_result.anomalies)
            continue
        
        if not fetch_result.data:
            logger.info(f"  No data returned for {symbol}, skipping")
            result.skipped.append(symbol)
            continue
        
        # Log content hash for dedup visibility
        content_hash = fetch_result.metadata.content_hash if fetch_result.metadata else "unknown"
        logger.info(f"  Fetched {len(fetch_result.data)} rows, content_hash={content_hash[:12]}...")
        
        if config.mode == "dry-run":
            result.success.append(symbol)
            result.total_rows += len(fetch_result.data)
            continue
        
        # Calculate changes and insert
        data = calculate_changes(fetch_result.data)
        now = datetime.now(UTC)
        content_hash_suffix = ""
        if fetch_result.metadata and fetch_result.metadata.content_hash:
            content_hash_suffix = f".{fetch_result.metadata.content_hash[:8]}"
        capture_id = f"market_data.prices.{symbol}.{now.strftime('%Y%m%dT%H%M%SZ')}{content_hash_suffix}"
        captured_at = now.isoformat().replace("+00:00", "Z")
        
        try:
            cursor = conn.cursor()
            for row in data:
                cursor.execute("""
                    INSERT INTO market_data_prices_daily 
                    (symbol, date, open, high, low, close, volume, change, change_percent,
                     source, capture_id, captured_at, is_valid)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                    ON CONFLICT (symbol, date, capture_id) DO UPDATE SET
                        open = excluded.open, high = excluded.high, low = excluded.low,
                        close = excluded.close, volume = excluded.volume,
                        change = excluded.change, change_percent = excluded.change_percent
                """, (
                    row["symbol"], row["date"], row["open"], row["high"], row["low"],
                    row["close"], row["volume"], row.get("change"), row.get("change_percent"),
                    source_name, capture_id, captured_at,
                ))
            conn.commit()
            
            result.success.append(symbol)
            result.total_rows += len(data)
            result.new_captures += 1
            logger.info(f"  Inserted {len(data)} rows, capture_id={capture_id[:50]}...")
            
        except Exception as e:
            logger.error(f"  Insert error for {symbol}: {e}")
            result.failed.append({"symbol": symbol, "error": str(e)})
    
    result.duration_seconds = time.time() - start_time
    return result


def print_summary(result: ScheduleResult, logger: logging.Logger) -> None:
    """Print execution summary."""
    logger.info("=" * 60)
    logger.info("EXECUTION SUMMARY")
    logger.info("=" * 60)
    logger.info(f"Duration:        {result.duration_seconds:.1f}s")
    logger.info(f"Success:         {len(result.success)} symbols")
    logger.info(f"Failed:          {len(result.failed)} symbols")
    logger.info(f"Skipped:         {len(result.skipped)} symbols")
    logger.info(f"Total rows:      {result.total_rows}")
    logger.info(f"New captures:    {result.new_captures}")
    logger.info(f"Anomalies:       {result.anomalies_recorded}")
    
    if result.success:
        logger.info(f"Successful:      {', '.join(result.success)}")
    if result.failed:
        for f in result.failed:
            logger.error(f"Failed:          {f['symbol']} - {f['error']}")
    if result.skipped:
        logger.info(f"Skipped:         {', '.join(result.skipped)}")


# =============================================================================
# CLI
# =============================================================================

def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Scheduled price data ingestion for Market Spine",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Ingest specific symbols
  python run_price_schedule.py --symbols AAPL,MSFT,GOOGL --mode run

  # Ingest from file
  python run_price_schedule.py --symbols-file watchlist.txt --mode run

  # Dry run (no database writes)
  python run_price_schedule.py --symbols AAPL --mode dry-run

  # Full historical data
  python run_price_schedule.py --symbols AAPL --outputsize full
        """,
    )
    
    # Symbol specification (mutually exclusive)
    symbol_group = parser.add_mutually_exclusive_group(required=True)
    symbol_group.add_argument(
        "--symbols",
        type=str,
        help="Comma-separated list of symbols (e.g., AAPL,MSFT,GOOGL)",
    )
    symbol_group.add_argument(
        "--symbols-file",
        type=str,
        help="Path to file with symbols (one per line)",
    )
    
    # Data options
    parser.add_argument(
        "--outputsize",
        choices=["compact", "full"],
        default="compact",
        help="Data size: compact (~100 days) or full (20+ years)",
    )
    parser.add_argument(
        "--source-type",
        type=str,
        default=None,
        help="Data source: alpha_vantage (default: auto-detect from env)",
    )
    
    # Rate limiting
    parser.add_argument(
        "--sleep-between",
        type=float,
        default=12.0,
        help="Seconds to sleep between API calls (default: 12 for 5 req/min)",
    )
    parser.add_argument(
        "--max-symbols-per-batch",
        type=int,
        default=25,
        help="Max symbols per run (default: 25 for daily limit)",
    )
    
    # Execution mode
    parser.add_argument(
        "--mode",
        choices=["run", "dry-run"],
        default="run",
        help="Execution mode: run (write to DB) or dry-run (fetch only)",
    )
    
    # Logging
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Logging level (default: INFO)",
    )
    
    # Database
    parser.add_argument(
        "--db-path",
        type=str,
        default=None,
        help="Database path (default: from environment or spine.db)",
    )
    
    return parser.parse_args()


def main() -> int:
    """Main entry point."""
    args = parse_args()
    logger = setup_logging(args.log_level)
    
    # Build config
    config = ScheduleConfig(
        source_type=args.source_type,
        outputsize=args.outputsize,
        sleep_between=args.sleep_between,
        max_symbols_per_batch=args.max_symbols_per_batch,
        mode=args.mode,
        db_path=args.db_path,
        log_level=args.log_level,
    )
    
    # Load symbols
    if args.symbols:
        config.symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    elif args.symbols_file:
        if not os.path.exists(args.symbols_file):
            logger.error(f"Symbols file not found: {args.symbols_file}")
            return 3
        config.symbols = load_symbols_from_file(args.symbols_file)
    
    if not config.symbols:
        logger.error("No symbols specified")
        return 3
    
    logger.info(f"Loaded {len(config.symbols)} symbols")
    
    # Set database path if specified
    if config.db_path:
        os.environ["MARKET_SPINE_DB_PATH"] = config.db_path
    
    # Run schedule
    try:
        result = run_schedule(config, logger)
    except Exception as e:
        logger.exception(f"Schedule execution failed: {e}")
        return 2
    
    # Print summary
    print_summary(result, logger)
    
    # Determine exit code
    if not result.success and not result.skipped:
        return 2  # All failed
    elif result.failed:
        return 1  # Partial success
    else:
        return 0  # All succeeded


if __name__ == "__main__":
    sys.exit(main())
