"""
FINRA OTC Transparency Weekly Refresh - Orchestration v2 Example

This example demonstrates how to use the new orchestration v2 primitives
to build a complete data ingestion workflow for FINRA OTC transparency data.

Key Concepts Demonstrated:
1. Workflow definition with Step factory methods
2. Lambda steps for validation and routing
3. Pipeline steps for registered pipelines
4. WorkflowContext for data passing between steps
5. StepResult for structured output
6. Quality metrics for data quality gates

Usage:
    python -m examples.finra_workflow_example
    
    # Or with parameters:
    python -m examples.finra_workflow_example --tier NMS_TIER_1 --week 2026-01-06
"""

from __future__ import annotations

import argparse
from datetime import datetime
from typing import Any

# Core imports
from spine.core.errors import SourceError, ValidationError
from spine.core.result import Ok, Err

# Orchestration v2 imports
from spine.orchestration import (
    Workflow,
    WorkflowContext,
    WorkflowRunner,
    WorkflowStatus,
    Step,
    StepResult,
)
from spine.orchestration.step_result import QualityMetrics, ErrorCategory

# Framework imports
from spine.framework.sources.file import FileSource, FileFormat
from spine.framework.alerts import (
    Alert,
    AlertSeverity,
    ConsoleChannel,
    alert_registry,
)


# =============================================================================
# STEP HANDLERS (Lambda Functions)
# =============================================================================


def validate_params(ctx: WorkflowContext, config: dict[str, Any]) -> StepResult:
    """
    Validate input parameters before starting the workflow.
    
    This is a lambda step that runs inline validation logic.
    """
    tier = ctx.get_param("tier")
    week_date = ctx.get_param("week_date")
    
    # Validate tier
    valid_tiers = ["NMS_TIER_1", "NMS_TIER_2", "OTC_TIER_1", "OTC_TIER_2"]
    if tier and tier not in valid_tiers:
        return StepResult.fail(
            error=f"Invalid tier: {tier}. Must be one of {valid_tiers}",
            category=ErrorCategory.CONFIGURATION,
        )
    
    # Validate week_date format
    if week_date:
        try:
            datetime.fromisoformat(week_date)
        except ValueError:
            return StepResult.fail(
                error=f"Invalid week_date format: {week_date}. Use YYYY-MM-DD",
                category=ErrorCategory.CONFIGURATION,
            )
    
    return StepResult.ok(
        output={"validated": True, "tier": tier, "week_date": week_date},
        context_updates={"validation_passed": True},
    )


def fetch_source_data(ctx: WorkflowContext, config: dict[str, Any]) -> StepResult:
    """
    Fetch data from FINRA source files.
    
    Uses the FileSource adapter with change detection.
    """
    tier = ctx.get_param("tier", "NMS_TIER_1")
    week_date = ctx.get_param("week_date", "2026-01-06")
    
    # Construct file path based on tier and week
    file_path = config.get("data_path", f"data/finra/otc_{tier.lower()}_{week_date}.psv")
    
    # For demo, we'll simulate the fetch
    # In production, this would use FileSource:
    #   source = FileSource(name="finra_otc", path=file_path, format="psv")
    #   result = source.fetch()
    
    # Simulated data
    simulated_records = [
        {"symbol": "AAPL", "tier": tier, "volume": 1000000, "trades": 5000},
        {"symbol": "GOOGL", "tier": tier, "volume": 500000, "trades": 2500},
        {"symbol": "MSFT", "tier": tier, "volume": 750000, "trades": 3750},
    ]
    
    return StepResult.ok(
        output={
            "record_count": len(simulated_records),
            "records": simulated_records,
            "source_file": file_path,
            "content_hash": "abc123def456",  # Would come from FileSource
        },
        context_updates={"fetch_completed": True},
    )


