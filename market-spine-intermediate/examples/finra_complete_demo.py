#!/usr/bin/env python3
"""
Comprehensive Spine-Core Demo - All Features Combined

This example demonstrates how all spine-core primitives work together
in a realistic FINRA data pipeline scenario:

1. Error Handling: SpineError hierarchy, Result[T] pattern
2. Source Framework: FileSource for data ingestion
3. Alerting: ConsoleChannel for notifications
4. Workflow Orchestration: Workflow v2 with data passing

This is the "kitchen sink" example showing how these primitives
compose into a production-ready pipeline.

Run:
    cd market-spine-intermediate
    uv run python -m examples.finra_complete_demo
"""

from __future__ import annotations

import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import dataclass
from typing import Any

# Spine core imports - Errors
from spine.core.errors import (
    SpineError,
    SourceError,
    ValidationError,
    TransientError,
    ErrorCategory,
    ErrorContext,
    is_retryable,
)
from spine.core.result import Result, Ok, Err, try_result

# Spine core imports - Sources
from spine.framework.sources import (
    SourceResult,
    source_registry,
)
from spine.framework.sources.file import FileSource

# Spine core imports - Alerts
from spine.framework.alerts import (
    Alert,
    AlertSeverity,
    ConsoleChannel,
    AlertRegistry,
)

# Spine core imports - Orchestration
from spine.orchestration import (
    Workflow,
    Step,
    StepResult,
    QualityMetrics,
    WorkflowContext,
    WorkflowRunner,
    WorkflowStatus,
)

# Pipeline framework
from spine.framework import clear_registry


# =============================================================================
# Configuration
# =============================================================================

QUALITY_THRESHOLD = 0.90  # 90% valid records required
MIN_RECORDS = 3


# =============================================================================
# Sample FINRA Data
# =============================================================================

SAMPLE_FINRA_PSV = """\
week_ending|symbol|tier|shares_or_principal|trade_count
2025-07-04|AAPL|NMS_TIER_1|150000|1200
2025-07-04|MSFT|NMS_TIER_1|120000|950
2025-07-04|GOOG|NMS_TIER_1|80000|600
2025-07-04|AMZN|NMS_TIER_2|45000|320
2025-07-04|TSLA|NMS_TIER_2|200000|1500
2025-07-04|BADCO|NMS_TIER_2|-100|0
"""  # Note: BADCO has invalid data (negative shares, zero trades)


# =============================================================================
# Data Models
# =============================================================================

@dataclass
class FinraRecord:
    """Normalized FINRA OTC record."""
    week_ending: str
    symbol: str
    tier: str
    shares: int
    trades: int
    avg_shares_per_trade: float | None = None
    is_valid: bool = True
    validation_errors: list[str] | None = None


# =============================================================================
# Service Layer (using Result pattern)
# =============================================================================


def parse_finra_record(row: dict[str, Any]) -> Result[FinraRecord]:
    """
    Parse a raw row into a FinraRecord.
    
    Uses Result pattern to make success/failure explicit.
    """
    errors = []
    
    # Validate required fields
    symbol = row.get("symbol", "").strip()
    if not symbol:
        errors.append("Missing symbol")
    
    # Parse shares
    try:
        shares = int(row.get("shares_or_principal", 0))
        if shares < 0:
            errors.append(f"Negative shares: {shares}")
    except (ValueError, TypeError):
        errors.append(f"Invalid shares: {row.get('shares_or_principal')}")
        shares = 0
    
    # Parse trades
    try:
        trades = int(row.get("trade_count", 0))
        if trades < 0:
            errors.append(f"Negative trades: {trades}")
    except (ValueError, TypeError):
        errors.append(f"Invalid trades: {row.get('trade_count')}")
        trades = 0
    
    # Create record
    record = FinraRecord(
        week_ending=row.get("week_ending", ""),
        symbol=symbol,
        tier=row.get("tier", "unknown"),
        shares=shares,
        trades=trades,
        avg_shares_per_trade=shares / trades if trades > 0 else None,
        is_valid=len(errors) == 0,
        validation_errors=errors if errors else None,
    )
    
    if errors:
        return Err(ValidationError(
            f"Invalid record: {', '.join(errors)}",
            context=ErrorContext(metadata={"symbol": symbol, "errors": errors}),
        ))
    
    return Ok(record)


