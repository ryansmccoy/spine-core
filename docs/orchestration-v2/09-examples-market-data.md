# Real Examples: Market Data & Exchange Calendar

> **Document**: Practical examples using market_data and exchange_calendar domains

## Overview

This document shows how to implement real market data workflows using Orchestration v2. These examples are based on the existing pipelines in `packages/spine-domains/src/spine/domains/market_data/` and `exchange_calendar/`.

---

## Example 1: Daily Price Feed Workflow

A daily workflow that handles market data prices with calendar awareness:

```python
from spine.orchestration import (
    Workflow,
    Step,
    WorkflowContext,
    StepResult,
    QualityMetrics,
)
from datetime import date


# ============================================================================
# Lambda Steps
# ============================================================================

def check_market_open(ctx: WorkflowContext, config: dict) -> StepResult:
    """
    Check if the market is open today.
    
    Skip processing on weekends and market holidays.
    Uses exchange_calendar domain.
    """
    run_date = date.fromisoformat(ctx.params.get("run_date", date.today().isoformat()))
    exchange = ctx.params.get("exchange", "NYSE")
    
    # Would call: exchange_calendar.is_trading_day(exchange, run_date)
    # For example, check against known holidays
    is_trading_day = run_date.weekday() < 5  # Simple weekend check
    
    if not is_trading_day:
        return StepResult.ok(
            output={
                "is_trading_day": False,
                "reason": "weekend" if run_date.weekday() >= 5 else "holiday",
            },
            context_updates={
                "skip_processing": True,
                "skip_reason": f"Market closed on {run_date}",
            },
        )
    
    return StepResult.ok(
        output={
            "is_trading_day": True,
            "exchange": exchange,
            "run_date": run_date.isoformat(),
        },
        context_updates={
            "skip_processing": False,
        },
    )


def validate_price_data(ctx: WorkflowContext, config: dict) -> StepResult:
    """
    Validate price data quality.
    
    Checks:
    - No stale prices (all prices from today)
    - No extreme price movements (>50% change)
    - Required symbols present
    """
    fetch_result = ctx.get_output("fetch_prices", {})
    records = fetch_result.get("records", [])
    run_date = ctx.params.get("run_date")
    
    # Quality checks
    stale_count = 0
    extreme_moves = []
    
    for record in records:
        # Check freshness
        if record.get("price_date") != run_date:
            stale_count += 1
        
        # Check price movement
        pct_change = abs(record.get("pct_change", 0))
        if pct_change > 0.50:  # >50% move
            extreme_moves.append({
                "symbol": record.get("symbol"),
                "pct_change": pct_change,
            })
    
    total_count = len(records)
    stale_rate = stale_count / total_count if total_count > 0 else 0
    
    quality = QualityMetrics(
        record_count=total_count,
        valid_count=total_count - stale_count,
        null_rate=0.0,
        custom_metrics={
            "stale_rate": stale_rate,
            "extreme_moves_count": len(extreme_moves),
        },
        passed=stale_rate < 0.05 and len(extreme_moves) < 10,
    )
    
    if not quality.passed:
        return StepResult.fail(
            error=f"Price data quality failed: {stale_rate:.1%} stale, {len(extreme_moves)} extreme moves",
            category="DATA_QUALITY",
            output={
                "stale_count": stale_count,
                "extreme_moves": extreme_moves[:10],
            },
        )
    
    return StepResult.ok(
        output={
            "validated": True,
            "total_records": total_count,
            "stale_count": stale_count,
            "extreme_moves": extreme_moves,
        },
        quality=quality,
    )


def calculate_derived_metrics(ctx: WorkflowContext, config: dict) -> StepResult:
    """
    Calculate derived metrics from price data.
    
    Examples: moving averages, volatility, relative strength.
    """
    # This would call actual calculation logic
    # For demonstration, just return success
    
    metrics_calculated = [
        "sma_20",
        "sma_50", 
        "sma_200",
        "volatility_20d",
        "relative_strength",
    ]
    
    return StepResult.ok(
        output={
            "metrics_calculated": metrics_calculated,
            "record_count": ctx.get_output("validate_prices", "total_records", 0),
        },
    )


# ============================================================================
# Workflow Definition
# ============================================================================

daily_price_workflow = Workflow(
    name="market_data.daily_prices",
    domain="market_data",
    description="Daily price feed with calendar awareness and quality gates",
    steps=[
        # Step 1: Check if market open
        Step.lambda_("check_market", check_market_open),
        
        # Step 2: Skip if market closed
        Step.choice("market_open_check",
            condition=lambda ctx: not ctx.params.get("skip_processing", False),
            then_step="fetch_prices",
            else_step="log_skip",
        ),
        
        # Step 3: Log skip (if market closed)
        Step.lambda_("log_skip", lambda ctx, cfg: StepResult.ok(
            output={"skipped": True, "reason": ctx.params.get("skip_reason")}
        )),
        
        # Step 4: Fetch prices from source
        Step.pipeline("fetch_prices", "market_data.fetch_daily_prices"),
        
        # Step 5: Validate quality
        Step.lambda_("validate_prices", validate_price_data),
        
        # Step 6: Store normalized prices
        Step.pipeline("store_prices", "market_data.store_prices"),
        
        # Step 7: Calculate derived metrics
        Step.lambda_("calc_metrics", calculate_derived_metrics),
        
        # Step 8: Update any dependent views
        Step.pipeline("refresh_views", "market_data.refresh_price_views"),
    ],
)


# ============================================================================
# Usage
# ============================================================================

def run_daily_prices(run_date: str = None):
    """Run daily price workflow."""
    from spine.orchestration import WorkflowRunner
    from datetime import date
    
    runner = WorkflowRunner()
    
    result = runner.execute(
        daily_price_workflow,
        params={
            "run_date": run_date or date.today().isoformat(),
            "exchange": "NYSE",
        },
    )
    
    if result.context.params.get("skip_processing"):
        print(f"Skipped: {result.context.params.get('skip_reason')}")
    else:
        print(f"Processed {result.context.get_output('validate_prices', 'total_records')} records")
    
    return result
```