def validate_data_quality(ctx: WorkflowContext, config: dict[str, Any]) -> StepResult:
    """
    Validate data quality against configurable thresholds.
    
    Returns quality metrics for observability.
    """
    # Get data from previous step
    records = ctx.get_output("fetch", "records", [])
    record_count = len(records)
    
    # Validate records
    valid_count = 0
    invalid_reasons = []
    
    for record in records:
        # Check required fields
        if not record.get("symbol"):
            invalid_reasons.append("Missing symbol")
            continue
        if record.get("volume", 0) < 0:
            invalid_reasons.append(f"Negative volume for {record['symbol']}")
            continue
        if record.get("trades", 0) < 0:
            invalid_reasons.append(f"Negative trades for {record['symbol']}")
            continue
        valid_count += 1
    
    # Create quality metrics
    quality = QualityMetrics(
        record_count=record_count,
        valid_count=valid_count,
        passed=valid_count == record_count,
        failure_reasons=invalid_reasons,
    )
    
    # Check quality gate
    min_valid_rate = config.get("min_valid_rate", 0.95)
    if quality.valid_rate < min_valid_rate:
        return StepResult.fail(
            error=f"Data quality below threshold: {quality.valid_rate:.1%} < {min_valid_rate:.0%}",
            category=ErrorCategory.DATA_QUALITY,
            quality=quality,
        )
    
    return StepResult.ok(
        output={
            "valid_count": valid_count,
            "invalid_count": record_count - valid_count,
            "valid_rate": quality.valid_rate,
        },
        quality=quality,
    )


def normalize_records(ctx: WorkflowContext, config: dict[str, Any]) -> StepResult:
    """
    Normalize records to standard schema.
    """
    records = ctx.get_output("fetch", "records", [])
    tier = ctx.get_param("tier", "NMS_TIER_1")
    week_date = ctx.get_param("week_date", "2026-01-06")
    
    normalized = []
    for record in records:
        normalized.append({
            "symbol": record["symbol"].upper(),
            "tier": tier,
            "week_date": week_date,
            "volume": int(record["volume"]),
            "trades": int(record["trades"]),
            "avg_trade_size": record["volume"] / max(record["trades"], 1),
            "normalized_at": datetime.now().isoformat(),
        })
    
    return StepResult.ok(
        output={
            "normalized_count": len(normalized),
            "normalized_records": normalized,
        },
    )


def send_completion_alert(ctx: WorkflowContext, config: dict[str, Any]) -> StepResult:
    """
    Send completion notification via alert channels.
    """
    tier = ctx.get_param("tier", "NMS_TIER_1")
    record_count = ctx.get_output("normalize", "normalized_count", 0)
    valid_rate = ctx.get_output("validate", "valid_rate", 1.0)
    
    # Create alert
    alert = Alert(
        severity=AlertSeverity.INFO,
        title=f"FINRA {tier} Weekly Refresh Complete",
        message=f"Processed {record_count} records with {valid_rate:.1%} validity",
        source="finra.otc_transparency.weekly_refresh",
        domain="finra.otc_transparency",
        metadata={
            "tier": tier,
            "record_count": record_count,
            "valid_rate": valid_rate,
            "run_id": ctx.run_id,
        },
    )
    
    # Send to all registered channels
    results = alert_registry.send_to_all(alert)
    
    return StepResult.ok(
        output={
            "alert_sent": True,
            "channels_notified": len(results),
        },
    )


# =============================================================================
# WORKFLOW DEFINITION
# =============================================================================


def create_finra_weekly_workflow() -> Workflow:
    """
    Create the FINRA OTC Transparency weekly refresh workflow.
    
    This workflow demonstrates:
    - Parameter validation (lambda step)
    - Data fetching with change detection (lambda step using FileSource)
    - Data quality validation with metrics (lambda step)
    - Data normalization (lambda step)
    - Completion notification (lambda step)
    
    In production, some of these would be pipeline steps referencing
    registered pipelines.
    """
    return Workflow(
        name="finra.otc_transparency.weekly_refresh",
        domain="finra.otc_transparency",
        description="Weekly refresh of FINRA OTC transparency data",
        version=1,
        defaults={
            "tier": "NMS_TIER_1",
            "week_date": datetime.now().strftime("%Y-%m-%d"),
        },
        tags=["finra", "otc", "weekly", "production"],
        steps=[
            # Step 1: Validate input parameters
            Step.lambda_(
                "validate_params",
                validate_params,
                config={},
            ),
            
            # Step 2: Fetch source data
            Step.lambda_(
                "fetch",
                fetch_source_data,
                config={"data_path": "data/finra/"},
            ),
            
            # Step 3: Validate data quality
            Step.lambda_(
                "validate",
                validate_data_quality,
                config={"min_valid_rate": 0.95},
            ),
            
            # Step 4: Normalize records
            Step.lambda_(
                "normalize",
                normalize_records,
                config={},
            ),
            
            # Step 5: Send completion alert
            Step.lambda_(
                "notify",
                send_completion_alert,
                config={},
            ),
        ],
    )