def fetch_finra_data(file_path: str) -> Result[list[dict[str, Any]]]:
    """
    Fetch FINRA data from a file.
    
    Uses try_result to wrap exceptions as Err.
    """
    def _fetch():
        source = FileSource(
            name="finra.weekly",
            path=file_path,
            domain="finra.otc_transparency",
        )
        
        result = source.fetch()
        
        if not result.success:
            raise SourceError(f"Failed to fetch: {result.error}")
        
        return result.data
    
    return try_result(_fetch)


# =============================================================================
# Alert Channel Setup
# =============================================================================

# Create alert registry with console channel
alerts = AlertRegistry()
console_alerts = ConsoleChannel(
    name="finra-console",
    min_severity=AlertSeverity.WARNING,
    color=True,
)
alerts.register(console_alerts)


def send_pipeline_alert(
    severity: AlertSeverity,
    title: str,
    message: str,
    ctx: WorkflowContext | None = None,
) -> None:
    """Send an alert through the registry."""
    alert = Alert(
        severity=severity,
        title=title,
        message=message,
        source="finra.weekly_refresh",
        domain="finra.otc_transparency",
        execution_id=ctx.run_id if ctx else None,
    )
    alerts.send_to_all(alert)


# =============================================================================
# Workflow Step Handlers
# =============================================================================


def step_fetch_data(ctx: WorkflowContext, config: dict) -> StepResult:
    """
    Step 1: Fetch raw FINRA data from file.
    
    Demonstrates: FileSource, SourceResult, error handling
    """
    file_path = ctx.params.get("file_path")
    
    if not file_path:
        return StepResult.fail(
            error="Missing required parameter: file_path",
            category="CONFIGURATION",
        )
    
    # Use FileSource to read data
    source = FileSource(
        name="finra.weekly",
        path=file_path,
        domain="finra.otc_transparency",
    )
    
    fetch_result = source.fetch()
    
    if not fetch_result.success:
        send_pipeline_alert(
            AlertSeverity.ERROR,
            "Data fetch failed",
            f"Could not read FINRA data: {fetch_result.error}",
            ctx,
        )
        return StepResult.fail(
            error=str(fetch_result.error),
            category="SOURCE",
        )
    
    records = fetch_result.data
    metadata = fetch_result.metadata
    
    print(f"    [fetch] Loaded {len(records)} raw records")
    print(f"    [fetch] Content hash: {metadata.content_hash[:16]}...")
    
    return StepResult.ok(
        output={
            "raw_records": records,
            "record_count": len(records),
            "content_hash": metadata.content_hash,
            "source_path": str(file_path),
        },
    )


def step_parse_records(ctx: WorkflowContext, config: dict) -> StepResult:
    """
    Step 2: Parse and validate raw records.
    
    Demonstrates: Result pattern, QualityMetrics
    """
    raw_records = ctx.get_output("fetch", "raw_records", [])
    
    parsed: list[FinraRecord] = []
    valid_count = 0
    invalid_count = 0
    validation_errors: list[str] = []
    
    for row in raw_records:
        result = parse_finra_record(row)
        
        match result:
            case Ok(record):
                parsed.append(record)
                if record.is_valid:
                    valid_count += 1
                else:
                    invalid_count += 1
                    if record.validation_errors:
                        validation_errors.extend(record.validation_errors)
            case Err(error):
                invalid_count += 1
                validation_errors.append(str(error.message))
    
    valid_rate = valid_count / len(raw_records) if raw_records else 0
    passed = valid_rate >= config.get("threshold", QUALITY_THRESHOLD)
    
    quality = QualityMetrics(
        record_count=len(raw_records),
        valid_count=valid_count,
        invalid_count=invalid_count,
        passed=passed,
        failure_reasons=validation_errors[:5],  # Limit for brevity
        custom_metrics={
            "valid_rate": valid_rate,
            "threshold": config.get("threshold", QUALITY_THRESHOLD),
        },
    )
    
    print(f"    [parse] Parsed {len(parsed)} records: {valid_count} valid, {invalid_count} invalid")
    print(f"    [parse] Valid rate: {valid_rate:.1%} (threshold: {QUALITY_THRESHOLD:.0%})")
    
    if not passed:
        send_pipeline_alert(
            AlertSeverity.WARNING,
            "Data quality below threshold",
            f"Valid rate {valid_rate:.1%} < {QUALITY_THRESHOLD:.0%}",
            ctx,
        )
    
    return StepResult.ok(
        output={
            "parsed_records": [r.__dict__ for r in parsed],
            "valid_records": [r.__dict__ for r in parsed if r.is_valid],
            "valid_count": valid_count,
            "invalid_count": invalid_count,
        },
        quality=quality,
    )


