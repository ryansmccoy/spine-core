#!/usr/bin/env python3
"""
Portable Orchestration Demo - Works Across All Tiers

This example demonstrates orchestration using spine.orchestration.GroupRunner
with actual pipeline execution. It is designed to work in:
- market-spine-basic
- market-spine-intermediate
- market-spine-advanced
- market-spine-full

WITHOUT any code changes.

Key Design Principles:
1. Uses spine.orchestration from spine-core (shared across all tiers)
2. Uses spine.framework.dispatcher (interface is tier-agnostic)
3. Registers test pipelines at runtime (no external dependencies)
4. Handles Windows console encoding gracefully

Run:
    cd market-spine-basic   # or any tier
    uv run python scripts/orchestration_portable_demo.py
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

# Fix Windows console encoding for emoji output
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Spine imports - these work identically across all tiers
from spine.framework.dispatcher import Dispatcher, TriggerSource, reset_dispatcher
from spine.framework.pipelines import Pipeline, PipelineResult, PipelineStatus
from spine.framework.registry import clear_registry, register_pipeline
from spine.orchestration import (
    ExecutionMode,
    ExecutionPolicy,
    FailurePolicy,
    GroupRunner,
    PipelineGroup,
    PipelineStep,
    PlanResolver,
    clear_group_registry,
    register_group,
)


# =============================================================================
# PORTABLE PIPELINES - Work in any tier
# =============================================================================


@dataclass
class MockDataRow:
    """Simple data structure for demo purposes."""

    symbol: str
    value: float
    source: str


@register_pipeline("demo.fetch_data")
class FetchDataPipeline(Pipeline):
    """Fetches data from a mock source. Tier-agnostic."""

    name = "demo.fetch_data"
    description = "Fetch market data (mock)"
    domain = "demo"

    def run(self) -> PipelineResult:
        started_at = datetime.now(timezone.utc)
        symbol = self.params.get("symbol", "AAPL")
        print(f"    [fetch_data] Fetching data for {symbol}...")

        # Simulate fetching data
        data = [
            MockDataRow(symbol=symbol, value=100.0, source="mock"),
            MockDataRow(symbol=symbol, value=101.5, source="mock"),
        ]

        return PipelineResult(
            status=PipelineStatus.COMPLETED,
            started_at=started_at,
            completed_at=datetime.now(timezone.utc),
            metrics={"rows_fetched": len(data)},
        )


@register_pipeline("demo.validate_data")
class ValidateDataPipeline(Pipeline):
    """Validates fetched data. Tier-agnostic."""

    name = "demo.validate_data"
    description = "Validate data quality"
    domain = "demo"

    def run(self) -> PipelineResult:
        started_at = datetime.now(timezone.utc)
        print("    [validate_data] Validating data quality...")

        # Simulate validation
        validation_passed = True

        return PipelineResult(
            status=PipelineStatus.COMPLETED,
            started_at=started_at,
            completed_at=datetime.now(timezone.utc),
            metrics={"validation_passed": validation_passed},
        )


@register_pipeline("demo.transform_data")
class TransformDataPipeline(Pipeline):
    """Transforms data. Tier-agnostic."""

    name = "demo.transform_data"
    description = "Transform and enrich data"
    domain = "demo"

    def run(self) -> PipelineResult:
        started_at = datetime.now(timezone.utc)
        print("    [transform_data] Transforming data...")

        return PipelineResult(
            status=PipelineStatus.COMPLETED,
            started_at=started_at,
            completed_at=datetime.now(timezone.utc),
            metrics={"transformations_applied": 3},
        )


@register_pipeline("demo.export_data")
class ExportDataPipeline(Pipeline):
    """Exports data. Tier-agnostic."""

    name = "demo.export_data"
    description = "Export processed data"
    domain = "demo"

    def run(self) -> PipelineResult:
        started_at = datetime.now(timezone.utc)
        output_format = self.params.get("output_format", "parquet")
        print(f"    [export_data] Exporting to {output_format}...")

        return PipelineResult(
            status=PipelineStatus.COMPLETED,
            started_at=started_at,
            completed_at=datetime.now(timezone.utc),
            metrics={"format": output_format},
        )


@register_pipeline("demo.failing_pipeline")
class FailingPipeline(Pipeline):
    """Always fails - for testing failure policies."""

    name = "demo.failing_pipeline"
    description = "Intentionally fails (for testing)"
    domain = "demo"

    def run(self) -> PipelineResult:
        print("    [failing_pipeline] About to fail...")
        raise RuntimeError("Intentional failure for testing")


# =============================================================================
# DEMO FUNCTIONS
# =============================================================================


def create_demo_group() -> PipelineGroup:
    """Create a demo pipeline group with diamond dependencies."""
    return PipelineGroup(
        name="demo.data_workflow",
        domain="demo",
        description="Demo data processing workflow",
        steps=[
            PipelineStep(
                name="fetch",
                pipeline="demo.fetch_data",
                depends_on=[],
                params={"source": "mock"},
            ),
            PipelineStep(
                name="validate",
                pipeline="demo.validate_data",
                depends_on=["fetch"],
            ),
            PipelineStep(
                name="transform",
                pipeline="demo.transform_data",
                depends_on=["validate"],
            ),
            PipelineStep(
                name="export",
                pipeline="demo.export_data",
                depends_on=["transform"],
                params={"output_format": "parquet"},
            ),
        ],
        defaults={"symbol": "AAPL"},
        policy=ExecutionPolicy(
            mode=ExecutionMode.SEQUENTIAL,
            on_failure=FailurePolicy.STOP,
        ),
        tags=["demo", "portable"],
    )


def run_demo() -> None:
    """Run the orchestration demo."""
    print("=" * 70)
    print("PORTABLE ORCHESTRATION DEMO")
    print("=" * 70)
    print()
    print("This demo works in: basic, intermediate, advanced, full tiers")
    print("No code changes required between tiers!")
    print()

    # Clean state
    clear_group_registry()
    reset_dispatcher()

    # Create and register group
    group = create_demo_group()
    register_group(group)

    print(f"Group: {group.name}")
    print(f"Domain: {group.domain}")
    print(f"Steps: {len(group.steps)}")
    print(f"Policy: {group.policy.mode.value}, on_failure={group.policy.on_failure.value}")
    print()

    # Resolve execution plan
    print("-" * 70)
    print("RESOLVING EXECUTION PLAN")
    print("-" * 70)

    resolver = PlanResolver()
    plan = resolver.resolve(group, params={"symbol": "MSFT"})

    print(f"Batch ID: {plan.batch_id}")
    print(f"Execution order ({len(plan.steps)} steps):")
    for i, step in enumerate(plan.steps, 1):
        deps = ", ".join(step.depends_on) if step.depends_on else "(none)"
        print(f"  {i}. {step.step_name} -> {step.pipeline_name}")
        print(f"     deps: {deps}")
    print()

    # Execute with GroupRunner
    print("-" * 70)
    print("EXECUTING WITH GROUPRUNNER")
    print("-" * 70)

    runner = GroupRunner()
    result = runner.execute(plan)

    print()
    print("-" * 70)
    print("EXECUTION RESULTS")
    print("-" * 70)

    status_emoji = {
        "completed": "[OK]",
        "failed": "[FAIL]",
        "partial": "[PARTIAL]",
        "skipped": "[SKIP]",
    }

    print(f"Status: {status_emoji.get(result.status.value, '?')} {result.status.value.upper()}")
    print(f"Duration: {result.duration_seconds:.3f}s")
    print(f"Steps: {result.completed_steps}/{result.total_steps} completed")
    print()
    print("Step Details:")
    for step_exec in result.step_results:
        step_status = step_exec.status.value
        emoji = status_emoji.get(step_status, "?")
        duration = f"{step_exec.duration_seconds:.3f}s" if step_exec.duration_seconds else "N/A"
        print(f"  {emoji} {step_exec.step_name}: {step_status} ({duration})")

    print()
    print("=" * 70)

    if result.status.value == "completed":
        print("SUCCESS: All steps completed!")
    else:
        print(f"FINISHED with status: {result.status.value}")

    return result


def demo_failure_policy_comparison() -> None:
    """Compare STOP vs CONTINUE failure policies."""
    print()
    print("=" * 70)
    print("FAILURE POLICY COMPARISON")
    print("=" * 70)

    # Clean state
    clear_group_registry()
    reset_dispatcher()

    # STOP policy
    print()
    print("-" * 70)
    print("1. STOP POLICY (default)")
    print("-" * 70)

    stop_group = PipelineGroup(
        name="demo.stop_test",
        domain="demo",
        steps=[
            PipelineStep(name="step1", pipeline="demo.fetch_data", depends_on=[]),
            PipelineStep(name="step2_fails", pipeline="demo.failing_pipeline", depends_on=["step1"]),
            PipelineStep(name="step3", pipeline="demo.export_data", depends_on=["step2_fails"]),
        ],
        policy=ExecutionPolicy(on_failure=FailurePolicy.STOP),
    )
    register_group(stop_group)

    resolver = PlanResolver()
    plan = resolver.resolve(stop_group)

    runner = GroupRunner()
    result = runner.execute(plan)

    print(f"\nResult: {result.status.value}")
    print(f"Completed: {result.completed_steps}, Failed: {result.failed_steps}, Skipped: {result.skipped_steps}")
    print("-> Execution stopped at first failure, step3 was skipped")

    # CONTINUE policy
    clear_group_registry()

    print()
    print("-" * 70)
    print("2. CONTINUE POLICY")
    print("-" * 70)

    continue_group = PipelineGroup(
        name="demo.continue_test",
        domain="demo",
        steps=[
            PipelineStep(name="step1", pipeline="demo.fetch_data", depends_on=[]),
            PipelineStep(name="step2_fails", pipeline="demo.failing_pipeline", depends_on=["step1"]),
            PipelineStep(name="step3", pipeline="demo.export_data", depends_on=["step2_fails"]),
        ],
        policy=ExecutionPolicy(on_failure=FailurePolicy.CONTINUE),
    )
    register_group(continue_group)

    plan = resolver.resolve(continue_group)
    result = runner.execute(plan)

    print(f"\nResult: {result.status.value}")
    print(f"Completed: {result.completed_steps}, Failed: {result.failed_steps}, Skipped: {result.skipped_steps}")
    print("-> Execution continued, but step3 was still skipped (depends on failed step)")


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Portable orchestration demo")
    parser.add_argument(
        "--demo-failures",
        action="store_true",
        help="Run failure policy comparison demo",
    )
    args = parser.parse_args()

    if args.demo_failures:
        demo_failure_policy_comparison()
    else:
        run_demo()
