#!/usr/bin/env python3
"""FastAPI Integration — Building REST APIs for Pipeline Orchestration.

================================================================================
WHY FASTAPI INTEGRATION?
================================================================================

Production data platforms need a REST API to:

    - Submit pipeline runs from external systems (Airflow, cron, webhooks)
    - Query run status and results (dashboards, monitoring)
    - Manage pipeline configuration (feature flags, schedules)

Spine-core's execution layer integrates directly with FastAPI::

    @app.post("/api/v1/runs", status_code=202)
    async def submit_run(spec: WorkSpec):
        run = await dispatcher.submit(spec)
        return {"run_id": run.run_id, "status": run.status}

    @app.get("/api/v1/runs/{run_id}")
    async def get_run(run_id: str):
        return ledger.get(run_id)


================================================================================
ARCHITECTURE: API → DISPATCHER → EXECUTOR
================================================================================

::

    ┌──────────┐  POST /runs   ┌──────────┐           ┌──────────────┐
    │  Client  │──────────────►│ FastAPI  │──────────►│  Dispatcher  │
    │ (curl/   │               │  Router  │  submit() │              │
    │  UI/     │               └──────────┘           └──────┬───────┘
    │  Airflow)│                                             │
    └──────────┘               ┌──────────┐           ┌──────┴───────┐
         ▲                     │ FastAPI  │◄──────────│   Executor   │
         │   GET /runs/{id}    │  Router  │  result   │ (Memory/     │
         └─────────────────────│          │           │  Local/      │
              202 Accepted     └──────────┘           │  Celery)     │
                                                      └──────────────┘

    HTTP Status Codes:
    ┌─────┬──────────────────────────────────────────────────────────────┐
    │ 202 │ Accepted — Run submitted, processing asynchronously          │
    │ 200 │ OK — Run status/result returned                              │
    │ 404 │ Not Found — Run ID doesn't exist                             │
    │ 422 │ Validation Error — Invalid WorkSpec                          │
    └─────┴──────────────────────────────────────────────────────────────┘


================================================================================
EXAMPLE USAGE
================================================================================

Run this example:
    pip install fastapi uvicorn
    python examples/02_execution/08_fastapi_integration.py
    # Open http://localhost:8000/docs for Swagger UI

See Also:
    - :mod:`spine.api` — Production API application
    - :mod:`spine.execution` — Dispatcher, WorkSpec
    - ``examples/02_execution/03_dispatcher_basics.py`` — Dispatcher without API
"""
import asyncio
import sys

try:
    import uvicorn
except ImportError:
    print("SKIP: uvicorn not installed (pip install uvicorn)")
    sys.exit(0)

from datetime import datetime, timezone
from typing import Optional

try:
    from fastapi import FastAPI, HTTPException, Query
    from pydantic import BaseModel, Field
except ImportError:
    print("FastAPI not installed. Run: pip install fastapi uvicorn")
    raise

from spine.execution import (
    EventDispatcher,
    WorkSpec,
    register_task,
    register_pipeline,
    HandlerRegistry,
    RunStatus,
    create_runs_router,
)
from spine.execution.executors import MemoryExecutor


# =============================================================================
# DOMAIN-SPECIFIC HANDLERS (real use cases from our ecosystem)
# =============================================================================

registry = HandlerRegistry()


# --- Entity Processing (like entityspine) ---

@register_task("resolve_entity", registry=registry, description="Resolve entity from identifiers")
async def resolve_entity(params: dict) -> dict:
    """Resolve an entity from various identifiers (CIK, ticker, CUSIP, etc.)."""
    await asyncio.sleep(0.1)  # Simulate lookup
    
    identifier_type = params.get("type", "ticker")
    identifier_value = params.get("value")
    
    # Mock entity resolution
    mock_entities = {
        "AAPL": {"cik": "0000320193", "name": "Apple Inc.", "sector": "Technology"},
        "MSFT": {"cik": "0000789019", "name": "Microsoft Corporation", "sector": "Technology"},
        "TSLA": {"cik": "0001318605", "name": "Tesla, Inc.", "sector": "Automotive"},
    }
    
    entity = mock_entities.get(identifier_value)
    if not entity:
        return {"found": False, "identifier": identifier_value}
    
    return {
        "found": True,
        "identifier": identifier_value,
        "entity": entity,
        "resolved_at": datetime.now(timezone.utc).isoformat(),
    }