def step_aggregate_by_tier(ctx: WorkflowContext, config: dict) -> StepResult:
    """
    Step 3: Aggregate valid records by tier.
    
    Demonstrates: Context data passing
    """
    valid_records = ctx.get_output("parse", "valid_records", [])
    
    tier_stats: dict[str, dict[str, Any]] = {}
    
    for record_dict in valid_records:
        tier = record_dict.get("tier", "unknown")
        
        if tier not in tier_stats:
            tier_stats[tier] = {
                "symbol_count": 0,
                "total_shares": 0,
                "total_trades": 0,
                "symbols": [],
            }
        
        tier_stats[tier]["symbol_count"] += 1
        tier_stats[tier]["total_shares"] += record_dict.get("shares", 0)
        tier_stats[tier]["total_trades"] += record_dict.get("trades", 0)
        tier_stats[tier]["symbols"].append(record_dict.get("symbol"))
    
    # Compute averages
    for tier, stats in tier_stats.items():
        if stats["total_trades"] > 0:
            stats["avg_shares_per_trade"] = stats["total_shares"] / stats["total_trades"]
        else:
            stats["avg_shares_per_trade"] = 0
    
    print(f"    [aggregate] Aggregated {len(tier_stats)} tiers")
    for tier, stats in tier_stats.items():
        print(f"        {tier}: {stats['symbol_count']} symbols, "
              f"{stats['total_shares']:,} shares, "
              f"{stats['avg_shares_per_trade']:.1f} avg/trade")
    
    return StepResult.ok(
        output={
            "tier_stats": tier_stats,
            "tier_count": len(tier_stats),
        },
    )


def step_quality_gate(ctx: WorkflowContext, config: dict) -> StepResult:
    """
    Step 4: Quality gate - check if data meets requirements.
    
    Demonstrates: Quality gating, alerting
    """
    valid_count = ctx.get_output("parse", "valid_count", 0)
    parse_quality = ctx.params.get("_step_quality", {}).get("parse")
    
    min_records = config.get("min_records", MIN_RECORDS)
    
    passed = valid_count >= min_records
    
    quality = QualityMetrics(
        record_count=valid_count,
        valid_count=valid_count if passed else 0,
        passed=passed,
        failure_reasons=[] if passed else [f"Valid count {valid_count} < {min_records}"],
    )
    
    if not passed:
        send_pipeline_alert(
            AlertSeverity.ERROR,
            "Quality gate failed",
            f"Only {valid_count} valid records (minimum: {min_records})",
            ctx,
        )
        return StepResult.fail(
            error=f"Quality gate failed: {valid_count} < {min_records}",
            category="DATA_QUALITY",
            quality=quality,
        )
    
    print(f"    [quality_gate] PASSED: {valid_count} >= {min_records}")
    
    return StepResult.ok(
        output={"gate_passed": True},
        quality=quality,
    )


def step_send_summary(ctx: WorkflowContext, config: dict) -> StepResult:
    """
    Step 5: Send completion summary.
    
    Demonstrates: Final alerting
    """
    tier_stats = ctx.get_output("aggregate", "tier_stats", {})
    valid_count = ctx.get_output("parse", "valid_count", 0)
    source_path = ctx.get_output("fetch", "source_path", "unknown")
    
    summary_lines = [
        f"Processed {valid_count} valid records from {source_path}",
        f"Tiers: {list(tier_stats.keys())}",
    ]
    
    send_pipeline_alert(
        AlertSeverity.INFO,
        "FINRA weekly refresh completed",
        "\n".join(summary_lines),
        ctx,
    )
    
    print(f"    [summary] Sent completion notification")
    
    return StepResult.ok(
        output={"summary_sent": True},
    )


# =============================================================================
# Main Demo
# =============================================================================


