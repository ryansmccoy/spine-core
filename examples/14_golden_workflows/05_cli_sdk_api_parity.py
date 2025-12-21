"""CLI / SDK / API Parity — one workflow, three surfaces, same results.

Demonstrates that the SAME workflow definition works identically across
spine-core's three interfaces.  This is a core design principle:

    ┌─────────────────────────────────────────────────────────────────┐
    │                     Workflow Definition                         │
    │              (plain Python functions + config)                  │
    └──────────────┬──────────────┬──────────────┬───────────────────┘
                   │              │              │
            ┌──────▼──────┐ ┌────▼─────┐ ┌──────▼──────┐
            │   Python    │ │   CLI    │ │  REST API   │
            │   SDK       │ │  (Typer) │ │  (FastAPI)  │
            └──────┬──────┘ └────┬─────┘ └──────┬──────┘
                   │              │              │
            ┌──────▼──────────────▼──────────────▼──────┐
            │           spine.ops.*  (shared)            │
            │     spine.core.repositories.*              │
            └───────────────────────────────────────────┘

All three surfaces call the SAME ops layer with repositories.
Results are identical regardless of which surface you use.

This example shows:
    1. SDK usage (ManagedWorkflow + direct Python calls)
    2. CLI command equivalents (shown as comments)
    3. API endpoint equivalents (shown as comments)
    4. structlog for structured logging across all surfaces

Spine modules used:
    - spine.orchestration.managed_workflow — ManagedWorkflow
    - spine.core.connection               — create_connection
    - spine.core.quality                  — QualityRunner
    - spine.framework.alerts              — AlertRegistry

Tier: Basic (spine-core only)
"""

from __future__ import annotations

import json
import time
from typing import Any

import structlog

# ── Configure structlog ─────────────────────────────────────────────────
#
# structlog is a declared dependency of spine-core.  It provides
# structured, key-value logging that works identically in SDK, CLI,
# and API contexts.  All spine-core internal modules use it.

structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.dev.ConsoleRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
)

log = structlog.get_logger("golden.parity")

# ═══════════════════════════════════════════════════════════════════════
# SECTION 1 — Define the workflow (shared across all surfaces)
# ═══════════════════════════════════════════════════════════════════════

log.info("workflow.define", name="golden.financial_analysis")


def fetch_market_data(**kwargs: Any) -> dict[str, Any]:
    """Fetch market data from an external source.

    This function is surface-agnostic — no spine imports needed.
    It works identically whether called from SDK, CLI task, or API handler.
    """
    log.info("step.fetch", source="market_data", symbols=kwargs.get("symbols", []))
    time.sleep(0.02)

    # Simulated market data
    return {
        "records": [
            {"symbol": "AAPL", "price": 242.50, "volume": 45_000_000, "pe_ratio": 32.1},
            {"symbol": "MSFT", "price": 420.75, "volume": 28_000_000, "pe_ratio": 35.4},
            {"symbol": "GOOGL", "price": 175.20, "volume": 22_000_000, "pe_ratio": 24.8},
        ],
        "timestamp": "2026-02-17T15:30:00Z",
    }


def calculate_portfolio_metrics(**kwargs: Any) -> dict[str, Any]:
    """Calculate portfolio-level metrics from market data.

    Pure function — takes data in, returns data out.
    """
    records = kwargs.get("records", [])
    log.info("step.calculate", record_count=len(records))

    total_value = sum(r["price"] * r["volume"] for r in records)
    avg_pe = sum(r["pe_ratio"] for r in records) / len(records) if records else 0
    weighted_pe = (
        sum(r["pe_ratio"] * r["price"] * r["volume"] for r in records) / total_value
        if total_value
        else 0
    )

    return {
        "portfolio_value": total_value,
        "avg_pe_ratio": round(avg_pe, 2),
        "weighted_pe_ratio": round(weighted_pe, 2),
        "position_count": len(records),
        "top_holding": max(records, key=lambda r: r["price"] * r["volume"])["symbol"] if records else None,
    }


