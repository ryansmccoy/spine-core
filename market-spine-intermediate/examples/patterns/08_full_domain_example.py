"""
Pattern 08: Full Domain Example

Complete domain implementation showing all pieces working together:
- Sources, Pipelines, Calculations, Aggregations
- Workflow orchestration with Step.pipeline() references
- DB tracking with core_manifest and core_anomalies
- Idempotency and provenance tracking

Run: uv run python -m examples.patterns.08_full_domain_example
"""

from datetime import datetime, timezone, date, timedelta
from typing import Any, Callable
from dataclasses import dataclass, field
from abc import ABC, abstractmethod
import random


# =============================================================================
# Core Tables (In-Memory Simulation)
# =============================================================================

class CoreManifest:
    """Tracks pipeline execution progress."""
    
    def __init__(self):
        self.entries: list[dict] = []
    
    def check_stage_complete(
        self,
        domain: str,
        partition_key: str,
        stage: str,
        tier: str,
    ) -> bool:
        """Check if stage is already complete."""
        return any(
            e["domain"] == domain and
            e["partition_key"] == partition_key and
            e["stage"] == stage and
            e["tier"] == tier and
            e["status"] == "COMPLETE"
            for e in self.entries
        )
    
    def record_start(
        self,
        domain: str,
        partition_key: str,
        stage: str,
        tier: str,
    ) -> str:
        """Record stage start, return capture_id."""
        capture_id = f"{domain}.{stage}.{partition_key}.{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
        self.entries.append({
            "capture_id": capture_id,
            "domain": domain,
            "partition_key": partition_key,
            "stage": stage,
            "tier": tier,
            "status": "RUNNING",
            "started_at": datetime.now(timezone.utc).isoformat(),
        })
        return capture_id
    
    def record_complete(self, capture_id: str, row_count: int):
        """Mark stage as complete."""
        for e in self.entries:
            if e["capture_id"] == capture_id:
                e["status"] = "COMPLETE"
                e["completed_at"] = datetime.now(timezone.utc).isoformat()
                e["row_count"] = row_count


class CoreAnomalies:
    """Records data quality issues."""
    
    def __init__(self):
        self.entries: list[dict] = []
    
    def record(
        self,
        capture_id: str,
        code: str,
        message: str,
        severity: str = "WARNING",
        context: dict | None = None,
    ):
        self.entries.append({
            "capture_id": capture_id,
            "anomaly_code": code,
            "message": message,
            "severity": severity,
            "context": context or {},
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        })


# Global instances
MANIFEST = CoreManifest()
ANOMALIES = CoreAnomalies()


# =============================================================================
# Pipeline Registry
# =============================================================================

_PIPELINE_REGISTRY: dict[str, Callable] = {}


def register_pipeline(name: str):
    """Decorator to register a pipeline function."""
    def decorator(fn: Callable) -> Callable:
        _PIPELINE_REGISTRY[name] = fn
        return fn
    return decorator


def run_pipeline(name: str, context: dict) -> dict:
    """Run a registered pipeline by name."""
    if name not in _PIPELINE_REGISTRY:
        raise KeyError(f"Unknown pipeline: {name}")
    return _PIPELINE_REGISTRY[name](context)


# =============================================================================
# Domain: OTC Market Data
# =============================================================================

DOMAIN = "otc.volume"


# --- Stage 1: Ingest Daily Volume ---

