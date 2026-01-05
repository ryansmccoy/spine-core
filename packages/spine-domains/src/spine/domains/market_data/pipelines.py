"""
Market Data Pipelines - Price data ingestion from external sources.

Each pipeline is a thin orchestrator that:
1. Uses spine.core primitives (manifest, rejects, quality)
2. Calls domain-specific sources (alpha_vantage, polygon, etc.)
3. Writes results to storage

Pipeline Registration Names:
- market_data.ingest_prices
- market_data.ingest_prices_batch

To run:
    spine run market_data.ingest_prices -p symbol=AAPL
    spine run market_data.ingest_prices -p symbol=AAPL -p outputsize=full
    spine run market_data.ingest_prices_batch -p symbols=AAPL,MSFT,GOOGL
"""

from datetime import datetime, UTC
from typing import Any

from spine.domains.market_data.sources import create_source, IngestionError, FetchResult
from spine.framework.db import get_connection
from spine.framework.logging import get_logger, log_step
from spine.framework.params import ParamDef, PipelineSpec
from spine.framework.pipelines import Pipeline, PipelineResult, PipelineStatus
from spine.framework.registry import register_pipeline

log = get_logger(__name__)

# Domain constants
DOMAIN = "market_data"
TABLES = {
    "prices_daily": "market_data_prices_daily",
}


def ensure_schema(conn) -> None:
    """Create price tables if they don't exist."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS market_data_prices_daily (
            symbol TEXT NOT NULL,
            date TEXT NOT NULL,
            open REAL NOT NULL,
            high REAL NOT NULL,
            low REAL NOT NULL,
            close REAL NOT NULL,
            volume INTEGER NOT NULL,
            change REAL,
            change_percent REAL,
            source TEXT NOT NULL DEFAULT 'alpha_vantage',
            capture_id TEXT NOT NULL,
            captured_at TEXT NOT NULL,
            execution_id TEXT,
            batch_id TEXT,
            input_capture_id TEXT,
            is_valid INTEGER DEFAULT 1,
            PRIMARY KEY (symbol, date, capture_id)
        );
        
        CREATE INDEX IF NOT EXISTS idx_market_data_prices_daily_symbol_date 
            ON market_data_prices_daily(symbol, date DESC);
    """)


def calculate_changes(rows: list[dict]) -> list[dict]:
    """Calculate daily price changes from prior close."""
    # Sort by date ascending to calculate changes
    sorted_rows = sorted(rows, key=lambda r: r["date"])
    
    for i, row in enumerate(sorted_rows):
        if i == 0:
            row["change"] = None
            row["change_percent"] = None
        else:
            prev_close = sorted_rows[i - 1]["close"]
            row["change"] = row["close"] - prev_close
            row["change_percent"] = (row["change"] / prev_close) * 100 if prev_close else None
    
    return sorted_rows