---

## Example 2: Exchange Calendar Sync Workflow

Synchronize exchange calendar data from external sources:

```python
from spine.orchestration import Workflow, Step, StepResult, WorkflowContext
from datetime import date, timedelta


def detect_calendar_source(ctx: WorkflowContext, config: dict) -> StepResult:
    """
    Detect which calendar sources to sync.
    
    Checks for available sources and their freshness.
    """
    exchanges = ctx.params.get("exchanges", ["NYSE", "NASDAQ", "LSE", "TSE"])
    
    sources_to_sync = []
    for exchange in exchanges:
        # Would check: last sync time, source availability
        # For demo, sync all
        sources_to_sync.append({
            "exchange": exchange,
            "source": "exchange_api",  # or "tradingcalendar", "manual"
            "last_sync": None,  # Would be actual date
        })
    
    return StepResult.ok(
        output={"sources": sources_to_sync},
        context_updates={"sources_to_sync": sources_to_sync},
    )


def validate_calendar_data(ctx: WorkflowContext, config: dict) -> StepResult:
    """
    Validate synced calendar data.
    
    Checks:
    - No gaps in dates
    - Expected holidays present
    - At least 1 year of future data
    """
    exchange = ctx.params.get("current_exchange")
    year = date.today().year
    
    # Would query actual data
    # For demo, assume valid
    
    return StepResult.ok(
        output={
            "exchange": exchange,
            "valid": True,
            "coverage_years": 2,
        },
    )


def sync_single_exchange(ctx: WorkflowContext, config: dict) -> StepResult:
    """Sync a single exchange calendar."""
    exchange = ctx.params.get("current_exchange")
    
    # Would call actual sync pipeline
    # For demo, simulate
    
    return StepResult.ok(
        output={
            "exchange": exchange,
            "holidays_synced": 15,
            "early_closes_synced": 3,
        },
    )


# Per-exchange workflow (called in map)
sync_exchange_workflow = Workflow(
    name="exchange_calendar.sync_exchange",
    steps=[
        Step.lambda_("sync", sync_single_exchange),
        Step.lambda_("validate", validate_calendar_data),
    ],
)


# Master workflow with map state
calendar_sync_workflow = Workflow(
    name="exchange_calendar.sync_all",
    domain="exchange_calendar",
    description="Sync all exchange calendars in parallel",
    steps=[
        # Step 1: Detect sources
        Step.lambda_("detect_sources", detect_calendar_source),
        
        # Step 2: Fan out to sync each exchange
        Step.map("sync_all_exchanges",
            items_path="sources_to_sync",
            item_param="current_exchange",
            iterator=sync_exchange_workflow,
            max_concurrency=4,
        ),
        
        # Step 3: Aggregate results
        Step.lambda_("aggregate", lambda ctx, cfg: StepResult.ok(
            output={
                "total_exchanges": len(ctx.params.get("sources_to_sync", [])),
                "sync_results": ctx.get_output("sync_all_exchanges", "results", []),
            }
        )),
    ],
)
```

