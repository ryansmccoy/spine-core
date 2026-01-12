#!/usr/bin/env python3
"""
Workflow Orchestration Example - Workflow v2 with Data Passing

This example demonstrates spine-core's Workflow orchestration:
1. Workflow with ordered steps
2. Lambda steps (inline functions)
3. Pipeline steps (registered pipelines)
4. WorkflowContext for data passing between steps
5. StepResult with quality metrics
6. WorkflowRunner for execution

Run:
    cd market-spine-intermediate
    uv run python -m examples.workflow
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import datetime, timezone

# Spine core imports
from spine.orchestration import (
    # Workflow primitives
    Workflow,
    Step,
    StepResult,
    StepType,
    QualityMetrics,
    # Context
    WorkflowContext,
    # Runner
    WorkflowRunner,
    WorkflowResult,
    WorkflowStatus,
)
from spine.framework import (
    Pipeline,
    PipelineResult,
    PipelineStatus,
    register_pipeline,
    clear_registry,
)


# =============================================================================
# Example Data
# =============================================================================

SAMPLE_FINRA_DATA = [
    {"symbol": "AAPL", "tier": "NMS_TIER_1", "shares": 150000, "trades": 1200},
    {"symbol": "MSFT", "tier": "NMS_TIER_1", "shares": 120000, "trades": 950},
    {"symbol": "GOOG", "tier": "NMS_TIER_1", "shares": 80000, "trades": 600},
    {"symbol": "AMZN", "tier": "NMS_TIER_2", "shares": 45000, "trades": 320},
    {"symbol": "TSLA", "tier": "NMS_TIER_2", "shares": 200000, "trades": 1500},
]


# =============================================================================
# Example 1: Creating a Workflow
# =============================================================================


def demo_workflow_creation():
    """Demonstrate creating a Workflow with different step types."""
    print("=" * 70)
    print("EXAMPLE 1: Creating a Workflow")
    print("=" * 70)
    print()
    
    # Lambda step handler - validation function
    def validate_data(ctx: WorkflowContext, config: dict) -> StepResult:
        """Validate ingested data meets quality thresholds."""
        record_count = ctx.get_output("ingest", "record_count", 0)
        min_records = config.get("min_records", 10)
        
        if record_count < min_records:
            return StepResult.fail(
                error=f"Too few records: {record_count} < {min_records}",
                category="DATA_QUALITY",
            )
        
        return StepResult.ok(
            output={"validated": True, "record_count": record_count},
            context_updates={"validation_passed": True},
        )
    
    # Create workflow with mixed step types
    workflow = Workflow(
        name="finra.weekly_refresh",
        domain="finra.otc_transparency",
        description="Weekly FINRA OTC data refresh workflow",
        steps=[
            # Step 1: Lambda to fetch data
            Step.lambda_("fetch", lambda ctx, cfg: StepResult.ok(
                output={"records": SAMPLE_FINRA_DATA, "record_count": len(SAMPLE_FINRA_DATA)}
            )),
            
            # Step 2: Lambda to validate
            Step.lambda_(
                name="validate",
                handler=validate_data,
                config={"min_records": 5},
            ),
            
            # Step 3: Lambda to transform
            Step.lambda_("transform", lambda ctx, cfg: StepResult.ok(
                output={
                    "transformed": True,
                    "tier_counts": {"NMS_TIER_1": 3, "NMS_TIER_2": 2}
                }
            )),
        ],
        defaults={"week_ending": "2025-07-04"},
        tags=["finra", "weekly", "otc"],
    )
    
    print(f"Workflow: {workflow.name}")
    print(f"Domain: {workflow.domain}")
    print(f"Description: {workflow.description}")
    print(f"Required tier: {workflow.required_tier()}")
    print(f"Tags: {workflow.tags}")
    print()
    
    print("Steps:")
    for i, step in enumerate(workflow.steps, 1):
        print(f"  {i}. {step.name}: {step.step_type.value}")
    print()
    
    print("Analysis:")
    print(f"  Has lambda steps: {workflow.has_lambda_steps()}")
    print(f"  Has pipeline steps: {workflow.has_pipeline_steps()}")
    print(f"  Has choice steps: {workflow.has_choice_steps()}")
    print()
    
    return workflow


# =============================================================================
# Example 2: WorkflowContext
# =============================================================================


def demo_workflow_context():
    """Demonstrate WorkflowContext creation and usage."""
    print("=" * 70)
    print("EXAMPLE 2: WorkflowContext")
    print("=" * 70)
    print()
    
    # Create context
    ctx = WorkflowContext.create(
        workflow_name="finra.weekly_refresh",
        params={
            "week_ending": "2025-07-04",
            "tier": "NMS_TIER_1",
            "force_refresh": False,
        },
        partition={"tier": "NMS_TIER_1"},
        dry_run=False,
    )
    
    print(f"Run ID: {ctx.run_id}")
    print(f"Workflow: {ctx.workflow_name}")
    print(f"Started at: {ctx.started_at}")
    print()
    
    print("Parameters:")
    for k, v in ctx.params.items():
        print(f"  {k}: {v}")
    print()
    
    print("Partition key:")
    print(f"  {ctx.partition}")
    print()
    
    # Simulate step outputs being added
    ctx_with_outputs = ctx.with_output("ingest", {
        "record_count": 100,
        "bytes_read": 15000,
        "source": "finra.api",
    })
    
    ctx_with_outputs = ctx_with_outputs.with_output("validate", {
        "valid_count": 95,
        "invalid_count": 5,
        "validation_passed": True,
    })
    
    print("After 2 steps:")
    print(f"  Outputs: {list(ctx_with_outputs.outputs.keys())}")
    print()
    
    # Access outputs
    record_count = ctx_with_outputs.get_output("ingest", "record_count", 0)
    valid_count = ctx_with_outputs.get_output("validate", "valid_count", 0)
    print(f"  ingest.record_count: {record_count}")
    print(f"  validate.valid_count: {valid_count}")
    print()


# =============================================================================
# Example 3: StepResult and QualityMetrics
# =============================================================================


def demo_step_result():
    """Demonstrate StepResult creation with quality metrics."""
    print("=" * 70)
    print("EXAMPLE 3: StepResult and QualityMetrics")
    print("=" * 70)
    print()
    
    # Successful result
    success_result = StepResult.ok(
        output={
            "record_count": 100,
            "processed": True,
        },
        context_updates={
            "last_processed_step": "ingest",
        },
    )
    
    print("Success Result:")
    print(f"  success: {success_result.success}")
    print(f"  output: {success_result.output}")
    print(f"  context_updates: {success_result.context_updates}")
    print()
    
    # Result with quality metrics
    quality = QualityMetrics(
        record_count=100,
        valid_count=95,
        invalid_count=5,
        null_count=2,
        passed=True,
        custom_metrics={
            "completeness": 0.95,
            "uniqueness": 1.0,
        },
    )
    
    result_with_quality = StepResult.ok(
        output={"validated": True},
        quality=quality,
    )
    
    print("Result with Quality Metrics:")
    print(f"  record_count: {quality.record_count}")
    print(f"  valid_count: {quality.valid_count}")
    print(f"  valid_rate: {quality.valid_rate:.1%}")
    print(f"  null_rate: {quality.null_rate:.1%}")
    print(f"  passed: {quality.passed}")
    print(f"  custom: {quality.custom_metrics}")
    print()
    
    # Failed result
    failed_result = StepResult.fail(
        error="Data completeness below 90%: 85%",
        category="DATA_QUALITY",
        quality=QualityMetrics(
            record_count=100,
            valid_count=85,
            passed=False,
            failure_reasons=["completeness_below_threshold"],
        ),
    )
    
    print("Failed Result:")
    print(f"  success: {failed_result.success}")
    print(f"  error: {failed_result.error}")
    print(f"  error_category: {failed_result.error_category}")
    print(f"  quality.passed: {failed_result.quality.passed}")
    print()


# =============================================================================
# Example 4: WorkflowRunner
# =============================================================================


def demo_workflow_runner():
    """Demonstrate WorkflowRunner execution."""
    print("=" * 70)
    print("EXAMPLE 4: WorkflowRunner Execution")
    print("=" * 70)
    print()
    
    # Define step handlers
    def fetch_data(ctx: WorkflowContext, config: dict) -> StepResult:
        """Fetch FINRA data."""
        tier_filter = ctx.params.get("tier")
        
        # Filter data by tier if specified
        if tier_filter:
            records = [r for r in SAMPLE_FINRA_DATA if r["tier"] == tier_filter]
        else:
            records = SAMPLE_FINRA_DATA
        
        print(f"    [fetch] Fetched {len(records)} records for tier={tier_filter}")
        
        return StepResult.ok(
            output={
                "records": records,
                "record_count": len(records),
            }
        )
    
    def validate_data(ctx: WorkflowContext, config: dict) -> StepResult:
        """Validate data quality."""
        record_count = ctx.get_output("fetch", "record_count", 0)
        records = ctx.get_output("fetch", "records", [])
        
        # Compute quality metrics
        valid_count = sum(1 for r in records if r.get("shares", 0) > 0)
        
        quality = QualityMetrics(
            record_count=record_count,
            valid_count=valid_count,
            passed=valid_count / record_count > 0.9 if record_count > 0 else False,
        )
        
        print(f"    [validate] Validated {valid_count}/{record_count} records")
        
        if not quality.passed:
            return StepResult.fail(
                error=f"Validation failed: {quality.valid_rate:.1%} < 90%",
                category="DATA_QUALITY",
                quality=quality,
            )
        
        return StepResult.ok(
            output={"validation_passed": True},
            quality=quality,
        )
    
    def aggregate_data(ctx: WorkflowContext, config: dict) -> StepResult:
        """Aggregate data by tier."""
        records = ctx.get_output("fetch", "records", [])
        
        tier_totals = {}
        for record in records:
            tier = record.get("tier", "unknown")
            if tier not in tier_totals:
                tier_totals[tier] = {"shares": 0, "trades": 0, "count": 0}
            tier_totals[tier]["shares"] += record.get("shares", 0)
            tier_totals[tier]["trades"] += record.get("trades", 0)
            tier_totals[tier]["count"] += 1
        
        print(f"    [aggregate] Aggregated {len(tier_totals)} tier(s)")
        
        return StepResult.ok(
            output={"tier_totals": tier_totals}
        )
    
    def send_alert(ctx: WorkflowContext, config: dict) -> StepResult:
        """Send completion alert."""
        record_count = ctx.get_output("fetch", "record_count", 0)
        tier_totals = ctx.get_output("aggregate", "tier_totals", {})
        
        print(f"    [alert] Would send: 'Processed {record_count} records across {len(tier_totals)} tiers'")
        
        return StepResult.ok(
            output={"alert_sent": True}
        )
    
    # Create workflow
    workflow = Workflow(
        name="finra.weekly_refresh",
        domain="finra.otc_transparency",
        steps=[
            Step.lambda_("fetch", fetch_data),
            Step.lambda_("validate", validate_data),
            Step.lambda_("aggregate", aggregate_data),
            Step.lambda_("alert", send_alert),
        ],
    )
    
    # Create runner and execute
    runner = WorkflowRunner()
    
    print("Executing workflow...")
    print()
    
    result = runner.execute(
        workflow,
        params={"tier": "NMS_TIER_1"},
    )
    
    print()
    print("-" * 40)
    print("EXECUTION RESULTS")
    print("-" * 40)
    print(f"Status: {result.status.value.upper()}")
    print(f"Run ID: {result.run_id[:8]}...")
    print(f"Duration: {result.duration_seconds:.3f}s")
    print(f"Steps: {len(result.completed_steps)}/{result.total_steps} completed")
    print()
    
    print("Step Details:")
    for step_exec in result.step_executions:
        status_icon = "[OK]" if step_exec.status == "completed" else "[FAIL]"
        duration = f"{step_exec.duration_seconds:.3f}s" if step_exec.duration_seconds else "N/A"
        print(f"  {status_icon} {step_exec.step_name}: {step_exec.status} ({duration})")
    print()
    
    # Access final context outputs
    if result.context:
        print("Final outputs:")
        for step_name, outputs in result.context.outputs.items():
            print(f"  {step_name}: {list(outputs.keys())}")
    print()


# =============================================================================
# Example 5: Complete FINRA Workflow
# =============================================================================


def demo_complete_finra_workflow():
    """Demonstrate a complete FINRA workflow with all features."""
    print("=" * 70)
    print("EXAMPLE 5: Complete FINRA Workflow")
    print("=" * 70)
    print()
    
    def ingest_week(ctx: WorkflowContext, config: dict) -> StepResult:
        """Ingest weekly FINRA data."""
        week_ending = ctx.params.get("week_ending", "2025-07-04")
        
        # Simulate ingestion with quality tracking
        records = SAMPLE_FINRA_DATA.copy()
        
        quality = QualityMetrics(
            record_count=len(records),
            valid_count=len(records),
            passed=True,
            custom_metrics={
                "source": "finra.api",
                "week_ending": week_ending,
            },
        )
        
        print(f"    [ingest] Ingested {len(records)} records for week {week_ending}")
        
        return StepResult.ok(
            output={
                "records": records,
                "record_count": len(records),
                "week_ending": week_ending,
            },
            quality=quality,
        )
    
    def normalize_week(ctx: WorkflowContext, config: dict) -> StepResult:
        """Normalize ingested data."""
        records = ctx.get_output("ingest", "records", [])
        
        # Normalize: compute avg shares per trade
        normalized = []
        for record in records:
            normalized.append({
                **record,
                "avg_shares_per_trade": record["shares"] / record["trades"] if record["trades"] > 0 else 0,
            })
        
        print(f"    [normalize] Normalized {len(normalized)} records")
        
        return StepResult.ok(
            output={
                "normalized_records": normalized,
                "record_count": len(normalized),
            }
        )
    
    def quality_gate(ctx: WorkflowContext, config: dict) -> StepResult:
        """Check data quality thresholds."""
        ingest_quality = None
        for step_exec in []:  # Would access quality from prior steps
            pass
        
        record_count = ctx.get_output("normalize", "record_count", 0)
        
        # Simulate quality check
        passed = record_count >= config.get("min_records", 1)
        
        quality = QualityMetrics(
            record_count=record_count,
            valid_count=record_count if passed else 0,
            passed=passed,
        )
        
        if not passed:
            return StepResult.fail(
                error=f"Quality gate failed: {record_count} < {config.get('min_records')}",
                quality=quality,
            )
        
        print(f"    [quality_gate] Passed with {record_count} records")
        
        return StepResult.ok(
            output={"quality_passed": True},
            quality=quality,
        )
    
    # Create complete workflow
    workflow = Workflow(
        name="finra.otc_transparency.weekly_refresh",
        domain="finra.otc_transparency",
        description="Complete FINRA OTC transparency weekly data refresh",
        version=2,
        steps=[
            Step.lambda_("ingest", ingest_week),
            Step.lambda_("normalize", normalize_week),
            Step.lambda_("quality_gate", quality_gate, config={"min_records": 3}),
        ],
        defaults={"week_ending": "2025-07-04"},
        tags=["finra", "weekly", "production"],
    )
    
    print(f"Workflow: {workflow.name}")
    print(f"Version: {workflow.version}")
    print(f"Required tier: {workflow.required_tier()}")
    print()
    
    runner = WorkflowRunner()
    result = runner.execute(workflow)
    
    print()
    print(f"Status: {result.status.value.upper()}")
    print(f"Duration: {result.duration_seconds:.3f}s")
    
    if result.status == WorkflowStatus.COMPLETED:
        print()
        print("SUCCESS: Weekly refresh completed!")
        
        # Show final state
        if result.context:
            normalized = result.context.get_output("normalize", "normalized_records", [])
            print(f"\nNormalized data sample:")
            for record in normalized[:2]:
                print(f"  {record['symbol']}: {record['avg_shares_per_trade']:.1f} avg shares/trade")
    else:
        print(f"\nFailed: {result.error}")
    print()


# =============================================================================
# Main
# =============================================================================


if __name__ == "__main__":
    # Windows console encoding fix
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    
    # Clear any registered pipelines from previous runs
    clear_registry()
    
    demo_workflow_creation()
    print()
    demo_workflow_context()
    print()
    demo_step_result()
    print()
    demo_workflow_runner()
    print()
    demo_complete_finra_workflow()
    
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print()
    print("Key spine-core workflow orchestration patterns:")
    print("  1. Workflow: Named collection of ordered steps")
    print("  2. Step.lambda_(): Inline function steps for validation/routing")
    print("  3. Step.pipeline(): Wrap registered pipelines (when available)")
    print("  4. WorkflowContext: Immutable context with data passing")
    print("  5. StepResult: Success/failure with output and quality metrics")
    print("  6. QualityMetrics: Track record counts, validity, custom metrics")
    print("  7. WorkflowRunner: Execute workflow with step-by-step results")
    print()
    print("Tier Progression:")
    print("  - Basic: Lambda + Pipeline steps")
    print("  - Intermediate: + ChoiceStep (conditional branching)")
    print("  - Advanced: + WaitStep, MapStep, retry policies")
    print()
