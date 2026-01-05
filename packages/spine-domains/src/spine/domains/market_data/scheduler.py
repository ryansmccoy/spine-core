"""
Market Data Scheduler - Batch price ingestion orchestration.

This module provides reusable scheduler entrypoints for price data ingestion.
Designed to be called from thin wrapper scripts or cron/k8s jobs.

Key Features:
    - Symbol batch processing with rate limiting
    - Idempotent execution (same symbol re-fetch is safe)
    - Anomaly recording for failures
    - Dry-run mode for testing
    - Clear result reporting

Usage:
    from spine.domains.market_data.scheduler import run_price_schedule
    
    result = run_price_schedule(
        symbols=["AAPL", "MSFT", "GOOGL"],
        mode="run",
        db_path="data/market_spine.db",
    )
    
    if result.has_failures:
        sys.exit(1)
"""

import time
from dataclasses import dataclass, field
from datetime import datetime, date, UTC
from pathlib import Path
from typing import Any
import hashlib
import logging
import uuid

log = logging.getLogger(__name__)


# =============================================================================
# Configuration
# =============================================================================

@dataclass
class PriceScheduleConfig:
    """Configuration for scheduled price ingestion."""
    symbols: list[str] = field(default_factory=list)
    source_type: str | None = None
    outputsize: str = "compact"
    lookback_days: int = 100  # compact = ~100 days
    sleep_between: float = 12.0  # seconds between API calls (5 req/min = 12s)
    max_symbols_per_batch: int = 25  # Alpha Vantage daily limit
    mode: str = "run"  # "run" or "dry-run"
    fail_fast: bool = False  # Stop on first failure
    db_path: str | None = None
    log_level: str = "INFO"


@dataclass
class PriceScheduleResult:
    """Result of scheduled price ingestion."""
    success: list[str] = field(default_factory=list)
    failed: list[dict] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    total_rows: int = 0
    new_captures: int = 0
    duration_seconds: float = 0.0
    anomalies_recorded: int = 0
    
    @property
    def has_failures(self) -> bool:
        """True if any symbols failed."""
        return len(self.failed) > 0
    
    @property
    def all_failed(self) -> bool:
        """True if all symbols failed."""
        return len(self.success) == 0 and len(self.failed) > 0
    
    def as_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "success": self.success,
            "failed": self.failed,
            "skipped": self.skipped,
            "total_rows": self.total_rows,
            "new_captures": self.new_captures,
            "duration_seconds": self.duration_seconds,
            "anomalies_recorded": self.anomalies_recorded,
            "has_failures": self.has_failures,
            "all_failed": self.all_failed,
        }


# =============================================================================
# Core Functions
# =============================================================================

def generate_price_capture_id(symbol: str, source: str, run_date: date) -> str:
    """
    Generate deterministic capture_id for price ingestion.
    
    Format: market_data.prices.{symbol}.{source}.{YYYYMMDD}
    """
    return f"market_data.prices.{symbol}.{source}.{run_date.strftime('%Y%m%d')}"


def record_price_anomaly(
    conn,
    symbol: str,
    severity: str,
    category: str,
    message: str,
    metadata: dict | None = None,
) -> None:
    """Record an anomaly for price ingestion."""
    import json
    
    anomaly_id = str(uuid.uuid4())
    detected_at = datetime.now(UTC).isoformat()
    
    conn.execute("""
        INSERT INTO core_anomalies (
            anomaly_id, domain, stage, partition_key,
            severity, category, message,
            detected_at, metadata, resolved_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
    """, (
        anomaly_id,
        "market_data",
        "INGEST",
        symbol,
        severity,
        category,
        message,
        detected_at,
        json.dumps(metadata) if metadata else None,
    ))
    conn.commit()