---

## Example 3: Multi-Source Price Aggregation

Aggregate prices from multiple sources with conflict resolution:

```python
from spine.orchestration import Workflow, Step, StepResult, WorkflowContext


def aggregate_sources(ctx: WorkflowContext, config: dict) -> StepResult:
    """
    Aggregate prices from multiple sources.
    
    Priority: Bloomberg > Refinitiv > Yahoo Finance
    Uses weighted average for numeric fields.
    """
    sources = ctx.params.get("price_sources", [])
    priority = config.get("source_priority", ["bloomberg", "refinitiv", "yahoo"])
    
    # Group by symbol
    by_symbol = {}
    for source in sources:
        for record in source.get("records", []):
            symbol = record["symbol"]
            if symbol not in by_symbol:
                by_symbol[symbol] = []
            by_symbol[symbol].append({
                "source": source["name"],
                "record": record,
            })
    
    # Resolve conflicts
    resolved = []
    for symbol, source_records in by_symbol.items():
        # Sort by priority
        source_records.sort(key=lambda x: priority.index(x["source"]) 
                           if x["source"] in priority else 999)
        # Take highest priority
        resolved.append(source_records[0]["record"])
    
    return StepResult.ok(
        output={
            "resolved_count": len(resolved),
            "conflict_count": sum(1 for s in by_symbol.values() if len(s) > 1),
        },
        context_updates={
            "resolved_prices": resolved,
        },
    )


multi_source_workflow = Workflow(
    name="market_data.multi_source_prices",
    steps=[
        # Fetch from each source in parallel
        Step.map("fetch_all_sources",
            items=["bloomberg", "refinitiv", "yahoo"],
            item_param="source_name",
            iterator=Workflow(
                steps=[Step.pipeline("fetch", "market_data.fetch_from_source")]
            ),
            max_concurrency=3,
        ),
        
        # Aggregate results
        Step.lambda_("aggregate", aggregate_sources,
            config={"source_priority": ["bloomberg", "refinitiv", "yahoo"]}),
        
        # Store resolved prices
        Step.pipeline("store", "market_data.store_prices"),
    ],
)
```

---

## Example 4: Historical Backfill with Partitioning

Backfill historical data with intelligent partitioning:

```python
from spine.orchestration import Workflow, Step, StepResult, WorkflowContext
from datetime import date, timedelta
import calendar


def partition_date_range(ctx: WorkflowContext, config: dict) -> StepResult:
    """
    Partition date range into monthly chunks.
    
    Enables parallel processing and checkpointing.
    """
    start = date.fromisoformat(ctx.params["start_date"])
    end = date.fromisoformat(ctx.params["end_date"])
    
    partitions = []
    current = start.replace(day=1)  # Start of month
    
    while current <= end:
        # Last day of month
        _, last_day = calendar.monthrange(current.year, current.month)
        month_end = current.replace(day=last_day)
        
        partitions.append({
            "start_date": max(current, start).isoformat(),
            "end_date": min(month_end, end).isoformat(),
            "month": current.strftime("%Y-%m"),
        })
        
        # Next month
        if current.month == 12:
            current = current.replace(year=current.year + 1, month=1)
        else:
            current = current.replace(month=current.month + 1)
    
    return StepResult.ok(
        output={"partitions": partitions, "partition_count": len(partitions)},
        context_updates={"partitions": partitions},
    )


def check_partition_status(ctx: WorkflowContext, config: dict) -> StepResult:
    """Check if partition already processed (idempotency)."""
    month = ctx.params.get("current_month")
    
    # Would query: SELECT status FROM backfill_progress WHERE partition = ?
    already_done = False  # Actual check
    
    return StepResult.ok(
        output={"already_processed": already_done},
        context_updates={"skip_partition": already_done},
    )


# Per-partition workflow
partition_workflow = Workflow(
    name="market_data.backfill_partition",
    steps=[
        Step.lambda_("check_status", check_partition_status),
        Step.choice("should_process",
            condition=lambda ctx: not ctx.params.get("skip_partition"),
            then_step="fetch",
            else_step="skip",
        ),
        Step.pipeline("fetch", "market_data.fetch_historical"),
        Step.pipeline("store", "market_data.store_prices"),
        Step.lambda_("skip", lambda ctx, cfg: StepResult.ok(
            output={"skipped": True, "reason": "already processed"}
        )),
    ],
)


# Master backfill workflow
backfill_workflow = Workflow(
    name="market_data.historical_backfill",
    domain="market_data",
    description="Historical data backfill with monthly partitions",
    steps=[
        # Partition the date range
        Step.lambda_("partition", partition_date_range),
        
        # Process each partition (can be parallelized)
        Step.map("process_partitions",
            items_path="partitions",
            item_param="current_partition",
            iterator=partition_workflow,
            max_concurrency=4,
        ),
        
        # Final validation
        Step.pipeline("validate_backfill", "market_data.validate_historical"),
    ],
)
```

