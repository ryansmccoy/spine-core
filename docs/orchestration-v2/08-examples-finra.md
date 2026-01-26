# Real Examples: FINRA OTC Transparency

> **Document**: Practical examples using the FINRA OTC domain

## Overview

This document shows how to implement real FINRA OTC Transparency workflows using Orchestration v2. These examples are based on the existing pipelines in `packages/spine-domains/src/spine/domains/finra/otc_transparency/`.

## Example 1: Weekly Refresh Workflow

A complete weekly data refresh that:
1. Ingests raw PSV data
2. Validates the data
3. Normalizes records
4. Aggregates by symbol
5. Computes rolling metrics
6. Notifies on completion

### Current v1 Approach (Pipeline Group)

```python
# Current: PipelineGroup with independent steps
from spine.orchestration import PipelineGroup, PipelineStep

group = PipelineGroup(
    name="finra.weekly_refresh",
    domain="finra.otc_transparency",
    steps=[
        PipelineStep("ingest", "finra.otc_transparency.ingest_week"),
        PipelineStep("normalize", "finra.otc_transparency.normalize_week", 
                     depends_on=["ingest"]),
        PipelineStep("aggregate", "finra.otc_transparency.aggregate_week",
                     depends_on=["normalize"]),
        PipelineStep("rolling", "finra.otc_transparency.compute_rolling",
                     depends_on=["aggregate"]),
    ],
)
```

**Limitations:**
- No data passing between steps
- Can't add validation without new pipeline
- No conditional routing

### New v2 Approach (Workflow)