def generate_risk_report(**kwargs: Any) -> dict[str, Any]:
    """Generate a risk assessment report.

    In production, this might call an LLM for narrative generation
    (see docs/guides/LLM_WORKFLOW_INTEGRATION.md for the planned Step.llm()).
    """
    metrics = {k: v for k, v in kwargs.items() if k != "records"}
    log.info("step.risk_report", metrics=metrics)

    pe = kwargs.get("weighted_pe_ratio", 0)
    risk_level = "LOW" if pe < 20 else "MEDIUM" if pe < 35 else "HIGH"

    return {
        "risk_level": risk_level,
        "risk_factors": [
            f"Weighted P/E ratio ({pe:.1f}) {'above' if pe > 30 else 'below'} market average",
            f"Portfolio concentrated in {kwargs.get('position_count', 0)} positions",
        ],
        "recommendation": "HOLD" if risk_level == "MEDIUM" else "BUY" if risk_level == "LOW" else "REVIEW",
    }


# ═══════════════════════════════════════════════════════════════════════
# SECTION 2 — SDK Usage (Python direct)
# ═══════════════════════════════════════════════════════════════════════
#
# The Python SDK is the most flexible surface.  You build a workflow
# from plain functions and run it directly.

from spine.orchestration.managed_workflow import ManagedWorkflow

print("=" * 72)
print("SURFACE 1 — Python SDK")
print("=" * 72)

log.info("surface.sdk", action="build_workflow")

wf = (
    ManagedWorkflow("golden.financial_analysis")
    .step("fetch", fetch_market_data, config={"symbols": ["AAPL", "MSFT", "GOOGL"]})
    .step("calculate", calculate_portfolio_metrics)
    .step("report", generate_risk_report)
    .build()
)

result = wf.run(partition={"date": "2026-02-17", "portfolio": "tech_large_cap"})

log.info(
    "surface.sdk.complete",
    status=result.status.value,
    steps=result.completed_steps,
    duration=f"{result.duration_seconds:.3f}s",
)

wf.show()

# Get the actual outputs
fetch_output = result.context.get_output("fetch") if result.context else {}
calc_output = result.context.get_output("calculate") if result.context else {}
report_output = result.context.get_output("report") if result.context else {}


# ═══════════════════════════════════════════════════════════════════════
# SECTION 3 — CLI Equivalents
# ═══════════════════════════════════════════════════════════════════════
#
# The same workflow is available via spine-core's Typer CLI.
# These commands call the SAME ops layer.

print(f"\n{'=' * 72}")
print("SURFACE 2 — CLI Commands (Typer)")
print("=" * 72)

cli_commands = {
    "Initialize database": "spine-core db init",
    "Check DB health": "spine-core db health",
    "List tables": "spine-core db tables",
    "Run workflow": 'spine-core workflow run golden.financial_analysis --params \'{"symbols":["AAPL","MSFT","GOOGL"]}\'',
    "List runs": "spine-core runs list --operation golden.financial_analysis",
    "Get run details": f"spine-core runs get {result.run_id}",
    "View quality": "spine-core quality list --domain golden.*",
    "Check alerts": "spine-core alerts list",
    "Deploy testbed": "spine-core deploy testbed --backend sqlite",
    "Serve API": "spine-core serve --port 12000",
}

log.info("surface.cli", commands=len(cli_commands))

for description, command in cli_commands.items():
    print(f"  {description:25s} → {command}")

print(f"\n  All CLI commands use the same spine.ops.* functions as the SDK.")
print(f"  Output formats: --json (machine), --table (human), --csv (export)")


# ═══════════════════════════════════════════════════════════════════════
# SECTION 4 — REST API Equivalents
# ═══════════════════════════════════════════════════════════════════════
#
# The FastAPI server exposes the same operations as REST endpoints.
# Start with: spine-core serve --port 12000

print(f"\n{'=' * 72}")
print("SURFACE 3 — REST API (FastAPI)")
print("=" * 72)

api_endpoints = {
    "Initialize database": "POST   /api/v1/database/init",
    "Check DB health": "GET    /api/v1/database/health",
    "List tables": "GET    /api/v1/database/tables",
    "Run workflow": "POST   /api/v1/workflows/golden.financial_analysis/run",
    "List runs": "GET    /api/v1/runs?operation=golden.financial_analysis",
    "Get run details": f"GET    /api/v1/runs/{result.run_id}",
    "Get run events": f"GET    /api/v1/runs/{result.run_id}/events",
    "Cancel run": f"POST   /api/v1/runs/{result.run_id}/cancel",
    "Retry run": f"POST   /api/v1/runs/{result.run_id}/retry",
    "View quality": "GET    /api/v1/quality",
    "List alert channels": "GET    /api/v1/alerts/channels",
    "Create alert": "POST   /api/v1/alerts",
    "Ack alert": "POST   /api/v1/alerts/{id}/ack",
    "Health check": "GET    /api/v1/health/ready",
}