---

## Example 5: Real-Time Price Update with Throttling

Handle real-time updates with rate limiting:

```python
from spine.orchestration import Workflow, Step, StepResult, WorkflowContext
from datetime import datetime


def check_rate_limit(ctx: WorkflowContext, config: dict) -> StepResult:
    """
    Check if we're within rate limits.
    
    Max 100 updates per minute per symbol.
    """
    symbol = ctx.params.get("symbol")
    window_minutes = config.get("window_minutes", 1)
    max_updates = config.get("max_updates", 100)
    
    # Would query: COUNT updates WHERE symbol = ? AND timestamp > NOW() - interval
    recent_count = 50  # Actual count from DB
    
    if recent_count >= max_updates:
        # Calculate wait time
        wait_seconds = 60 - (datetime.now().second)
        
        return StepResult.ok(
            output={"throttled": True, "wait_seconds": wait_seconds},
            context_updates={"should_wait": True, "wait_seconds": wait_seconds},
        )
    
    return StepResult.ok(
        output={"throttled": False},
        context_updates={"should_wait": False},
    )


realtime_update_workflow = Workflow(
    name="market_data.realtime_update",
    steps=[
        # Check rate limit
        Step.lambda_("check_rate", check_rate_limit,
            config={"max_updates": 100, "window_minutes": 1}),
        
        # Wait if throttled
        Step.choice("rate_check",
            condition=lambda ctx: ctx.params.get("should_wait", False),
            then_step="wait",
            else_step="process",
        ),
        
        # Wait step
        Step.wait("wait",
            duration_path="wait_seconds",
            next_step="process",
        ),
        
        # Process update
        Step.lambda_("process", lambda ctx, cfg: StepResult.ok(
            output={"processed": True, "symbol": ctx.params["symbol"]}
        )),
        
        # Store
        Step.pipeline("store", "market_data.store_tick"),
    ],
)
```

---

## Integration Pattern: Combining Domains

A workflow that combines multiple domains:

```python
from spine.orchestration import Workflow, Step


combined_daily_workflow = Workflow(
    name="combined.daily_refresh",
    description="Daily refresh combining market_data and exchange_calendar",
    steps=[
        # First sync calendar (needed for market open check)
        Step.pipeline("sync_calendar", "exchange_calendar.sync_daily"),
        
        # Then run market data (uses calendar)
        Step.pipeline("fetch_prices", "market_data.daily_prices"),
        
        # Finally, run FINRA if it's Friday (weekly data)
        Step.choice("is_friday",
            condition=lambda ctx: ctx.params.get("day_of_week") == 4,
            then_step="finra_weekly",
            else_step="complete",
        ),
        
        Step.pipeline("finra_weekly", "finra.otc_transparency.weekly_refresh"),
        
        Step.lambda_("complete", lambda ctx, cfg: StepResult.ok(
            output={"all_complete": True}
        )),
    ],
)
```