@register_task("enrich_entity", registry=registry, description="Enrich entity with additional data")
async def enrich_entity(params: dict) -> dict:
    """Enrich entity with data from multiple sources."""
    await asyncio.sleep(0.15)
    
    cik = params.get("cik")
    sources = params.get("sources", ["sec", "finra"])
    
    enrichments = {
        "sec": {"filings_count": 1234, "last_filing": "2026-01-10"},
        "finra": {"otc_volume": 5678900, "tier": "NMS_TIER_1"},
        "market": {"market_cap": "2.5T", "pe_ratio": 28.5},
    }
    
    result = {"cik": cik, "enrichments": {}}
    for source in sources:
        if source in enrichments:
            result["enrichments"][source] = enrichments[source]
    
    return result


# --- Feed Processing (like feedspine) ---

@register_task("fetch_feed", registry=registry, description="Fetch records from a feed source")
async def fetch_feed(params: dict) -> dict:
    """Generic feed fetcher."""
    await asyncio.sleep(0.2)
    
    feed_name = params.get("feed_name")
    since = params.get("since")
    
    # Mock feed data
    records = [
        {"id": f"{feed_name}-001", "timestamp": "2026-01-15T10:00:00Z"},
        {"id": f"{feed_name}-002", "timestamp": "2026-01-15T10:01:00Z"},
        {"id": f"{feed_name}-003", "timestamp": "2026-01-15T10:02:00Z"},
    ]
    
    return {
        "feed_name": feed_name,
        "record_count": len(records),
        "records": records,
    }


@register_task("validate_records", registry=registry, description="Validate feed records")
async def validate_records(params: dict) -> dict:
    """Validate records against schema."""
    records = params.get("records", [])
    
    valid = []
    invalid = []
    
    for record in records:
        if "id" in record and "timestamp" in record:
            valid.append(record)
        else:
            invalid.append({"record": record, "error": "Missing required fields"})
    
    return {
        "valid_count": len(valid),
        "invalid_count": len(invalid),
        "valid_records": valid,
        "invalid_records": invalid,
    }


# --- Alerting (like monitoring) ---

