"""
Market Data Scheduler - Batch price ingestion orchestration.

This module provides reusable scheduler entrypoints for price data ingestion.
Designed to be called from thin wrapper scripts or cron/k8s jobs.

Key Features:
    - Symbol batch processing with rate limiting
    - Idempotent execution (same symbol re-fetch is safe)
    - Anomaly recording for failures
    - Dry-run mode for testing
    - Returns standardized SchedulerResult contract

Usage:
    from spine.domains.market_data.scheduler import run_price_schedule
    
    result = run_price_schedule(
        symbols=["AAPL", "MSFT", "GOOGL"],
        mode="run",
        db_path="data/market_spine.db",
    )
    
    print(result.to_json())
    sys.exit(result.exit_code)
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
# Constants
# =============================================================================

DOMAIN = "market_data"
SCHEDULER_NAME = "price_ingest"


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


# Legacy result type (deprecated, use SchedulerResult)
@dataclass
class PriceScheduleResult:
    """DEPRECATED: Use SchedulerResult instead. Kept for backwards compatibility."""
    success: list[str] = field(default_factory=list)
    failed: list[dict] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    total_rows: int = 0
    new_captures: int = 0
    duration_seconds: float = 0.0
    anomalies_recorded: int = 0
    _exit_code: int = 0
    
    @property
    def has_failures(self) -> bool:
        """True if any symbols failed."""
        return len(self.failed) > 0
    
    @property
    def all_failed(self) -> bool:
        """True if all symbols failed."""
        return len(self.success) == 0 and len(self.failed) > 0
    
    @property
    def exit_code(self) -> int:
        """Exit code for CLI: 0=success, 1=failure, 2=partial."""
        return self._exit_code
    
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
# Result Contract Import (lazy to avoid circular deps)
# =============================================================================

def _get_result_contract():
    """Import result contract from market_spine.app.scheduling."""
    try:
        from market_spine.app.scheduling import (
            SchedulerResult,
            SchedulerStats,
            SchedulerStatus,
            RunResult,
            RunStatus,
            AnomalySummary,
        )
        return SchedulerResult, SchedulerStats, SchedulerStatus, RunResult, RunStatus, AnomalySummary
    except ImportError:
        # Fallback if market_spine not installed
        return None, None, None, None, None, None


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
):
    """
    Run scheduled price ingestion for multiple symbols.
    
    This is the main entrypoint for scheduler scripts.
    Returns a SchedulerResult (standardized contract) if available,
    otherwise falls back to a compatible dict.
    
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
        SchedulerResult with runs[], stats, anomalies, exit_code
    """
    import sqlite3
    
    # Import result contract
    SchedulerResult, SchedulerStats, SchedulerStatus, RunResult, RunStatus, AnomalySummary = _get_result_contract()
    
    started_at = datetime.now(UTC).isoformat()
    start_time = time.time()
    run_date = run_date or date.today()
    
    # Build result tracking
    warnings = []
    runs = []
    anomalies = []
    stats = {"attempted": 0, "succeeded": 0, "failed": 0, "skipped": 0}
    
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
    
    config_dict = {
        "symbols_count": len(symbols),
        "source_type": config.source_type,
        "outputsize": config.outputsize,
        "max_symbols_per_batch": config.max_symbols_per_batch,
        "mode": config.mode,
        "fail_fast": config.fail_fast,
    }
    
    # Legacy result for backwards compatibility
    legacy_result = PriceScheduleResult()
    
    # Limit symbols if needed
    symbols_to_process = symbols[:config.max_symbols_per_batch]
    if len(symbols) > len(symbols_to_process):
        legacy_result.skipped = symbols[config.max_symbols_per_batch:]
        stats["skipped"] = len(legacy_result.skipped)
        warnings.append(f"Skipping {len(legacy_result.skipped)} symbols (batch limit: {config.max_symbols_per_batch})")
        log.warning(warnings[-1])
    
    # Open database connection
    db_path_resolved = db_path or "data/market_spine.db"
    conn = sqlite3.connect(db_path_resolved)
    
    try:
        for i, symbol in enumerate(symbols_to_process):
            log.info(f"[{i+1}/{len(symbols_to_process)}] Processing {symbol}...")
            stats["attempted"] += 1
            stage_start = time.time()
            
            success, details = process_symbol(symbol, config, conn, run_date)
            duration_ms = int((time.time() - stage_start) * 1000)
            
            if success:
                legacy_result.success.append(symbol)
                legacy_result.total_rows += details.get("rows", 0)
                if details.get("capture_id"):
                    legacy_result.new_captures += 1
                stats["succeeded"] += 1
                
                if RunResult:
                    run_status = RunStatus.DRY_RUN if mode == "dry-run" else RunStatus.COMPLETED
                    runs.append(RunResult(
                        pipeline=f"{DOMAIN}.ingest_prices",
                        partition_key=symbol,
                        status=run_status,
                        duration_ms=duration_ms,
                        capture_id=details.get("capture_id"),
                        rows_affected=details.get("rows", 0),
                    ))
            else:
                legacy_result.failed.append({"symbol": symbol, "error": details.get("error")})
                legacy_result.anomalies_recorded += 1
                stats["failed"] += 1
                
                if RunResult:
                    runs.append(RunResult(
                        pipeline=f"{DOMAIN}.ingest_prices",
                        partition_key=symbol,
                        status=RunStatus.FAILED,
                        duration_ms=duration_ms,
                        error=details.get("error", "Unknown error")[:500],
                    ))
                
                if fail_fast:
                    log.error(f"Fail-fast: stopping due to failure on {symbol}")
                    # Mark remaining as skipped
                    remaining = symbols_to_process[i+1:]
                    legacy_result.skipped.extend(remaining)
                    stats["skipped"] += len(remaining)
                    break
            
            # Rate limiting (skip on last symbol)
            if i < len(symbols_to_process) - 1 and config.sleep_between > 0:
                log.debug(f"Rate limit: sleeping {config.sleep_between}s...")
                time.sleep(config.sleep_between)
    
    finally:
        conn.close()
    
    finished_at = datetime.now(UTC).isoformat()
    legacy_result.duration_seconds = time.time() - start_time
    
    # Determine status
    if mode == "dry-run":
        status = SchedulerStatus.DRY_RUN if SchedulerStatus else "dry_run"
    elif stats["failed"] == 0:
        status = SchedulerStatus.SUCCESS if SchedulerStatus else "success"
    elif stats["succeeded"] > 0:
        status = SchedulerStatus.PARTIAL if SchedulerStatus else "partial"
    else:
        status = SchedulerStatus.FAILURE if SchedulerStatus else "failure"
    
    # Log summary
    log.info(f"Schedule complete: {len(legacy_result.success)} success, {len(legacy_result.failed)} failed, {len(legacy_result.skipped)} skipped")
    log.info(f"Total rows: {legacy_result.total_rows}, Duration: {legacy_result.duration_seconds:.1f}s")
    
    # Build and return SchedulerResult if available
    if SchedulerResult:
        return SchedulerResult(
            domain=DOMAIN,
            scheduler=SCHEDULER_NAME,
            started_at=started_at,
            finished_at=finished_at,
            status=status,
            stats=SchedulerStats(**stats),
            runs=runs,
            anomalies=anomalies,
            warnings=warnings,
            config=config_dict,
        )
    
    # Fallback: return legacy result with added exit_code property
    legacy_result._exit_code = 0 if status in ("success", "dry_run") else (2 if status == "partial" else 1)
    return legacy_result