```python
from spine.orchestration import (
    Workflow,
    Step,
    WorkflowContext,
    StepResult,
    QualityMetrics,
)


# ============================================================================
# Lambda Steps (inline validation and routing)
# ============================================================================

def validate_ingest(ctx: WorkflowContext, config: dict) -> StepResult:
    """
    Validate data after ingestion.
    
    Checks:
    - Record count is reasonable (>0, <1M)
    - No critical symbols missing
    - Data freshness
    """
    ingest_result = ctx.get_output("ingest", {})
    pipeline_result = ingest_result.get("pipeline_result", {})
    metrics = pipeline_result.get("metrics", {})
    
    record_count = metrics.get("rows", 0)
    week_ending = ctx.params.get("week_ending")
    tier = ctx.params.get("tier")
    
    # Validate record count
    if record_count == 0:
        return StepResult.fail(
            f"No records ingested for {tier} {week_ending}",
            category="DATA_QUALITY",
        )
    
    if record_count > 1_000_000:
        return StepResult.fail(
            f"Suspiciously high record count: {record_count}",
            category="DATA_QUALITY",
        )
    
    # Check for expected symbols (configurable)
    expected_symbols = config.get("expected_symbols", [])
    # In real implementation, would query DB to verify
    
    quality = QualityMetrics(
        record_count=record_count,
        valid_count=record_count,  # Assume all valid for now
        null_rate=0.0,
        passed=True,
    )
    
    return StepResult.ok(
        output={
            "record_count": record_count,
            "validated": True,
            "week_ending": week_ending,
            "tier": tier,
        },
        context_updates={
            "ingest_record_count": record_count,
            "ingest_validated": True,
        },
        quality=quality,
    )


def check_rolling_prerequisites(ctx: WorkflowContext, config: dict) -> StepResult:
    """
    Check if we have enough history for rolling calculations.
    
    Rolling metrics require 6 consecutive weeks.
    Skip rolling if we don't have enough history.
    """
    week_ending = ctx.params.get("week_ending")
    tier = ctx.params.get("tier")
    window_weeks = config.get("window_weeks", 6)
    
    # In real implementation, would query DB:
    # SELECT DISTINCT week_ending FROM otc_normalized 
    # WHERE tier = ? AND week_ending <= ?
    # ORDER BY week_ending DESC LIMIT ?
    
    # For example purposes, assume we check and have enough
    has_sufficient_history = True  # Would be actual check
    available_weeks = 8  # Would be actual count
    
    if not has_sufficient_history:
        return StepResult.ok(
            output={
                "has_sufficient_history": False,
                "available_weeks": available_weeks,
                "required_weeks": window_weeks,
            },
            context_updates={
                "skip_rolling": True,
                "skip_reason": f"Only {available_weeks} weeks available, need {window_weeks}",
            },
        )
    
    return StepResult.ok(
        output={
            "has_sufficient_history": True,
            "available_weeks": available_weeks,
        },
        context_updates={
            "skip_rolling": False,
        },
    )


def send_completion_notification(ctx: WorkflowContext, config: dict) -> StepResult:
    """
    Send notification on workflow completion.
    
    Includes summary of what was processed.
    """
    week_ending = ctx.params.get("week_ending")
    tier = ctx.params.get("tier")
    
    # Gather metrics from prior steps
    ingest_count = ctx.get_output("validate_ingest", "record_count", 0)
    rolling_skipped = ctx.params.get("skip_rolling", False)
    
    message = f"""
    FINRA Weekly Refresh Complete
    =============================
    Week Ending: {week_ending}
    Tier: {tier}
    Records Ingested: {ingest_count}
    Rolling Calculated: {"No (insufficient history)" if rolling_skipped else "Yes"}
    """
    
    # In real implementation:
    # send_slack_notification(config["slack_channel"], message)
    # or send_email(config["email_recipients"], message)
    
    return StepResult.ok(
        output={
            "notification_sent": True,
            "message_preview": message.strip()[:200],
        },
        events=[
            {"type": "notification", "channel": "slack", "status": "sent"},
        ],
    )


# ============================================================================
# Workflow Definition
# ============================================================================

finra_weekly_refresh = Workflow(
    name="finra.weekly_refresh_v2",
    domain="finra.otc_transparency",
    description="Complete weekly FINRA OTC data refresh with validation and routing",
    steps=[
        # Step 1: Ingest raw data
        Step.pipeline("ingest", "finra.otc_transparency.ingest_week"),
        
        # Step 2: Validate ingestion (lambda)
        Step.lambda_("validate_ingest", validate_ingest,
            config={"expected_symbols": ["AAPL", "MSFT", "GOOGL"]}),
        
        # Step 3: Normalize
        Step.pipeline("normalize", "finra.otc_transparency.normalize_week"),
        
        # Step 4: Aggregate by symbol
        Step.pipeline("aggregate", "finra.otc_transparency.aggregate_week"),
        
        # Step 5: Check if we can compute rolling
        Step.lambda_("check_rolling", check_rolling_prerequisites,
            config={"window_weeks": 6}),
        
        # Step 6: Conditional - skip rolling if not enough history
        Step.choice("should_compute_rolling",
            condition=lambda ctx: not ctx.params.get("skip_rolling", False),
            then_step="rolling",
            else_step="notify",
        ),
        
        # Step 7: Compute rolling metrics (may be skipped)
        Step.pipeline("rolling", "finra.otc_transparency.compute_rolling"),
        
        # Step 8: Send notification
        Step.lambda_("notify", send_completion_notification,
            config={"slack_channel": "#data-ops"},
            on_error=ErrorPolicy.CONTINUE),  # Don't fail workflow if notification fails
    ],
)


# ============================================================================
# Usage
# ============================================================================

def run_weekly_refresh():
    """Example: Run the weekly refresh workflow."""
    from spine.orchestration import WorkflowRunner
    
    runner = WorkflowRunner()
    
    result = runner.execute(
        finra_weekly_refresh,
        params={
            "tier": "NMS_TIER_1",
            "week_ending": "2026-01-10",
        },
        # Optional: partition for tracking
        partition={"tier": "NMS_TIER_1", "week_ending": "2026-01-10"},
    )
    
    print(f"Status: {result.status}")
    print(f"Completed: {result.completed_steps}/{result.total_steps}")
    
    if result.status == "failed":
        print(f"Failed at: {result.error_step}")
        print(f"Error: {result.error}")
    else:
        # Access outputs from any step
        ingest_count = result.context.get_output("validate_ingest", "record_count")
        print(f"Ingested {ingest_count} records")
```

