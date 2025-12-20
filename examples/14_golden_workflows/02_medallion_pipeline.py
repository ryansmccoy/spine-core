"""Multi-Stage Medallion Workflow — Bronze → Silver → Gold with quality gates.

Demonstrates the medallion architecture pattern where data flows through
stages with quality gates between each transition. Only clean data that
passes quality checks advances to the next stage.

Architecture:
    ┌──────────┐   QualityGate   ┌──────────┐   QualityGate   ┌──────────┐
    │  Bronze  │ ──────────────→ │  Silver  │ ──────────────→ │   Gold   │
    │ (raw)    │  completeness   │(cleaned) │  business rules │(enriched)│
    └──────────┘                 └──────────┘                 └──────────┘
         ↑                            ↑                            ↑
    Ingest raw data          Validate & normalize         Aggregate & score
    from external source     null handling, types         derived metrics

Key patterns:
    - Each stage is its own ManagedWorkflow with persistence
    - QualityRunner gates between stages prevent bad data propagation
    - Failed quality checks halt the workflow with full audit trail
    - Each stage's output becomes the next stage's input
    - Summary JSON captures the entire multi-stage run

Spine modules used:
    - spine.orchestration.managed_workflow — ManagedWorkflow builder
    - spine.core.quality                  — QualityRunner, QualityCheck
    - spine.core.connection               — create_connection
    - spine.framework.alerts.protocol     — Alert, AlertSeverity

Tier: Basic (spine-core only)
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any

from spine.core.connection import create_connection
from spine.core.quality import (
    QualityCategory,
    QualityCheck,
    QualityResult,
    QualityRunner,
    QualityStatus,
)
from spine.orchestration.managed_workflow import ManagedWorkflow

# ── Shared database ─────────────────────────────────────────────────────
#
# All three stages share the same database connection so quality results,
# manifests, and execution history are in one place for auditing.

conn, info = create_connection(init_schema=True)


# ═══════════════════════════════════════════════════════════════════════
# BRONZE STAGE — Raw Data Ingestion
# ═══════════════════════════════════════════════════════════════════════

def ingest_raw_filings(**kwargs: Any) -> dict[str, Any]:
    """Pull raw SEC filings — minimal transformation, preserve everything.

    Bronze layer rules:
      - Keep all fields exactly as received
      - Add ingestion metadata (source, timestamp, batch_id)
      - No filtering, no cleaning, no type coercion
    """
    # Simulated raw data from SEC EDGAR (some records intentionally messy)
    raw_records = [
        {"cik": "320193", "form": "10-K", "filed": "2024-10-31", "revenue": "391035000000",
         "net_income": "93736000000", "shares_outstanding": "15115785000", "period": "2024-09-28"},
        {"cik": "320193", "form": "10-K", "filed": "2023-11-02", "revenue": "383285000000",
         "net_income": "96995000000", "shares_outstanding": "15552752000", "period": "2023-09-30"},
        {"cik": "320193", "form": "10-K", "filed": "2022-10-28", "revenue": "394328000000",
         "net_income": "99803000000", "shares_outstanding": "15943425000", "period": "2022-09-24"},
        # Intentionally incomplete record — should be caught by quality gate
        {"cik": "320193", "form": "10-K", "filed": "2021-10-29", "revenue": None,
         "net_income": "94680000000", "shares_outstanding": "16426786000", "period": "2021-09-25"},
    ]

    return {
        "records": raw_records,
        "record_count": len(raw_records),
        "source": "SEC EDGAR",
        "ingested_at": datetime.now(timezone.utc).isoformat(),
        "batch_id": f"bronze-{int(time.time())}",
    }


print("=" * 72)
print("STAGE 1 — BRONZE (Raw Ingestion)")
print("=" * 72)

bronze_wf = (
    ManagedWorkflow("medallion.bronze")
    .step("ingest", ingest_raw_filings)
    .build()
)
bronze_result = bronze_wf.run()

bronze_data = bronze_result.context.get_output("ingest") if bronze_result.context else {}
records = bronze_data.get("records", [])

print(f"  Status : {bronze_result.status.value}")
print(f"  Records: {len(records)} raw filings ingested")
for r in records:
    rev = r.get("revenue", "N/A")
    print(f"    {r['period']}: revenue={rev}")


# ── Bronze → Silver Quality Gate ─────────────────────────────────────────

print(f"\n  {'─' * 60}")
print(f"  Quality Gate: Bronze → Silver")
print(f"  {'─' * 60}")


def check_completeness(ctx: dict) -> QualityResult:
    """Verify no null revenue values (required for Silver)."""
    recs = ctx.get("records", [])
    nulls = [r for r in recs if r.get("revenue") is None]
    if not nulls:
        return QualityResult(QualityStatus.PASS, "All records have revenue", 0, 0)
    # WARN, not FAIL — we filter nulls at Silver layer
    return QualityResult(
        QualityStatus.WARN,
        f"{len(nulls)} records missing revenue (will be filtered)",
        len(nulls), 0,
    )


def check_record_count(ctx: dict) -> QualityResult:
    """Verify minimum record count for processing."""
    count = len(ctx.get("records", []))
    if count >= 2:
        return QualityResult(QualityStatus.PASS, f"{count} records sufficient", count, ">=2")
    return QualityResult(QualityStatus.FAIL, f"Only {count} record(s)", count, ">=2")


bronze_qr = QualityRunner(conn, domain="medallion.bronze", execution_id=bronze_result.run_id)
bronze_qr.add(QualityCheck("completeness", QualityCategory.COMPLETENESS, check_completeness))
bronze_qr.add(QualityCheck("record_count", QualityCategory.COMPLETENESS, check_record_count))
bronze_checks = bronze_qr.run_all(bronze_data)

for name, status in bronze_checks.items():
    icon = "✓" if status == QualityStatus.PASS else "⚠" if status == QualityStatus.WARN else "✗"
    print(f"  [{icon}] {name}: {status.value}")

if bronze_qr.has_failures():
    print("\n  ✗ BRONZE QUALITY GATE FAILED — halting workflow")
    raise SystemExit(1)

print("  ✓ Bronze quality gate passed — advancing to Silver")


# ═══════════════════════════════════════════════════════════════════════
# SILVER STAGE — Cleaned & Normalized
# ═══════════════════════════════════════════════════════════════════════


def clean_and_normalize(**kwargs: Any) -> dict[str, Any]:
    """Clean raw records — filter nulls, coerce types, normalize formats.

    Silver layer rules:
      - Filter out records with null required fields
      - Coerce string numbers to int/float
      - Normalize date formats
      - Add derived fields that don't require cross-record logic
    """
    raw = kwargs.get("records", [])

    cleaned = []
    rejected = []
    for r in raw:
        if r.get("revenue") is None:
            rejected.append({"record": r, "reason": "null_revenue"})
            continue

        cleaned.append({
            "cik": r["cik"].zfill(10),  # Normalize CIK to 10-digit
            "form_type": r["form"],
            "filed_date": r["filed"],
            "period_end": r["period"],
            "revenue": int(r["revenue"]),
            "net_income": int(r["net_income"]),
            "shares_outstanding": int(r["shares_outstanding"]),
            "eps": round(int(r["net_income"]) / int(r["shares_outstanding"]), 2),
            "profit_margin_pct": round(int(r["net_income"]) / int(r["revenue"]) * 100, 2),
        })

    return {
        "records": cleaned,
        "rejected": rejected,
        "clean_count": len(cleaned),
        "reject_count": len(rejected),
    }


print(f"\n{'=' * 72}")
print("STAGE 2 — SILVER (Cleaned & Normalized)")
print("=" * 72)

silver_wf = (
    ManagedWorkflow("medallion.silver")
    .step("clean", clean_and_normalize, config={"records": records})
    .build()
)
silver_result = silver_wf.run()

silver_data = silver_result.context.get_output("clean") if silver_result.context else {}
clean_records = silver_data.get("records", [])

print(f"  Status  : {silver_result.status.value}")
print(f"  Cleaned : {silver_data.get('clean_count', 0)} records")
print(f"  Rejected: {silver_data.get('reject_count', 0)} records")
for r in clean_records:
    print(f"    {r['period_end']}: EPS=${r['eps']}, margin={r['profit_margin_pct']}%")


# ── Silver → Gold Quality Gate ───────────────────────────────────────────

print(f"\n  {'─' * 60}")
print(f"  Quality Gate: Silver → Gold")
print(f"  {'─' * 60}")


def check_eps_positive(ctx: dict) -> QualityResult:
    """All EPS values must be positive for Gold stage."""
    recs = ctx.get("records", [])
    negatives = [r for r in recs if r.get("eps", 0) <= 0]
    if not negatives:
        return QualityResult(QualityStatus.PASS, "All EPS positive", 0, 0)
    return QualityResult(QualityStatus.FAIL, f"{len(negatives)} records with non-positive EPS",
                         len(negatives), 0)


def check_margin_range(ctx: dict) -> QualityResult:
    """Profit margins should be 0-100% (sanity check)."""
    recs = ctx.get("records", [])
    out_of_range = [r for r in recs if not (0 <= r.get("profit_margin_pct", 0) <= 100)]
    if not out_of_range:
        return QualityResult(QualityStatus.PASS, "All margins in 0-100% range", 0, 0)
    return QualityResult(QualityStatus.FAIL, f"{len(out_of_range)} records with invalid margins",
                         len(out_of_range), 0)


def check_data_freshness(ctx: dict) -> QualityResult:
    """Verify we have recent data (within 3 years)."""
    recs = ctx.get("records", [])
    if recs:
        latest = max(r["period_end"] for r in recs)
        if latest >= "2023-01-01":
            return QualityResult(QualityStatus.PASS, f"Latest period: {latest}", latest, ">=2023")
        return QualityResult(QualityStatus.WARN, f"Latest period {latest} is old", latest, ">=2023")
    return QualityResult(QualityStatus.FAIL, "No records", 0, ">=1")


silver_qr = QualityRunner(conn, domain="medallion.silver", execution_id=silver_result.run_id)
silver_qr.add(QualityCheck("eps_positive", QualityCategory.BUSINESS_RULE, check_eps_positive))
silver_qr.add(QualityCheck("margin_range", QualityCategory.INTEGRITY, check_margin_range))
silver_qr.add(QualityCheck("data_freshness", QualityCategory.COMPLETENESS, check_data_freshness))
silver_checks = silver_qr.run_all(silver_data)

for name, status in silver_checks.items():
    icon = "✓" if status == QualityStatus.PASS else "⚠" if status == QualityStatus.WARN else "✗"
    print(f"  [{icon}] {name}: {status.value}")

if silver_qr.has_failures():
    print("\n  ✗ SILVER QUALITY GATE FAILED — halting workflow")
    raise SystemExit(1)

print("  ✓ Silver quality gate passed — advancing to Gold")


# ═══════════════════════════════════════════════════════════════════════
# GOLD STAGE — Enriched & Aggregated
# ═══════════════════════════════════════════════════════════════════════


def calculate_trends(**kwargs: Any) -> dict[str, Any]:
    """Calculate year-over-year trends and scoring.

    Gold layer rules:
      - Cross-record calculations (YoY growth, moving averages)
      - Scoring and ranking
      - Final analytical output ready for consumption
    """
    records = kwargs.get("records", [])

    # Sort by period (most recent first)
    sorted_records = sorted(records, key=lambda r: r["period_end"], reverse=True)

    # Calculate YoY changes
    enriched = []
    for i, r in enumerate(sorted_records):
        entry = {**r}
        if i < len(sorted_records) - 1:
            prev = sorted_records[i + 1]
            entry["revenue_yoy_pct"] = round((r["revenue"] - prev["revenue"]) / prev["revenue"] * 100, 2)
            entry["eps_yoy_pct"] = round((r["eps"] - prev["eps"]) / prev["eps"] * 100, 2)
        else:
            entry["revenue_yoy_pct"] = None
            entry["eps_yoy_pct"] = None
        enriched.append(entry)

    # Summary score (simple composite)
    latest = enriched[0] if enriched else {}
    health_score = 0
    if latest.get("profit_margin_pct", 0) > 20:
        health_score += 30
    if latest.get("revenue_yoy_pct") and latest["revenue_yoy_pct"] > 0:
        health_score += 25
    if latest.get("eps_yoy_pct") and latest["eps_yoy_pct"] > 0:
        health_score += 25
    if latest.get("eps", 0) > 5:
        health_score += 20

    return {
        "records": enriched,
        "health_score": health_score,
        "trend": "GROWING" if health_score >= 60 else "STABLE" if health_score >= 30 else "DECLINING",
        "latest_period": sorted_records[0]["period_end"] if sorted_records else None,
        "periods_analyzed": len(enriched),
    }


print(f"\n{'=' * 72}")
print("STAGE 3 — GOLD (Enriched & Aggregated)")
print("=" * 72)

gold_wf = (
    ManagedWorkflow("medallion.gold")
    .step("trends", calculate_trends, config={"records": clean_records})
    .build()
)
gold_result = gold_wf.run()

gold_data = gold_result.context.get_output("trends") if gold_result.context else {}

print(f"  Status       : {gold_result.status.value}")
print(f"  Health Score : {gold_data.get('health_score', 'N/A')}/100")
print(f"  Trend        : {gold_data.get('trend', 'N/A')}")
print(f"  Periods      : {gold_data.get('periods_analyzed', 0)}")

gold_records = gold_data.get("records", [])
for r in gold_records:
    rev_yoy = f"{r['revenue_yoy_pct']:+.1f}%" if r.get("revenue_yoy_pct") is not None else "N/A"
    eps_yoy = f"{r['eps_yoy_pct']:+.1f}%" if r.get("eps_yoy_pct") is not None else "N/A"
    print(f"    {r['period_end']}: EPS=${r['eps']}, rev YoY={rev_yoy}, EPS YoY={eps_yoy}")


# ═══════════════════════════════════════════════════════════════════════
# WORKFLOW SUMMARY
# ═══════════════════════════════════════════════════════════════════════

print(f"\n{'=' * 72}")
print("MEDALLION WORKFLOW SUMMARY")
print("=" * 72)

wf_summary = {
    "workflow": "medallion.sec_analysis",
    "completed_at": datetime.now(timezone.utc).isoformat(),
    "stages": {
        "bronze": {
            "status": bronze_result.status.value,
            "records_ingested": len(records),
            "quality_checks": {k: v.value for k, v in bronze_checks.items()},
        },
        "silver": {
            "status": silver_result.status.value,
            "records_cleaned": silver_data.get("clean_count", 0),
            "records_rejected": silver_data.get("reject_count", 0),
            "quality_checks": {k: v.value for k, v in silver_checks.items()},
        },
        "gold": {
            "status": gold_result.status.value,
            "health_score": gold_data.get("health_score"),
            "trend": gold_data.get("trend"),
            "periods_analyzed": gold_data.get("periods_analyzed", 0),
        },
    },
    "total_quality_checks": len(bronze_checks) + len(silver_checks),
    "all_quality_passed": not bronze_qr.has_failures() and not silver_qr.has_failures(),
}

print(f"  Summary JSON:")
print(f"  {json.dumps(wf_summary, indent=2)}")

print(f"""
  Medallion workflow completed:
    Bronze  → {len(records)} raw records ingested
    Silver  → {silver_data.get('clean_count', 0)} cleaned, {silver_data.get('reject_count', 0)} rejected
    Gold    → Score {gold_data.get('health_score', 'N/A')}/100, Trend: {gold_data.get('trend', 'N/A')}
    Quality → {wf_summary['total_quality_checks']} checks, all passed: {wf_summary['all_quality_passed']}
""")

# Cleanup
bronze_wf.close()
silver_wf.close()
gold_wf.close()