@register_pipeline(f"{DOMAIN}/ingest_daily")
def pipeline_ingest_daily(context: dict) -> dict:
    """
    Ingest daily volume data from source.
    
    Outputs to: raw_daily_volume
    """
    partition_key = context.get("partition_key", date.today().isoformat())
    tier = context.get("tier", "BRONZE")
    
    # Idempotency check
    if MANIFEST.check_stage_complete(DOMAIN, partition_key, "INGEST", tier):
        return {"status": "SKIPPED", "reason": "Already complete"}
    
    capture_id = MANIFEST.record_start(DOMAIN, partition_key, "INGEST", tier)
    
    # Simulate fetching from source
    rows = _simulate_fetch_daily_volume(partition_key)
    
    # Validate and record anomalies
    valid_rows = []
    for row in rows:
        if row.get("volume") is None:
            ANOMALIES.record(capture_id, "NULL_VOLUME", f"Null volume for {row.get('symbol')}")
            continue
        if row["volume"] < 0:
            ANOMALIES.record(capture_id, "NEGATIVE_VOLUME", f"Negative volume for {row.get('symbol')}")
            continue
        row["capture_id"] = capture_id
        valid_rows.append(row)
    
    # "Write" to raw_daily_volume (in real system: DB insert)
    context["raw_daily_volume"] = valid_rows
    
    MANIFEST.record_complete(capture_id, len(valid_rows))
    
    return {
        "status": "SUCCESS",
        "capture_id": capture_id,
        "rows_ingested": len(valid_rows),
        "anomalies": len(rows) - len(valid_rows),
    }


def _simulate_fetch_daily_volume(trade_date: str) -> list[dict]:
    """Simulate fetching from an external source."""
    symbols = ["AAPL", "TSLA", "MSFT", "GOOG", "AMZN"]
    rows = []
    for symbol in symbols:
        vol = random.randint(100000, 5000000)
        # Simulate occasional bad data
        if random.random() < 0.1:
            vol = None
        rows.append({
            "symbol": symbol,
            "trade_date": trade_date,
            "volume": vol,
        })
    return rows


# --- Stage 2: Aggregate Weekly ---

@register_pipeline(f"{DOMAIN}/aggregate_weekly")
def pipeline_aggregate_weekly(context: dict) -> dict:
    """
    Aggregate daily volumes into weekly totals.
    
    Inputs: raw_daily_volume
    Outputs: weekly_volume
    """
    partition_key = context.get("partition_key", "2025-W23")
    tier = context.get("tier", "SILVER")
    
    # Idempotency check
    if MANIFEST.check_stage_complete(DOMAIN, partition_key, "AGGREGATE", tier):
        return {"status": "SKIPPED", "reason": "Already complete"}
    
    capture_id = MANIFEST.record_start(DOMAIN, partition_key, "AGGREGATE", tier)
    
    # Read daily data (in real system: DB query)
    daily_rows = context.get("raw_daily_volume", [])
    
    if not daily_rows:
        ANOMALIES.record(capture_id, "NO_INPUT", "No daily data for aggregation")
        return {"status": "ERROR", "reason": "No input data"}
    
    # Aggregate by symbol
    by_symbol: dict[str, list] = {}
    input_capture_ids = set()
    
    for row in daily_rows:
        symbol = row["symbol"]
        if symbol not in by_symbol:
            by_symbol[symbol] = []
        by_symbol[symbol].append(row)
        if row.get("capture_id"):
            input_capture_ids.add(row["capture_id"])
    
    # Compute aggregates
    weekly_rows = []
    for symbol, rows in by_symbol.items():
        volumes = [r["volume"] for r in rows if r.get("volume")]
        weekly_rows.append({
            "symbol": symbol,
            "week_key": partition_key,
            "total_volume": sum(volumes),
            "avg_daily_volume": sum(volumes) / len(volumes) if volumes else 0,
            "trade_days": len(volumes),
            "capture_id": capture_id,
            "input_min_capture_id": min(input_capture_ids) if input_capture_ids else None,
            "input_max_capture_id": max(input_capture_ids) if input_capture_ids else None,
        })
    
    context["weekly_volume"] = weekly_rows
    
    MANIFEST.record_complete(capture_id, len(weekly_rows))
    
    return {
        "status": "SUCCESS",
        "capture_id": capture_id,
        "rows_aggregated": len(weekly_rows),
    }


# --- Stage 3: Calculate Scores ---