---

## Example 2: Backfill Workflow with Checkpointing

A workflow for backfilling historical data with resume capability:

```python
from spine.orchestration import (
    Workflow,
    Step,
    WorkflowContext,
    StepResult,
    WorkflowRunner,
)
from datetime import date, timedelta


def generate_week_list(ctx: WorkflowContext, config: dict) -> StepResult:
    """Generate list of weeks to backfill."""
    start_date = date.fromisoformat(ctx.params["start_date"])
    end_date = date.fromisoformat(ctx.params["end_date"])
    
    # Generate Fridays between dates
    weeks = []
    current = start_date
    while current <= end_date:
        # Find Friday of this week
        days_until_friday = (4 - current.weekday()) % 7
        friday = current + timedelta(days=days_until_friday)
        if friday <= end_date:
            weeks.append(friday.isoformat())
        current += timedelta(days=7)
    
    return StepResult.ok(
        output={
            "weeks": weeks,
            "week_count": len(weeks),
        },
        context_updates={
            "weeks_to_process": weeks,
            "total_weeks": len(weeks),
            "processed_weeks": [],
        },
    )


def check_week_exists(ctx: WorkflowContext, config: dict) -> StepResult:
    """Check if week already processed (for idempotency)."""
    week = ctx.params.get("current_week")
    tier = ctx.params.get("tier")
    
    # Would query: SELECT 1 FROM core_manifest WHERE partition_key = ?
    already_exists = False  # Actual check
    
    return StepResult.ok(
        output={"already_exists": already_exists},
        context_updates={"skip_current_week": already_exists},
    )


def record_progress(ctx: WorkflowContext, config: dict) -> StepResult:
    """Record progress for checkpoint."""
    current_week = ctx.params.get("current_week")
    processed = ctx.params.get("processed_weeks", [])
    processed.append(current_week)
    
    return StepResult.ok(
        output={"processed_week": current_week},
        context_updates={"processed_weeks": processed},
    )


# Backfill workflow for a single week (called in loop)
backfill_single_week = Workflow(
    name="finra.backfill_single_week",
    steps=[
        Step.lambda_("check_exists", check_week_exists),
        Step.choice("should_process",
            condition=lambda ctx: not ctx.params.get("skip_current_week"),
            then_step="ingest",
            else_step="record_progress",
        ),
        Step.pipeline("ingest", "finra.otc_transparency.ingest_week"),
        Step.pipeline("normalize", "finra.otc_transparency.normalize_week"),
        Step.pipeline("aggregate", "finra.otc_transparency.aggregate_week"),
        Step.lambda_("record_progress", record_progress),
    ],
)


def run_backfill():
    """Run backfill with resume capability."""
    runner = WorkflowRunner()
    
    # Initial run
    result = runner.execute(
        generate_weeks_workflow,  # First generate week list
        params={
            "tier": "NMS_TIER_1",
            "start_date": "2025-01-01",
            "end_date": "2025-12-31",
        },
    )
    
    weeks = result.context.get_output("generate_weeks", "weeks", [])
    
    # Process each week
    for week in weeks:
        week_result = runner.execute(
            backfill_single_week,
            params={
                "tier": "NMS_TIER_1",
                "week_ending": week,
                "current_week": week,
            },
        )
        
        if week_result.status == "failed":
            print(f"Failed on week {week}: {week_result.error}")
            # Could save checkpoint and resume later
            save_checkpoint(week_result)
            break
```

---

## Example 3: Multi-Tier Parallel Processing

Process all three tiers in parallel:

```python
from spine.orchestration import Workflow, Step, WorkflowRunner
from concurrent.futures import ThreadPoolExecutor


def run_all_tiers(week_ending: str):
    """Process all tiers in parallel."""
    runner = WorkflowRunner()
    tiers = ["NMS_TIER_1", "NMS_TIER_2", "OTC"]
    
    def process_tier(tier: str):
        return runner.execute(
            finra_weekly_refresh,
            params={
                "tier": tier,
                "week_ending": week_ending,
            },
            partition={"tier": tier, "week_ending": week_ending},
        )
    
    # Run in parallel
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(process_tier, tier): tier for tier in tiers}
        
        results = {}
        for future in futures:
            tier = futures[future]
            try:
                results[tier] = future.result()
            except Exception as e:
                results[tier] = {"error": str(e)}
    
    return results
```