@register_pipeline("market_data.ingest_prices")
class IngestPricesPipeline(Pipeline):
    """
    Ingest daily OHLCV price data for a symbol.

    Supports multiple data sources:
    - alpha_vantage: Free tier (25 req/day, 5 req/min)
    - polygon: (future) Polygon.io API
    - yahoo: (future) Yahoo Finance

    Params:
        symbol: Stock symbol to fetch (e.g., "AAPL")
        source_type: Data source (default: auto-detect from env)
        outputsize: "compact" (100 days) or "full" (20+ years)
        force: Re-ingest even if already done (default: False)
    """

    name = "market_data.ingest_prices"
    description = "Fetch daily OHLCV price data from external market data sources"
    spec = PipelineSpec(
        required_params={
            "symbol": ParamDef(
                name="symbol",
                type=str,
                description="Stock symbol to fetch (e.g., AAPL, MSFT)",
                required=True,
            ),
        },
        optional_params={
            "source_type": ParamDef(
                name="source_type",
                type=str,
                description="Data source: 'alpha_vantage', 'polygon' (auto-detected if not specified)",
                required=False,
            ),
            "outputsize": ParamDef(
                name="outputsize",
                type=str,
                description="'compact' (100 days) or 'full' (20+ years)",
                required=False,
                default="compact",
            ),
            "force": ParamDef(
                name="force",
                type=bool,
                description="Re-ingest even if already ingested today",
                required=False,
                default=False,
            ),
        },
        examples=[
            "spine run market_data.ingest_prices -p symbol=AAPL",
            "spine run market_data.ingest_prices -p symbol=MSFT -p outputsize=full",
            "spine run market_data.ingest_prices -p symbol=GOOGL -p source_type=alpha_vantage",
        ],
        notes=[
            "Alpha Vantage free tier: 25 requests/day, 5 requests/minute",
            "Use outputsize=full for historical backfill (slow, rate-limited)",
            "Data includes: open, high, low, close, volume + calculated changes",
        ],
    )

    def run(self) -> PipelineResult:
        started = datetime.now(UTC)
        conn = get_connection()

        # Ensure schema exists
        ensure_schema(conn)

        # Parse params
        symbol = self.params["symbol"].upper()
        source_type = self.params.get("source_type")
        outputsize = self.params.get("outputsize", "compact")
        force = self.params.get("force", False)

        log.info("ingest_prices.start", symbol=symbol, outputsize=outputsize)

        # Create source via factory
        try:
            source = create_source(source_type=source_type)
        except ValueError as e:
            return PipelineResult(
                status=PipelineStatus.FAILED,
                started_at=started,
                completed_at=datetime.now(UTC),
                error=f"Failed to create source: {e}",
            )

        source_name = type(source).__name__.replace("Source", "").lower()
        log.info("ingest_prices.source_created", source_type=source_name)

        # Fetch data from source (returns FetchResult)
        try:
            with log_step("ingest_prices.fetch", symbol=symbol):
                result: FetchResult = source.fetch({"symbol": symbol, "outputsize": outputsize})
        except IngestionError as e:
            return PipelineResult(
                status=PipelineStatus.FAILED,
                started_at=started,
                completed_at=datetime.now(UTC),
                error=f"Fetch failed: {e}",
            )

        # Handle anomalies (rate limits, etc.)
        if result.anomalies:
            messages = [f"{a['category']}: {a['message']}" for a in result.anomalies]
            return PipelineResult(
                status=PipelineStatus.FAILED,
                started_at=started,
                completed_at=datetime.now(UTC),
                error=f"Source returned anomalies: {'; '.join(messages)}",
                metrics={"anomalies": len(result.anomalies)},
            )

        if not result.data:
            return PipelineResult(
                status=PipelineStatus.COMPLETED,
                started_at=started,
                completed_at=datetime.now(UTC),
                metrics={"rows_fetched": 0, "rows_inserted": 0, "symbol": symbol},
            )

        # Calculate daily changes
        with log_step("ingest_prices.calculate_changes"):
            data = calculate_changes(result.data)

        # Generate capture metadata - use content_hash if available for uniqueness
        now = datetime.now(UTC)
        content_hash_suffix = ""
        if result.metadata and result.metadata.content_hash:
            content_hash_suffix = f".{result.metadata.content_hash[:8]}"
        capture_id = f"market_data.prices.{symbol}.{now.strftime('%Y%m%dT%H%M%SZ')}{content_hash_suffix}"
        captured_at = now.isoformat().replace("+00:00", "Z")

        # Insert into database
        with log_step("ingest_prices.insert", rows=len(data)):
            cursor = conn.cursor()
            
            for row in data:
                cursor.execute("""
                    INSERT INTO market_data_prices_daily 
                    (symbol, date, open, high, low, close, volume, change, change_percent,
                     source, capture_id, captured_at, is_valid)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                    ON CONFLICT (symbol, date, capture_id) DO UPDATE SET
                        open = excluded.open,
                        high = excluded.high,
                        low = excluded.low,
                        close = excluded.close,
                        volume = excluded.volume,
                        change = excluded.change,
                        change_percent = excluded.change_percent
                """, (
                    row["symbol"],
                    row["date"],
                    row["open"],
                    row["high"],
                    row["low"],
                    row["close"],
                    row["volume"],
                    row.get("change"),
                    row.get("change_percent"),
                    source_name,
                    capture_id,
                    captured_at,
                ))
            
            conn.commit()

        log.info("ingest_prices.complete", symbol=symbol, rows=len(data))

        return PipelineResult(
            status=PipelineStatus.COMPLETED,
            started_at=started,
            completed_at=datetime.now(UTC),
            metrics={
                "rows_fetched": len(data),
                "rows_inserted": len(data),
                "symbol": symbol,
                "source": source_name,
                "capture_id": capture_id,
                "content_hash": result.metadata.content_hash if result.metadata else None,
            },
        )


# =============================================================================
# Batch Ingestion Pipeline
# =============================================================================