@register_task("check_alert_rule", registry=registry, description="Check an alert rule condition")
async def check_alert_rule(params: dict) -> dict:
    """Evaluate an alert rule against current metrics."""
    rule_name = params.get("rule_name")
    threshold = params.get("threshold", 100)
    
    # Mock metric value
    import random
    current_value = random.randint(50, 150)
    
    triggered = current_value > threshold
    
    return {
        "rule_name": rule_name,
        "threshold": threshold,
        "current_value": current_value,
        "triggered": triggered,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


@register_task("send_alert", registry=registry, description="Send an alert notification")
async def send_alert(params: dict) -> dict:
    """Send alert via configured channels."""
    await asyncio.sleep(0.05)
    
    channel = params.get("channel", "slack")
    message = params.get("message")
    severity = params.get("severity", "warning")
    
    print(f"  🚨 Alert ({severity}): {message} -> {channel}")
    
    return {
        "sent": True,
        "channel": channel,
        "severity": severity,
        "sent_at": datetime.now(timezone.utc).isoformat(),
    }


# --- Pipelines ---

@register_pipeline("daily_entity_refresh", registry=registry, description="Refresh entity data daily")
async def daily_entity_refresh(params: dict) -> dict:
    """Daily pipeline to refresh entity enrichments."""
    entities = params.get("entities", ["AAPL", "MSFT", "TSLA"])
    
    results = []
    for entity in entities:
        resolve_result = await resolve_entity({"type": "ticker", "value": entity})
        if resolve_result.get("found"):
            enrich_result = await enrich_entity({
                "cik": resolve_result["entity"]["cik"],
                "sources": ["sec", "finra", "market"],
            })
            results.append({
                "entity": entity,
                "enrichments": enrich_result["enrichments"],
            })
    
    return {
        "refreshed_count": len(results),
        "entities": results,
    }


@register_pipeline("alert_check_cycle", registry=registry, description="Check all alert rules")
async def alert_check_cycle(params: dict) -> dict:
    """Check all configured alert rules."""
    rules = params.get("rules", [
        {"name": "high_volume", "threshold": 100},
        {"name": "error_rate", "threshold": 5},
    ])
    
    triggered_alerts = []
    
    for rule in rules:
        result = await check_alert_rule({
            "rule_name": rule["name"],
            "threshold": rule["threshold"],
        })
        
        if result["triggered"]:
            await send_alert({
                "channel": "slack",
                "message": f"Alert: {rule['name']} exceeded threshold",
                "severity": "warning",
            })
            triggered_alerts.append(result)
    
    return {
        "rules_checked": len(rules),
        "alerts_triggered": len(triggered_alerts),
        "triggered_alerts": triggered_alerts,
    }


# =============================================================================
# FASTAPI APPLICATION
# =============================================================================

def create_app() -> FastAPI:
    """Create FastAPI application with spine.execution integration."""
    
    # Create executor and dispatcher
    executor = MemoryExecutor(handlers=registry.to_executor_handlers())
    dispatcher = EventDispatcher(executor=executor, registry=registry)
    
    # Create FastAPI app
    app = FastAPI(
        title="Spine Execution API",
        description="Unified execution API for tasks, pipelines, and workflows",
        version="1.0.0",
    )
    
    # Include the unified /runs router
    runs_router = create_runs_router(dispatcher, prefix="/api/v1/runs", tags=["runs"])
    app.include_router(runs_router)
    
    # --- Custom endpoints ---
    
    @app.get("/")
    async def root():
        return {
            "name": "Spine Execution API",
            "version": "1.0.0",
            "docs": "/docs",
            "endpoints": {
                "runs": "/api/v1/runs",
                "handlers": "/api/v1/handlers",
            }
        }
    
    @app.get("/api/v1/handlers", tags=["meta"])
    async def list_handlers():
        """List all registered handlers with metadata."""
        return {
            "handlers": registry.list_with_metadata(),
            "counts": {
                "tasks": len(registry.list_handlers(kind="task")),
                "pipelines": len(registry.list_handlers(kind="pipeline")),
            }
        }
    
    @app.get("/health", tags=["meta"])
    async def health():
        """Health check endpoint."""
        return {
            "status": "healthy",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    
    return app


# =============================================================================
# MAIN
# =============================================================================

def main():
    """Run the FastAPI server or demo mode."""
    print("\n" + "=" * 60)
    print("SPINE EXECUTION - FASTAPI INTEGRATION EXAMPLE")
    print("=" * 60)
    print(f"\nRegistered handlers:")
    for kind, name in registry.list_handlers():
        print(f"  - {kind}:{name}")

    app = create_app()

    if "--serve" in sys.argv:
        print(f"\nStarting server at http://localhost:8000")
        print(f"Swagger UI: http://localhost:8000/docs")
        print("=" * 60 + "\n")
        uvicorn.run(app, host="0.0.0.0", port=8000)
    else:
        # Demo mode: verify app creation without blocking
        print(f"\nApp created with {len(app.routes)} routes")
        print("Run with --serve to start the HTTP server")
        print("=" * 60)
        print("\n✓ FastAPI integration example validated successfully")


if __name__ == "__main__":
    main()