def process_symbol(
    symbol: str,
    config: PriceScheduleConfig,
    conn,
    run_date: date,
) -> tuple[bool, dict[str, Any]]:
    """
    Process a single symbol for ingestion.
    
    Returns:
        (success: bool, result: dict with rows/error info)
    """
    from spine.domains.market_data.sources import create_source, IngestionError
    
    capture_id = generate_price_capture_id(
        symbol,
        config.source_type or "alpha_vantage",
        run_date,
    )
    
    if config.mode == "dry-run":
        log.info(f"[DRY-RUN] Would ingest {symbol} with capture_id: {capture_id}")
        return (True, {"mode": "dry-run", "capture_id": capture_id})
    
    try:
        # Create source and fetch
        source = create_source(source_type=config.source_type)
        result = source.fetch({
            "symbol": symbol,
            "outputsize": config.outputsize,
        })
        
        if not result.success:
            record_price_anomaly(
                conn,
                symbol=symbol,
                severity="ERROR",
                category="FETCH_FAILED",
                message=f"Fetch failed: {result.error}",
                metadata={"source": config.source_type},
            )
            return (False, {"error": result.error})
        
        # Insert rows
        rows = result.data or []
        if not rows:
            log.warning(f"No data returned for {symbol}")
            return (True, {"rows": 0, "warning": "no_data"})
        
        # Ensure schema exists
        from spine.domains.market_data.pipelines import ensure_schema
        ensure_schema(conn)
        
        # Insert with capture_id
        captured_at = datetime.now(UTC).isoformat()
        inserted = 0
        
        for row in rows:
            try:
                conn.execute("""
                    INSERT OR REPLACE INTO market_data_prices_daily (
                        symbol, date, open, high, low, close, volume,
                        change, change_percent, source,
                        capture_id, captured_at, is_valid
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                """, (
                    symbol,
                    row["date"],
                    row["open"],
                    row["high"],
                    row["low"],
                    row["close"],
                    row.get("volume", 0),
                    row.get("change"),
                    row.get("change_percent"),
                    config.source_type or "alpha_vantage",
                    capture_id,
                    captured_at,
                ))
                inserted += 1
            except Exception as e:
                log.warning(f"Failed to insert row for {symbol}: {e}")
        
        conn.commit()
        log.info(f"✓ {symbol}: inserted {inserted} rows")
        return (True, {"rows": inserted, "capture_id": capture_id})
        
    except IngestionError as e:
        record_price_anomaly(
            conn,
            symbol=symbol,
            severity="ERROR",
            category="INGESTION_ERROR",
            message=str(e),
            metadata={"source": config.source_type},
        )
        return (False, {"error": str(e)})
    except Exception as e:
        log.error(f"Unexpected error for {symbol}: {e}")
        record_price_anomaly(
            conn,
            symbol=symbol,
            severity="ERROR",
            category="UNEXPECTED_ERROR",
            message=str(e),
            metadata={"source": config.source_type},
        )
        return (False, {"error": str(e)})


# =============================================================================
# Main Entrypoint
# =============================================================================

def run_price_schedule(
    symbols: list[str],
    mode: str = "run",
    source_type: str | None = None,
    outputsize: str = "compact",
    sleep_between: float = 12.0,
    max_symbols: int | None = None,
    fail_fast: bool = False,
    db_path: str | None = None,
    run_date: date | None = None,
) -> PriceScheduleResult:
    """
    Run scheduled price ingestion for multiple symbols.
    
    This is the main entrypoint for scheduler scripts.
    
    Args:
        symbols: List of stock symbols to ingest
        mode: "run" or "dry-run"
        source_type: Source type (None = auto-detect from env)
        outputsize: "compact" (~100 days) or "full" (20 years)
        sleep_between: Seconds to wait between API calls
        max_symbols: Maximum symbols to process (for rate limiting)
        fail_fast: Stop on first failure
        db_path: Database path
        run_date: Reference date for capture_id generation
    
    Returns:
        PriceScheduleResult with success/failed/skipped lists
    """
    import sqlite3
    
    start_time = time.time()
    run_date = run_date or date.today()
    
    config = PriceScheduleConfig(
        symbols=symbols,
        source_type=source_type,
        outputsize=outputsize,
        sleep_between=sleep_between,
        max_symbols_per_batch=max_symbols or 25,
        mode=mode,
        fail_fast=fail_fast,
        db_path=db_path,
    )
    
    result = PriceScheduleResult()
    
    # Limit symbols if needed
    symbols_to_process = symbols[:config.max_symbols_per_batch]
    if len(symbols) > len(symbols_to_process):
        result.skipped = symbols[config.max_symbols_per_batch:]
        log.warning(f"Skipping {len(result.skipped)} symbols (batch limit: {config.max_symbols_per_batch})")
    
    # Open database connection
    db_path_resolved = db_path or "data/market_spine.db"
    conn = sqlite3.connect(db_path_resolved)
    
    try:
        for i, symbol in enumerate(symbols_to_process):
            log.info(f"[{i+1}/{len(symbols_to_process)}] Processing {symbol}...")
            
            success, details = process_symbol(symbol, config, conn, run_date)
            
            if success:
                result.success.append(symbol)
                result.total_rows += details.get("rows", 0)
                if details.get("capture_id"):
                    result.new_captures += 1
            else:
                result.failed.append({"symbol": symbol, "error": details.get("error")})
                result.anomalies_recorded += 1
                
                if fail_fast:
                    log.error(f"Fail-fast: stopping due to failure on {symbol}")
                    # Mark remaining as skipped
                    result.skipped.extend(symbols_to_process[i+1:])
                    break
            
            # Rate limiting (skip on last symbol)
            if i < len(symbols_to_process) - 1 and config.sleep_between > 0:
                log.debug(f"Rate limit: sleeping {config.sleep_between}s...")
                time.sleep(config.sleep_between)
    
    finally:
        conn.close()
    
    result.duration_seconds = time.time() - start_time
    
    # Log summary
    log.info(f"Schedule complete: {len(result.success)} success, {len(result.failed)} failed, {len(result.skipped)} skipped")
    log.info(f"Total rows: {result.total_rows}, Duration: {result.duration_seconds:.1f}s")
    
    return result