---

## Example 4: Quality-Gated Workflow

Stop workflow if data quality falls below threshold:

```python
from spine.orchestration import Workflow, Step, StepResult, QualityMetrics


def strict_quality_check(ctx: WorkflowContext, config: dict) -> StepResult:
    """
    Strict quality gate - fail if thresholds not met.
    
    Thresholds:
    - Null rate < 1%
    - Missing symbols < 5
    - Record count variance < 20% from historical average
    """
    record_count = ctx.get_output("normalize", "record_count", 0)
    null_count = ctx.get_output("normalize", "null_count", 0)
    
    # Calculate metrics
    null_rate = null_count / record_count if record_count > 0 else 1.0
    
    # Historical average (would query from DB)
    historical_avg = 50000  # Example
    variance = abs(record_count - historical_avg) / historical_avg
    
    quality = QualityMetrics(
        record_count=record_count,
        null_rate=null_rate,
        passed=null_rate < 0.01 and variance < 0.20,
    )
    
    if not quality.passed:
        reasons = []
        if null_rate >= 0.01:
            reasons.append(f"Null rate {null_rate:.2%} exceeds 1% threshold")
        if variance >= 0.20:
            reasons.append(f"Record count variance {variance:.2%} exceeds 20%")
        
        return StepResult.fail(
            error=f"Quality gate failed: {'; '.join(reasons)}",
            category="QUALITY_GATE",
            output={"reasons": reasons},
        )
    
    return StepResult.ok(
        output={"quality_passed": True, "null_rate": null_rate, "variance": variance},
        quality=quality,
    )


quality_gated_workflow = Workflow(
    name="finra.quality_gated_refresh",
    steps=[
        Step.pipeline("ingest", "finra.otc_transparency.ingest_week"),
        Step.pipeline("normalize", "finra.otc_transparency.normalize_week"),
        Step.lambda_("quality_gate", strict_quality_check,
            on_error=ErrorPolicy.STOP),  # Stop workflow if quality fails
        Step.pipeline("aggregate", "finra.otc_transparency.aggregate_week"),
        Step.pipeline("rolling", "finra.otc_transparency.compute_rolling"),
    ],
)
```

---

## Example 5: YAML-Based Workflow Definition

Workflows can also be defined in YAML:

```yaml
# workflows/finra_weekly_refresh.yaml
name: finra.weekly_refresh_v2
domain: finra.otc_transparency
description: Complete weekly FINRA OTC data refresh with validation
version: 1

steps:
  - name: ingest
    type: pipeline
    pipeline: finra.otc_transparency.ingest_week
    
  - name: validate_ingest
    type: lambda
    handler: finra.otc_transparency.steps.validate_ingest
    config:
      expected_symbols: ["AAPL", "MSFT", "GOOGL"]
    
  - name: normalize
    type: pipeline
    pipeline: finra.otc_transparency.normalize_week
    
  - name: aggregate
    type: pipeline
    pipeline: finra.otc_transparency.aggregate_week
    
  - name: check_rolling
    type: lambda
    handler: finra.otc_transparency.steps.check_rolling_prerequisites
    config:
      window_weeks: 6
    
  - name: should_compute_rolling
    type: choice
    condition: "not skip_rolling"
    then_step: rolling
    else_step: notify
    
  - name: rolling
    type: pipeline
    pipeline: finra.otc_transparency.compute_rolling
    
  - name: notify
    type: lambda
    handler: common.steps.send_completion_notification
    config:
      slack_channel: "#data-ops"
    on_error: continue
```

Load and run:

```python
from spine.orchestration import load_workflow_from_yaml, WorkflowRunner

workflow = load_workflow_from_yaml("workflows/finra_weekly_refresh.yaml")
runner = WorkflowRunner()
result = runner.execute(workflow, params={...})
```