def run_complete_demo():
    """Run the complete FINRA workflow demo."""
    print("=" * 70)
    print("COMPREHENSIVE SPINE-CORE DEMO")
    print("=" * 70)
    print()
    print("This demo combines all spine-core features:")
    print("  - Error handling (SpineError, Result[T])")
    print("  - Source framework (FileSource)")
    print("  - Alerting (ConsoleChannel)")
    print("  - Workflow orchestration (Workflow v2)")
    print()
    
    # Create temp file with sample data
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".psv", delete=False, encoding="utf-8"
    ) as f:
        f.write(SAMPLE_FINRA_PSV)
        temp_file = f.name
    
    try:
        print("-" * 70)
        print("CREATING WORKFLOW")
        print("-" * 70)
        print()
        
        # Create the workflow
        workflow = Workflow(
            name="finra.otc_transparency.weekly_refresh",
            domain="finra.otc_transparency",
            description="Complete FINRA OTC weekly data refresh with quality gates",
            version=1,
            steps=[
                Step.lambda_("fetch", step_fetch_data),
                Step.lambda_("parse", step_parse_records, config={"threshold": 0.90}),
                Step.lambda_("aggregate", step_aggregate_by_tier),
                Step.lambda_("quality_gate", step_quality_gate, config={"min_records": 3}),
                Step.lambda_("summary", step_send_summary),
            ],
            defaults={
                "week_ending": "2025-07-04",
            },
            tags=["finra", "weekly", "production"],
        )
        
        print(f"Workflow: {workflow.name}")
        print(f"Version: {workflow.version}")
        print(f"Steps: {len(workflow.steps)}")
        print(f"Required tier: {workflow.required_tier()}")
        print()
        
        print("-" * 70)
        print("EXECUTING WORKFLOW")
        print("-" * 70)
        print()
        
        # Execute workflow
        runner = WorkflowRunner()
        result = runner.execute(
            workflow,
            params={
                "file_path": temp_file,
                "week_ending": "2025-07-04",
            },
        )
        
        print()
        print("-" * 70)
        print("EXECUTION RESULTS")
        print("-" * 70)
        print()
        
        status_icon = {
            WorkflowStatus.COMPLETED: "[SUCCESS]",
            WorkflowStatus.FAILED: "[FAILED]",
            WorkflowStatus.PARTIAL: "[PARTIAL]",
        }
        
        print(f"Status: {status_icon.get(result.status, '?')} {result.status.value.upper()}")
        print(f"Run ID: {result.run_id[:8]}...")
        print(f"Duration: {result.duration_seconds:.3f}s")
        print(f"Steps: {len(result.completed_steps)}/{result.total_steps} completed")
        print()
        
        print("Step Execution:")
        for step_exec in result.step_executions:
            icon = "[OK]" if step_exec.status == "completed" else "[FAIL]"
            duration = f"{step_exec.duration_seconds:.3f}s" if step_exec.duration_seconds else "N/A"
            print(f"  {icon} {step_exec.step_name}: {step_exec.status} ({duration})")
            if step_exec.error:
                print(f"      Error: {step_exec.error}")
        print()
        
        # Show final outputs
        if result.context and result.status == WorkflowStatus.COMPLETED:
            print("-" * 70)
            print("FINAL OUTPUTS")
            print("-" * 70)
            print()
            
            tier_stats = result.context.get_output("aggregate", "tier_stats", {})
            print("Tier Summary:")
            for tier, stats in tier_stats.items():
                print(f"  {tier}:")
                print(f"    Symbols: {stats['symbols']}")
                print(f"    Total shares: {stats['total_shares']:,}")
                print(f"    Avg shares/trade: {stats['avg_shares_per_trade']:.1f}")
            print()
        
        print("=" * 70)
        print("DEMO COMPLETE")
        print("=" * 70)
        print()
        print("This demo showed:")
        print("  1. FileSource reading PSV data with metadata")
        print("  2. Result[T] pattern for parsing with explicit errors")
        print("  3. QualityMetrics tracking valid/invalid records")
        print("  4. Quality gates enforcing data requirements")
        print("  5. ConsoleChannel alerting for warnings/errors")
        print("  6. Workflow orchestration with 5 lambda steps")
        print("  7. Data passing between steps via WorkflowContext")
        print()
        
        return result
        
    finally:
        Path(temp_file).unlink(missing_ok=True)


# =============================================================================
# Main
# =============================================================================


if __name__ == "__main__":
    # Windows console encoding fix
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    
    # Clear registries
    clear_registry()
    
    run_complete_demo()