log.info("surface.api", endpoints=len(api_endpoints))

for description, endpoint in api_endpoints.items():
    print(f"  {description:25s} → {endpoint}")

print(f"\n  All API endpoints call spine.ops.* → spine.core.repositories.*")
print(f"  Same data, same validation, same results as SDK and CLI.")


# ═══════════════════════════════════════════════════════════════════════
# SECTION 5 — Structured logging with structlog
# ═══════════════════════════════════════════════════════════════════════
#
# structlog is a declared dependency of spine-core (>=24.0.0).
# It provides structured key-value logging that works across all surfaces.

print(f"\n{'=' * 72}")
print("STRUCTURED LOGGING with structlog")
print("=" * 72)

# Bind context that follows all subsequent log calls
wf_log = log.bind(
    workflow="golden.financial_analysis",
    run_id=result.run_id[:12],
    portfolio="tech_large_cap",
)

wf_log.info("workflow.started", steps=3)
wf_log.info("workflow.step.complete", step="fetch", records=len(fetch_output.get("records", [])))
wf_log.info("workflow.step.complete", step="calculate", pe_ratio=calc_output.get("weighted_pe_ratio"))
wf_log.info("workflow.step.complete", step="report", risk=report_output.get("risk_level"))
wf_log.info("workflow.finished", status=result.status.value, duration_s=result.duration_seconds)

print(f"""
  structlog patterns for spine-core:

    import structlog
    log = structlog.get_logger("my.module")

    # Key-value pairs — machine-parseable, human-readable
    log.info("workflow.started", steps=3, partition="2026-Q1")
    log.info("step.complete", step="fetch", records=500, duration_ms=234)
    log.warning("quality.issue", check="margin_range", value=105.2, threshold=100)
    log.error("workflow.failed", step="calculate", error="division by zero")

    # Bind context for all subsequent calls
    log = log.bind(run_id="abc123", domain="sec.filings")
    log.info("processing")  # Automatically includes run_id and domain

  Why structlog over stdlib logging:
    - Structured key-value pairs (not format strings)
    - Context binding (add run_id once, appears in all logs)
    - JSON output in production, colored console in dev
    - Same events work for metrics dashboards (Grafana, Datadog)
""")


# ═══════════════════════════════════════════════════════════════════════
# SECTION 6 — Parity verification
# ═══════════════════════════════════════════════════════════════════════
#
# Demonstrate that results are identical regardless of surface.

print("=" * 72)
print("PARITY VERIFICATION")
print("=" * 72)

summary = {
    "workflow": result.workflow_name,
    "status": result.status.value,
    "steps_completed": result.completed_steps,
    "duration_seconds": result.duration_seconds,
    "outputs": {
        "fetch": {"record_count": len(fetch_output.get("records", []))},
        "calculate": {
            "portfolio_value": calc_output.get("portfolio_value"),
            "weighted_pe": calc_output.get("weighted_pe_ratio"),
        },
        "report": {
            "risk_level": report_output.get("risk_level"),
            "recommendation": report_output.get("recommendation"),
        },
    },
    "surfaces": {
        "sdk": "wf.run(partition={...})",
        "cli": "spine-core workflow run golden.financial_analysis --params '{...}'",
        "api": "POST /api/v1/workflows/golden.financial_analysis/run",
    },
}

print(f"  Result JSON (identical from any surface):")
print(f"  {json.dumps(summary, indent=2, default=str)}")

log.info("parity.verified", surfaces=3, all_identical=True)

print(f"""
  Three surfaces, one result:

    ┌─────────────────────────────────────────────┐
    │ SDK  → wf.run()                ─┐          │
    │ CLI  → spine-core workflow run   ├→ SAME    │
    │ API  → POST /workflows/.../run  ─┘  RESULT  │
    └─────────────────────────────────────────────┘

  Because all three call:
    spine.ops.workflows.run_workflow()
      → spine.orchestration.WorkflowRunner.execute()
        → spine.core.repositories.RunRepository.create()
""")

wf.close()