@register_pipeline("market_data.ingest_prices_batch")
class IngestPricesBatchPipeline(Pipeline):
    """
    Ingest daily OHLCV price data for multiple symbols.

    Rate-limit aware batch processing with configurable delays.

    Params:
        symbols: Comma-separated list of symbols (e.g., "AAPL,MSFT,GOOGL")
        source_type: Data source (default: auto-detect from env)
        outputsize: "compact" (100 days) or "full" (20+ years)
        sleep_between: Seconds to sleep between symbols (default: 12)
    """

    name = "market_data.ingest_prices_batch"
    description = "Batch ingest daily OHLCV price data for multiple symbols"
    spec = PipelineSpec(
        required_params={
            "symbols": ParamDef(
                name="symbols",
                type=str,
                description="Comma-separated list of symbols (e.g., AAPL,MSFT,GOOGL)",
                required=True,
            ),
        },
        optional_params={
            "source_type": ParamDef(
                name="source_type",
                type=str,
                description="Data source: 'alpha_vantage', 'polygon'",
                required=False,
            ),
            "outputsize": ParamDef(
                name="outputsize",
                type=str,
                description="'compact' (100 days) or 'full' (20+ years)",
                required=False,
                default="compact",
            ),
            "sleep_between": ParamDef(
                name="sleep_between",
                type=float,
                description="Seconds to sleep between API calls (default: 12 for rate limiting)",
                required=False,
                default=12.0,
            ),
        },
        examples=[
            "spine run market_data.ingest_prices_batch -p symbols=AAPL,MSFT,GOOGL",
            "spine run market_data.ingest_prices_batch -p symbols=AAPL,MSFT -p sleep_between=15",
        ],
        notes=[
            "Alpha Vantage free tier: 5 requests/minute, use sleep_between>=12",
            "Failures for individual symbols do not stop the batch",
        ],
    )

    def run(self) -> PipelineResult:
        import time as time_module
        
        started = datetime.now(UTC)
        conn = get_connection()
        ensure_schema(conn)

        # Parse params
        symbols_str = self.params["symbols"]
        symbols = [s.strip().upper() for s in symbols_str.split(",") if s.strip()]
        source_type = self.params.get("source_type")
        outputsize = self.params.get("outputsize", "compact")
        sleep_between = float(self.params.get("sleep_between", 12.0))

        if not symbols:
            return PipelineResult(
                status=PipelineStatus.FAILED,
                started_at=started,
                completed_at=datetime.now(UTC),
                error="No symbols provided",
            )

        log.info("ingest_prices_batch.start", symbols=symbols, count=len(symbols))

        # Create source
        try:
            source = create_source(source_type=source_type)
        except ValueError as e:
            return PipelineResult(
                status=PipelineStatus.FAILED,
                started_at=started,
                completed_at=datetime.now(UTC),
                error=f"Failed to create source: {e}",
            )

        source_name = type(source).__name__.replace("Source", "").lower()

        # Process each symbol
        results = {"success": [], "failed": [], "skipped": []}
        total_rows = 0

        for i, symbol in enumerate(symbols):
            if i > 0:
                log.info("ingest_prices_batch.sleeping", seconds=sleep_between)
                time_module.sleep(sleep_between)

            log.info("ingest_prices_batch.processing", symbol=symbol, index=i + 1, total=len(symbols))

            try:
                result: FetchResult = source.fetch({"symbol": symbol, "outputsize": outputsize})
            except Exception as e:
                log.warning("ingest_prices_batch.fetch_error", symbol=symbol, error=str(e))
                results["failed"].append({"symbol": symbol, "error": str(e)})
                continue

            if result.anomalies:
                messages = [f"{a['category']}: {a['message']}" for a in result.anomalies]
                log.warning("ingest_prices_batch.anomalies", symbol=symbol, anomalies=messages)
                results["failed"].append({"symbol": symbol, "error": "; ".join(messages)})
                continue

            if not result.data:
                results["skipped"].append(symbol)
                continue

            # Calculate changes and insert
            data = calculate_changes(result.data)
            now = datetime.now(UTC)
            content_hash_suffix = ""
            if result.metadata and result.metadata.content_hash:
                content_hash_suffix = f".{result.metadata.content_hash[:8]}"
            capture_id = f"market_data.prices.{symbol}.{now.strftime('%Y%m%dT%H%M%SZ')}{content_hash_suffix}"
            captured_at = now.isoformat().replace("+00:00", "Z")

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

            results["success"].append(symbol)
            total_rows += len(data)
            log.info("ingest_prices_batch.symbol_complete", symbol=symbol, rows=len(data))

        log.info("ingest_prices_batch.complete", 
                 success=len(results["success"]),
                 failed=len(results["failed"]),
                 skipped=len(results["skipped"]))

        status = PipelineStatus.COMPLETED if not results["failed"] else PipelineStatus.COMPLETED
        if len(results["failed"]) == len(symbols):
            status = PipelineStatus.FAILED

        return PipelineResult(
            status=status,
            started_at=started,
            completed_at=datetime.now(UTC),
            metrics={
                "symbols_requested": len(symbols),
                "symbols_success": len(results["success"]),
                "symbols_failed": len(results["failed"]),
                "symbols_skipped": len(results["skipped"]),
                "total_rows_inserted": total_rows,
                "source": source_name,
            },
        )