@register_pipeline(f"{DOMAIN}/calculate_scores")
def pipeline_calculate_scores(context: dict) -> dict:
    """
    Calculate volume scores relative to market.
    
    Inputs: weekly_volume
    Outputs: volume_scores
    """
    partition_key = context.get("partition_key", "2025-W23")
    tier = context.get("tier", "GOLD")
    
    # Idempotency check
    if MANIFEST.check_stage_complete(DOMAIN, partition_key, "SCORE", tier):
        return {"status": "SKIPPED", "reason": "Already complete"}
    
    capture_id = MANIFEST.record_start(DOMAIN, partition_key, "SCORE", tier)
    
    weekly_rows = context.get("weekly_volume", [])
    
    if not weekly_rows:
        ANOMALIES.record(capture_id, "NO_INPUT", "No weekly data for scoring")
        return {"status": "ERROR", "reason": "No input data"}
    
    # Calculate market average
    volumes = [r["total_volume"] for r in weekly_rows]
    market_avg = sum(volumes) / len(volumes) if volumes else 0
    
    # Score each symbol
    score_rows = []
    for row in weekly_rows:
        raw_score = (row["total_volume"] / market_avg * 100) if market_avg > 0 else 0
        normalized = min(max(raw_score, 0), 200)
        
        score_rows.append({
            "symbol": row["symbol"],
            "week_key": row["week_key"],
            "total_volume": row["total_volume"],
            "volume_score": round(normalized, 2),
            "market_avg": round(market_avg, 2),
            "capture_id": capture_id,
            "input_capture_id": row.get("capture_id"),
        })
    
    context["volume_scores"] = score_rows
    
    MANIFEST.record_complete(capture_id, len(score_rows))
    
    return {
        "status": "SUCCESS",
        "capture_id": capture_id,
        "rows_scored": len(score_rows),
    }


# =============================================================================
# Workflow Orchestration
# =============================================================================

@dataclass
class StepResult:
    success: bool
    data: dict = field(default_factory=dict)
    error: str | None = None


@dataclass
class Step:
    name: str
    step_type: str  # "pipeline", "lambda", "choice"
    ref: str | None = None  # pipeline name or lambda name
    fn: Callable | None = None  # for lambda steps
    choices: list["Step"] | None = None  # for choice steps
    condition: Callable | None = None


@dataclass
class Workflow:
    name: str
    steps: list[Step]
    
    @staticmethod
    def pipeline(name: str, ref: str) -> Step:
        """Create a pipeline step."""
        return Step(name=name, step_type="pipeline", ref=ref)
    
    @staticmethod
    def lambda_(name: str, fn: Callable) -> Step:
        """Create a lambda step (lightweight validation only!)."""
        return Step(name=name, step_type="lambda", fn=fn)


def run_workflow(workflow: Workflow, context: dict) -> dict:
    """
    Execute a workflow.
    
    Lambdas: Lightweight validation ONLY
    Pipelines: Actual work via registry lookup
    """
    results = {}
    
    for step in workflow.steps:
        print(f"  → Step: {step.name}")
        
        if step.step_type == "lambda":
            # Lambda: MUST be lightweight validation
            try:
                result = step.fn(context)
                results[step.name] = {"status": "SUCCESS", "result": result}
            except Exception as e:
                results[step.name] = {"status": "ERROR", "error": str(e)}
                break
                
        elif step.step_type == "pipeline":
            # Pipeline: actual work via registry
            try:
                result = run_pipeline(step.ref, context)
                results[step.name] = result
                if result.get("status") == "ERROR":
                    break
            except Exception as e:
                results[step.name] = {"status": "ERROR", "error": str(e)}
                break
    
    return {
        "workflow": workflow.name,
        "steps": results,
        "context_keys": list(context.keys()),
    }


# =============================================================================
# Demo Workflow Definition
# =============================================================================

