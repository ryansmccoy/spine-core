"""Golden Path Workflow — all 7 phases in one end-to-end run.

Demonstrates the complete "golden path" pattern: initialize everything from
scratch, pull data, process it, verify quality, output a summary, and send
an alert — all in a single ManagedWorkflow that persists every step.

Phases covered:
    1. Initialize database schema (create_connection + init_schema)
    2. Verify tables exist (table_counts, health check)
    3. Pull external data (simulated DataSource)
    4. Process / aggregate / calculate (workflow steps)
    5. Quality gates (QualityRunner + has_failures)
    6. Output summary JSON (WorkflowResult.to_dict)
    7. Alert on completion (AlertRegistry + send_alert)

The same workflow runs identically whether you:
    - Call it from Python (SDK)
    - Invoke it via CLI (spine-core workflow run golden.sec_workflow)
    - POST to the API (/api/v1/workflows/golden.sec_workflow/run)

Spine modules used:
    - spine.core.connection         — create_connection()
    - spine.core.quality            — QualityRunner, QualityCheck
    - spine.core.schema             — CORE_TABLES, create_tables()
    - spine.orchestration           — ManagedWorkflow, WorkflowResult
    - spine.framework.alerts        — AlertRegistry, send_alert, Alert
    - spine.observability.metrics   — Counter, Gauge

Tier: Basic (spine-core only, no Docker required)
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any

# ── 1. Database initialization ───────────────────────────────────────────
#
# create_connection() is the single entry point for all DB access.
# Pass init_schema=True to auto-create core tables on first run.

from spine.core.connection import create_connection

conn, info = create_connection(init_schema=True)  # in-memory SQLite

print("=" * 72)
print("PHASE 1 — Database Initialization")
print("=" * 72)
print(f"  Backend   : {info.backend}")
print(f"  Persistent: {info.persistent}")
print(f"  URL       : {info.url}")


# ── 2. Verify tables exist ──────────────────────────────────────────────
#
# After init, verify the schema was created correctly.
# In production, this catches Docker startup races or missing migrations.

print("\n" + "=" * 72)
print("PHASE 2 — Table Verification")
print("=" * 72)

cursor = conn.execute(
    "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'core_%' ORDER BY name"
)
tables = [row[0] for row in cursor.fetchall()]

print(f"  Core tables created: {len(tables)}")
for t in tables:
    count_row = conn.execute(f"SELECT COUNT(*) FROM [{t}]").fetchone()
    print(f"    {t}: {count_row[0]} rows")

assert len(tables) >= 5, f"Expected 5+ core tables, got {len(tables)}"
print("  ✓ Schema verified — all core tables present")


# ── 3. Define workflow step functions ────────────────────────────────────
#
# These are plain Python functions — no spine imports needed.
# ManagedWorkflow wraps them with persistence, tracking, and retry.


def fetch_sec_filings(**kwargs: Any) -> dict[str, Any]:
    """Simulate pulling SEC EDGAR filing data.

    In production, this would call the SEC EDGAR API or read from S3.
    The function returns raw data that downstream steps will process.
    """
    cik = kwargs.get("cik", "0000320193")  # Apple Inc.
    filing_type = kwargs.get("filing_type", "10-K")

    # Simulated external data pull
    filings = [
        {
            "accession": "0000320193-24-000123",
            "cik": cik,
            "form_type": filing_type,
            "filed_date": "2024-10-31",
            "period_of_report": "2024-09-28",
            "revenue": 391_035_000_000,
            "net_income": 93_736_000_000,
            "total_assets": 364_980_000_000,
            "total_liabilities": 308_030_000_000,
        },
        {
            "accession": "0000320193-23-000106",
            "cik": cik,
            "form_type": filing_type,
            "filed_date": "2023-11-02",
            "period_of_report": "2023-09-30",
            "revenue": 383_285_000_000,
            "net_income": 96_995_000_000,
            "total_assets": 352_583_000_000,
            "total_liabilities": 290_437_000_000,
        },
    ]

    time.sleep(0.05)  # Simulate network latency
    return {"filings": filings, "source": "SEC EDGAR", "fetched_at": datetime.now(timezone.utc).isoformat()}


def process_filings(**kwargs: Any) -> dict[str, Any]:
    """Transform raw filings into analytical metrics.

    Calculates derived metrics: profit margin, debt-to-equity,
    asset turnover, year-over-year growth rates.
    """
    filings = kwargs.get("filings", [])

    processed = []
    for f in filings:
        equity = f["total_assets"] - f["total_liabilities"]
        record = {
            "accession": f["accession"],
            "period": f["period_of_report"],
            "revenue": f["revenue"],
            "net_income": f["net_income"],
            "profit_margin_pct": round(f["net_income"] / f["revenue"] * 100, 2),
            "debt_to_equity": round(f["total_liabilities"] / equity, 2) if equity else None,
            "asset_turnover": round(f["revenue"] / f["total_assets"], 2),
        }
        processed.append(record)

    return {"records": processed, "record_count": len(processed)}


def aggregate_metrics(**kwargs: Any) -> dict[str, Any]:
    """Aggregate processed records into summary statistics.

    Computes averages, trends, and flags outliers — the kind of
    calculations that should run AFTER quality gates on individual records.
    """
    records = kwargs.get("records", [])

    if not records:
        return {"error": "no records to aggregate"}

    avg_margin = sum(r["profit_margin_pct"] for r in records) / len(records)
    avg_debt_equity = sum(r["debt_to_equity"] for r in records if r["debt_to_equity"]) / len(records)

    # Year-over-year revenue growth
    if len(records) >= 2:
        yoy_growth = (records[0]["revenue"] - records[1]["revenue"]) / records[1]["revenue"] * 100
    else:
        yoy_growth = None

    return {
        "summary": {
            "avg_profit_margin_pct": round(avg_margin, 2),
            "avg_debt_to_equity": round(avg_debt_equity, 2),
            "yoy_revenue_growth_pct": round(yoy_growth, 2) if yoy_growth else None,
            "filing_count": len(records),
            "periods": [r["period"] for r in records],
        },
    }


# ── 4. Build and run the workflow ────────────────────────────────────────
#
# ManagedWorkflow is the primary integration point:
#   - Wraps plain functions into tracked steps
#   - Handles DB connection, schema init, persistence
#   - Provides .show(), .history(), .table_counts()

from spine.orchestration.managed_workflow import ManagedWorkflow

print("\n" + "=" * 72)
print("PHASE 3+4 — Data Ingestion + Processing")
print("=" * 72)

wf = (
    ManagedWorkflow("golden.sec_workflow")
    .step("fetch", fetch_sec_filings, config={"cik": "0000320193", "filing_type": "10-K"})
    .step("process", process_filings)
    .step("aggregate", aggregate_metrics)
    .build()
)

# Run with partition key for idempotency
result = wf.run(partition={"cik": "0000320193", "period": "2024-Q4"})

print(f"  Workflow : {result.workflow_name}")
print(f"  Status   : {result.status.value}")
print(f"  Duration : {result.duration_seconds:.3f}s")
print(f"  Steps    : {result.completed_steps}")
wf.show()


# ── 5. Quality gates ────────────────────────────────────────────────────
#
# QualityRunner executes checks and records results.
# has_failures() is the quality gate — if it returns True, stop processing.

from spine.core.quality import (
    QualityCategory,
    QualityCheck,
    QualityResult,
    QualityRunner,
    QualityStatus,
)

print("\n" + "=" * 72)
print("PHASE 5 — Quality Gates")
print("=" * 72)

# Get the aggregated summary from the workflow
summary_output = result.context.get_output("aggregate") if result.context else {}
summary = summary_output.get("summary", {}) if summary_output else {}


def check_profit_margin(ctx: dict) -> QualityResult:
    """Verify profit margin is within expected range (10-50%)."""
    margin = ctx.get("avg_profit_margin_pct", 0)
    if 10 <= margin <= 50:
        return QualityResult(QualityStatus.PASS, f"Margin {margin}% within range", margin, "10-50%")
    elif 5 <= margin < 10:
        return QualityResult(QualityStatus.WARN, f"Margin {margin}% is low", margin, "10-50%")
    return QualityResult(QualityStatus.FAIL, f"Margin {margin}% out of range", margin, "10-50%")


def check_filing_count(ctx: dict) -> QualityResult:
    """Verify we have enough filings for trend analysis."""
    count = ctx.get("filing_count", 0)
    if count >= 2:
        return QualityResult(QualityStatus.PASS, f"{count} filings sufficient", count, ">=2")
    return QualityResult(QualityStatus.FAIL, f"Only {count} filing(s)", count, ">=2")


def check_debt_ratio(ctx: dict) -> QualityResult:
    """Flag dangerous debt-to-equity ratios (>5.0)."""
    ratio = ctx.get("avg_debt_to_equity", 0)
    if ratio <= 3.0:
        return QualityResult(QualityStatus.PASS, f"D/E ratio {ratio} healthy", ratio, "<=3.0")
    elif ratio <= 5.0:
        return QualityResult(QualityStatus.WARN, f"D/E ratio {ratio} elevated", ratio, "<=3.0")
    return QualityResult(QualityStatus.FAIL, f"D/E ratio {ratio} dangerous", ratio, "<=3.0")


# Use the workflow's own connection for quality recording
q_conn, q_info = create_connection(init_schema=True)
quality = QualityRunner(q_conn, domain="sec.filings", execution_id=result.run_id)
quality.add(QualityCheck("profit_margin", QualityCategory.BUSINESS_RULE, check_profit_margin))
quality.add(QualityCheck("filing_count", QualityCategory.COMPLETENESS, check_filing_count))
quality.add(QualityCheck("debt_ratio", QualityCategory.INTEGRITY, check_debt_ratio))

q_results = quality.run_all(summary)

for name, status in q_results.items():
    icon = "✓" if status == QualityStatus.PASS else "⚠" if status == QualityStatus.WARN else "✗"
    print(f"  [{icon}] {name}: {status.value}")

if quality.has_failures():
    print("\n  ✗ QUALITY GATE FAILED — workflow halted")
    print(f"    Failed checks: {quality.failures()}")
else:
    print("\n  ✓ All quality checks passed — proceeding to output")


# ── 6. Summary JSON output ──────────────────────────────────────────────
#
# WorkflowResult.to_dict() provides the full workflow result as JSON.
# Combined with quality check results, this is the workflow artifact.

print("\n" + "=" * 72)
print("PHASE 6 — Summary JSON Output")
print("=" * 72)

wf_summary = {
    "workflow": result.to_dict(),
    "quality": {name: status.value for name, status in q_results.items()},
    "quality_gate": "PASSED" if not quality.has_failures() else "FAILED",
    "analytics": summary,
    "produced_at": datetime.now(timezone.utc).isoformat(),
}

# In production: write to S3, Elasticsearch, or spine's own manifest
summary_json = json.dumps(wf_summary, indent=2, default=str)
print(f"  Summary JSON ({len(summary_json)} bytes):")
print(f"  {json.dumps({k: type(v).__name__ for k, v in wf_summary.items()}, indent=4)}")

# Show the analytics section
print(f"\n  Analytics:")
for k, v in summary.items():
    print(f"    {k}: {v}")


# ── 7. Alerts ────────────────────────────────────────────────────────────
#
# AlertRegistry routes alerts to channels (Slack, email, webhook, console).
# send_alert() is the convenience function for quick notifications.

from spine.framework.alerts.protocol import (
    Alert,
    AlertSeverity,
    ChannelType,
    DeliveryResult,
)
from spine.framework.alerts.registry import AlertRegistry, alert_registry

print("\n" + "=" * 72)
print("PHASE 7 — Completion Alerts")
print("=" * 72)


# Register a console channel for demo purposes
class ConsoleChannel:
    """Simple console alert channel for demonstration."""

    name = "demo_console"
    channel_type = ChannelType.CONSOLE
    min_severity = AlertSeverity.INFO

    def should_send(self, alert: Alert) -> bool:
        return alert.severity >= self.min_severity

    def send(self, alert: Alert) -> DeliveryResult:
        print(f"  📧 ALERT [{alert.severity.value}] {alert.title}")
        print(f"     {alert.message}")
        if alert.metadata:
            print(f"     Metadata: {alert.metadata}")
        return DeliveryResult(channel_name=self.name, success=True, message="Sent to console")


alert_registry.register(ConsoleChannel())

# Send completion alert
status_label = "completed successfully" if not quality.has_failures() else "FAILED quality gates"
completion_alert = Alert(
    severity=AlertSeverity.INFO if not quality.has_failures() else AlertSeverity.ERROR,
    title=f"Workflow {result.workflow_name} {status_label}",
    message=(
        f"Run {result.run_id} finished in {result.duration_seconds:.2f}s. "
        f"Steps: {len(result.completed_steps)}/{result.total_steps} completed. "
        f"Quality: {len([s for s in q_results.values() if s == QualityStatus.PASS])}/{len(q_results)} passed."
    ),
    source="golden.sec_workflow",
    domain="sec.filings",
    execution_id=result.run_id,
    metadata={
        "quality_gate": "PASSED" if not quality.has_failures() else "FAILED",
        "analytics_summary": summary,
    },
)

deliveries = alert_registry.send_to_all(completion_alert)
for d in deliveries:
    print(f"  Delivery to {d.channel_name}: {'✓' if d.success else '✗'} {d.message}")


# ── 8. Inspect persisted state ───────────────────────────────────────────
#
# Everything is recorded — runs, steps, quality checks, events.
# Query the backing store directly for full audit trail.

print("\n" + "=" * 72)
print("PHASE 8 — Persisted State (Audit Trail)")
print("=" * 72)

table_counts = wf.table_counts()
print("  Core table row counts:")
for table, count in sorted(table_counts.items()):
    print(f"    {table}: {count}")

run_history = wf.history()
print(f"\n  Run history ({len(run_history)} runs):")
for run in run_history:
    print(f"    {run['run_id'][:8]}... → {run['status']} ({run['duration_seconds']:.3f}s)")


# ── RECAP ────────────────────────────────────────────────────────────────

print("\n" + "=" * 72)
print("GOLDEN PATH WORKFLOW — COMPLETE")
print("=" * 72)
print("""
  This single workflow demonstrated:

    Phase 1  → create_connection(init_schema=True)     DB from scratch
    Phase 2  → table verification                      Schema health
    Phase 3  → fetch_sec_filings()                     External data pull
    Phase 4  → process + aggregate                     Transform & calculate
    Phase 5  → QualityRunner + has_failures()          Quality gates
    Phase 6  → WorkflowResult.to_dict()                Summary JSON
    Phase 7  → AlertRegistry.send_to_all()             Completion alerts
    Phase 8  → wf.table_counts() + wf.history()        Audit trail

  Same workflow works across:
    SDK  → wf.run(partition={...})
    CLI  → spine-core workflow run golden.sec_workflow --partition '{"cik":"..."}"
    API  → POST /api/v1/workflows/golden.sec_workflow/run
""")

# Cleanup
wf.close()
alert_registry.unregister("demo_console")