# =============================================================================
# WORKFLOW WITH CHOICE STEP (Intermediate Tier)
# =============================================================================


def create_finra_workflow_with_routing() -> Workflow:
    """
    Create a workflow with conditional routing based on data quality.
    
    This demonstrates the choice step for branching logic.
    """
    def quality_check(ctx: WorkflowContext) -> bool:
        """Check if data quality passed threshold."""
        valid_rate = ctx.get_output("validate", "valid_rate", 0)
        return valid_rate >= 0.95
    
    return Workflow(
        name="finra.otc_transparency.weekly_refresh_with_routing",
        domain="finra.otc_transparency",
        description="Weekly refresh with quality-based routing",
        steps=[
            Step.lambda_("validate_params", validate_params),
            Step.lambda_("fetch", fetch_source_data),
            Step.lambda_("validate", validate_data_quality, config={"min_valid_rate": 0.80}),
            
            # Choice step: route based on quality
            Step.choice(
                "quality_gate",
                condition=quality_check,
                then_step="normalize",  # Good quality -> proceed
                else_step="notify_failure",  # Poor quality -> alert
            ),
            
            # Success path
            Step.lambda_("normalize", normalize_records),
            Step.lambda_("notify_success", send_completion_alert),
            
            # Failure path
            Step.lambda_(
                "notify_failure",
                lambda ctx, cfg: StepResult.ok(output={"alerted": True}),
            ),
        ],
    )


# =============================================================================
# MAIN EXECUTION
# =============================================================================


def main():
    """Run the FINRA workflow example."""
    parser = argparse.ArgumentParser(
        description="FINRA OTC Transparency Weekly Refresh Example"
    )
    parser.add_argument(
        "--tier",
        default="NMS_TIER_1",
        choices=["NMS_TIER_1", "NMS_TIER_2", "OTC_TIER_1", "OTC_TIER_2"],
        help="FINRA tier to process",
    )
    parser.add_argument(
        "--week",
        default="2026-01-06",
        help="Week date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run without side effects",
    )
    args = parser.parse_args()
    
    # Register console channel for alerts
    console_channel = ConsoleChannel(
        name="console",
        min_severity=AlertSeverity.INFO,
    )
    alert_registry.register(console_channel)
    
    # Create workflow
    workflow = create_finra_weekly_workflow()
    
    print("=" * 60)
    print(f"Workflow: {workflow.name}")
    print(f"Domain: {workflow.domain}")
    print(f"Steps: {workflow.step_names()}")
    print(f"Required Tier: {workflow.required_tier()}")
    print("=" * 60)
    print()
    
    # Create runner
    runner = WorkflowRunner(dry_run=args.dry_run)
    
    # Execute workflow
    result = runner.execute(
        workflow,
        params={
            "tier": args.tier,
            "week_date": args.week,
        },
    )
    
    # Print results
    print()
    print("=" * 60)
    print("WORKFLOW RESULT")
    print("=" * 60)
    print(f"Status: {result.status.value}")
    print(f"Run ID: {result.run_id}")
    print(f"Duration: {result.duration_seconds:.2f}s")
    print(f"Completed Steps: {result.completed_steps}")
    print(f"Failed Steps: {result.failed_steps}")
    
    if result.error:
        print(f"Error: {result.error}")
        print(f"Error Step: {result.error_step}")
    
    # Print step outputs
    print()
    print("STEP OUTPUTS:")
    for step_name in result.completed_steps:
        output = result.context.get_output(step_name)
        print(f"  {step_name}: {output}")
    
    return 0 if result.status == WorkflowStatus.COMPLETED else 1


if __name__ == "__main__":
    exit(main())
