#!/usr/bin/env python3
"""Structured Logging — Production-ready logging with structlog.

WHY STRUCTURED LOGGING
──────────────────────
Plain-text log lines are impossible to query at scale.  Structured
logging emits key-value pairs that can be indexed by ELK, Datadog,
or CloudWatch Insights.  Instead of grepping for a substring you can
write `pipeline="otc_volume" AND stage="transform" AND rejected>100`.

ARCHITECTURE
────────────
    ┌────────────────────────────────────────┐
    │  get_logger("module")                     │
    │    .info("msg", key=value, ...)            │
    └──────────────────┬─────────────────────┘
                       │
              add_context(batch_id=..., domain=...)
                       │
                       ▼
    ┌────────────────────────────────────────┐
    │  Output (JSON or console):                │
    │  {"event": "msg", "batch_id": "...",      │
    │   "domain": "finra_otc", "key": "value"}  │
    └────────────────────────────────────────┘

KEY FUNCTIONS
─────────────
    Function           Purpose
    ────────────────── ───────────────────────────────────
    configure_logging  Set level, format (JSON vs console)
    get_logger(name)   Create a bound logger for a module
    add_context(k=v)   Inject fields into all subsequent logs
    clear_context()    Reset thread-local context
    get_context()      Inspect current context dict

BEST PRACTICES
──────────────
• Use json_output=True in production for machine-parseable logs.
• Bind batch_id and domain early in the pipeline function.
• Log stage transitions to track pipeline progress.
• Include record counts and durations in every stage log.
• Call clear_context() when switching to a new request/batch.

Run: python examples/06_observability/01_structured_logging.py

See Also:
    02_metrics — Prometheus-style counters, gauges, histograms
    03_context_binding — deep-dive on context scoping
"""
from spine.observability import (
    get_logger,
    configure_logging,
    LogLevel,
    add_context,
    clear_context,
    get_context,
)


def main():
    print("=" * 60)
    print("Structured Logging Examples")
    print("=" * 60)
    
    # === 1. Configure logging ===
    print("\n[1] Configure Logging")
    
    configure_logging(
        level="INFO",
        json_output=False,  # Human-readable for demo
    )
    print("  Logging configured (INFO level, console output)")
    
    # === 2. Get logger ===
    print("\n[2] Get Logger")
    
    log = get_logger("my_module")
    print("  Logger created for 'my_module'")
    
    # === 3. Basic logging ===
    print("\n[3] Basic Log Messages")
    
    log.info("Starting process")
    log.warning("Something needs attention")
    
    # === 4. Structured fields ===
    print("\n[4] Structured Fields")
    
    log.info(
        "Processing data",
        symbol="AAPL",
        volume=1000000,
        price=150.50,
    )
    
    log.info(
        "Batch complete",
        records_processed=500,
        duration_ms=1234,
        success=True,
    )
    
    # === 5. Context binding ===
    print("\n[5] Context Binding")
    
    # Bind context for all subsequent logs
    add_context(
        batch_id="batch-2024-001",
        domain="finra_otc",
    )
    
    log.info("Step 1: Fetching data")
    log.info("Step 2: Transforming data")
    log.info("Step 3: Loading data")
    
    # Get current context
    ctx = get_context()
    print(f"  Current context: {ctx}")
    
    # Clear context
    clear_context()
    log.info("Context cleared")
    
    # === 6. Error logging ===
    print("\n[6] Error Logging")
    
    try:
        raise ValueError("Something went wrong")
    except Exception as e:
        log.error(
            "Operation failed",
            error=str(e),
            error_type=type(e).__name__,
        )
    
    # === 7. Real-world: Pipeline logging ===
    print("\n[7] Real-world: Pipeline Logging")
    
    def run_pipeline(name: str, week: str):
        """Pipeline with structured logging."""
        log = get_logger("pipeline")
        
        add_context(pipeline=name, week=week)
        
        log.info("Pipeline started")
        
        # Extract stage
        add_context(stage="extract")
        log.info("Fetching data from source")
        records = 1000
        log.info("Extract complete", records=records)
        
        # Transform stage
        add_context(stage="transform")
        log.info("Applying transformations")
        valid = 980
        rejected = 20
        log.info("Transform complete", valid=valid, rejected=rejected)
        
        # Load stage
        add_context(stage="load")
        log.info("Loading to database")
        log.info("Load complete", inserted=valid)
        
        log.info("Pipeline complete", total_records=records, success_rate=valid/records)
        
        clear_context()
    
    run_pipeline("otc_volume", "2024-01-19")
    
    print("\n" + "=" * 60)
    print("[OK] Structured Logging Complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