def build_otc_volume_workflow() -> Workflow:
    """
    Build the OTC volume processing workflow.
    
    Pattern: Lambda validates → Pipeline works
    """
    return Workflow(
        name="otc_volume_weekly",
        steps=[
            # Lambda: Lightweight validation
            Workflow.lambda_(
                "validate_partition",
                lambda ctx: ctx.get("partition_key") is not None,
            ),
            
            # Pipeline: Ingest daily data
            Workflow.pipeline(
                "ingest",
                f"{DOMAIN}/ingest_daily",
            ),
            
            # Lambda: Check data quality
            Workflow.lambda_(
                "check_data_quality",
                lambda ctx: len(ctx.get("raw_daily_volume", [])) > 0,
            ),
            
            # Pipeline: Aggregate weekly
            Workflow.pipeline(
                "aggregate",
                f"{DOMAIN}/aggregate_weekly",
            ),
            
            # Pipeline: Calculate scores
            Workflow.pipeline(
                "score",
                f"{DOMAIN}/calculate_scores",
            ),
        ],
    )


# =============================================================================
# Demo
# =============================================================================

def main():
    print("=" * 70)
    print("Pattern 08: Full Domain Example")
    print("=" * 70)
    
    random.seed(42)  # For reproducible demo
    
    # Build workflow
    workflow = build_otc_volume_workflow()
    
    print(f"\n📋 Workflow: {workflow.name}")
    print(f"  Steps: {len(workflow.steps)}")
    for step in workflow.steps:
        step_type = "λ" if step.step_type == "lambda" else "📦"
        ref = step.ref or "(inline)"
        print(f"    {step_type} {step.name} → {ref}")
    
    # Run workflow - first execution
    print("\n🚀 First Execution:")
    print("-" * 50)
    
    context = {
        "partition_key": "2025-W23",
        "tier": "BRONZE",
    }
    
    result = run_workflow(workflow, context)
    
    print("\n  Step Results:")
    for name, step_result in result["steps"].items():
        status = step_result.get("status", "?")
        extra = ""
        if "rows_ingested" in step_result:
            extra = f" (rows={step_result['rows_ingested']})"
        elif "rows_aggregated" in step_result:
            extra = f" (rows={step_result['rows_aggregated']})"
        elif "rows_scored" in step_result:
            extra = f" (rows={step_result['rows_scored']})"
        print(f"    {name}: {status}{extra}")
    
    # Show output data
    print("\n📊 Output Data:")
    print("-" * 50)
    
    if "volume_scores" in context:
        print("  Volume Scores:")
        for score in sorted(context["volume_scores"], key=lambda x: -x["volume_score"]):
            print(f"    {score['symbol']}: score={score['volume_score']}, vol={score['total_volume']:,}")
    
    # Show manifest entries
    print("\n📋 Manifest Entries:")
    print("-" * 50)
    for entry in MANIFEST.entries:
        print(f"  {entry['stage']}/{entry['tier']}: {entry['status']}")
        print(f"    capture_id: {entry['capture_id']}")
    
    # Show anomalies
    print("\n⚠️  Anomalies Recorded:")
    print("-" * 50)
    if ANOMALIES.entries:
        for a in ANOMALIES.entries:
            print(f"  [{a['severity']}] {a['anomaly_code']}: {a['message']}")
    else:
        print("  None")
    
    # Run workflow again - should be idempotent
    print("\n🔄 Second Execution (Idempotency Test):")
    print("-" * 50)
    
    context2 = {"partition_key": "2025-W23", "tier": "BRONZE"}
    result2 = run_workflow(workflow, context2)
    
    print("\n  Step Results:")
    for name, step_result in result2["steps"].items():
        status = step_result.get("status", "?")
        reason = step_result.get("reason", "")
        if reason:
            print(f"    {name}: {status} - {reason}")
        else:
            print(f"    {name}: {status}")
    
    # Summary
    print("\n📈 Summary:")
    print("-" * 50)
    print(f"  Manifest entries: {len(MANIFEST.entries)}")
    print(f"  Anomalies recorded: {len(ANOMALIES.entries)}")
    print(f"  Pipelines registered: {len(_PIPELINE_REGISTRY)}")
    print(f"  Final scores: {len(context.get('volume_scores', []))}")
    
    print("\n✅ Demo complete!")


if __name__ == "__main__":
    main()
