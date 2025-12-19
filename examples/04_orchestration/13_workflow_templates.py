#!/usr/bin/env python3
"""Workflow Templates — pre-built patterns for common workflow shapes.

Demonstrates the template system for rapidly creating workflows from
proven patterns.  Templates encode best-practice step configurations
so teams can instantiate, customize, and register without building
workflows from scratch.

Demonstrates:
    1. ``etl_pipeline()`` — Extract → Transform → Load (+optional validation)
    2. ``fan_out_fan_in()`` — Map/scatter step → merge results
    3. ``conditional_branch()`` — Route based on a condition
    4. ``retry_wrapper()`` — Pipeline with retry + optional fallback
    5. ``scheduled_batch()`` — Wait → Execute → Validate → Notify
    6. Template registry — ``register_template()``, ``get_template()``, ``list_templates()``
    7. Custom templates — build and register your own

Architecture::

    Template Registry
    ├── etl_pipeline        → 3-4 step sequential workflow
    ├── fan_out_fan_in      → map + optional merge
    ├── conditional_branch  → choice + two pipeline branches
    ├── retry_wrapper       → pipeline with retry_policy + fallback
    └── scheduled_batch     → wait + execute + validate? + notify?

    register_template("my_pattern", my_factory)
                  ↓
    get_template("my_pattern")(**kwargs)  →  Workflow

Key Concepts:
    - **Template factories**: Each template is a function that returns
      a ``Workflow``.  Parameters customize names, pipelines, options.
    - **Auto-registration**: Built-in templates register themselves
      on import.  Custom templates use ``register_template()``.
    - **Composition over inheritance**: Templates create standard
      ``Workflow`` objects — no special subclass needed.

See Also:
    - ``01_workflow_basics.py``    — manual workflow construction
    - ``07_parallel_dag.py``       — custom DAGs
    - :mod:`spine.orchestration.templates`

Run:
    python examples/04_orchestration/13_workflow_templates.py

Expected Output:
    Seven sections demonstrating each built-in template, the registry,
    and custom template creation.
"""

from __future__ import annotations

from spine.orchestration import Workflow, Step, StepResult
from spine.orchestration.templates import (
    conditional_branch,
    etl_pipeline,
    fan_out_fan_in,
    get_template,
    list_templates,
    register_template,
    retry_wrapper,
    scheduled_batch,
)


# =============================================================================
# Example handlers for templates that need callables
# =============================================================================

def validate_quality(ctx, config) -> StepResult:
    """Validate data quality between extract and transform."""
    return StepResult.ok(output={"quality_score": 0.97, "passed": True})


def should_use_realtime(ctx) -> bool:
    """Condition: route to realtime pipeline if data is fresh."""
    return ctx.params.get("data_age_hours", 24) < 1


def merge_results(ctx, config) -> StepResult:
    """Merge scattered results after fan-in."""
    return StepResult.ok(output={"merged": True, "total_items": 42})


def send_notification(ctx, config) -> StepResult:
    """Send batch completion notification."""
    return StepResult.ok(output={"notified": True, "channel": "slack"})


def validate_batch(ctx, config) -> StepResult:
    """Validate batch execution results."""
    return StepResult.ok(output={"batch_valid": True})


def main() -> None:
    """Run all workflow template demonstrations."""

    # ─────────────────────────────────────────────────────────────────
    print("=" * 72)
    print("SECTION 1: Template Registry")
    print("=" * 72)

    templates = list_templates()
    print(f"\nRegistered templates ({len(templates)}):")
    for name in templates:
        print(f"  • {name}")

    # Templates can be looked up by name
    etl_factory = get_template("etl_pipeline")
    print(f"\nLooked up 'etl_pipeline': {etl_factory.__name__}")

    # ─────────────────────────────────────────────────────────────────
    print("\n" + "=" * 72)
    print("SECTION 2: ETL Pipeline Template")
    print("=" * 72)

    # Basic 3-step ETL
    wf_basic = etl_pipeline(
        name="finra.daily_etl",
        extract_pipeline="finra.fetch_data",
        transform_pipeline="finra.normalize",
        load_pipeline="finra.store",
        domain="finra",
    )
    print(f"\nBasic ETL: {wf_basic.name}")
    print(f"  Steps: {[s.name for s in wf_basic.steps]}")
    print(f"  Domain: {wf_basic.domain}")
    print(f"  Tags: {wf_basic.tags}")

    # ETL with validation step
    wf_validated = etl_pipeline(
        name="sec.filing_etl",
        extract_pipeline="sec.fetch_filings",
        transform_pipeline="sec.parse_xbrl",
        load_pipeline="sec.store_parsed",
        validate_handler=validate_quality,
        domain="sec",
        description="SEC filing pipeline with quality gate",
        tags=["sec", "etl", "validated"],
    )
    print(f"\nValidated ETL: {wf_validated.name}")
    print(f"  Steps: {[s.name for s in wf_validated.steps]}")
    print(f"  Has validation: {any(s.name == 'validate' for s in wf_validated.steps)}")
    print(f"  Description: {wf_validated.description}")

    # ─────────────────────────────────────────────────────────────────
    print("\n" + "=" * 72)
    print("SECTION 3: Fan-Out / Fan-In Template")
    print("=" * 72)

    wf_fanout = fan_out_fan_in(
        name="batch.process_records",
        items_path="$.data.records",
        iterator_pipeline="record.process_single",
        merge_handler=merge_results,
        max_concurrency=16,
        domain="batch",
        tags=["batch", "parallel"],
    )
    print(f"\nFan-out workflow: {wf_fanout.name}")
    print(f"  Steps: {[s.name for s in wf_fanout.steps]}")
    for step in wf_fanout.steps:
        print(f"    {step.name}: type={step.step_type.value}", end="")
        if step.items_path:
            print(f", items_path={step.items_path}, concurrency={step.max_concurrency}", end="")
        print()
    print(f"  Tags: {wf_fanout.tags}")

    # Fan-out without merge (fire-and-forget)
    wf_scatter = fan_out_fan_in(
        name="events.broadcast",
        items_path="$.events",
        iterator_pipeline="event.publish",
        max_concurrency=32,
    )
    print(f"\nFire-and-forget scatter: {wf_scatter.name}")
    print(f"  Steps: {[s.name for s in wf_scatter.steps]}")

    # ─────────────────────────────────────────────────────────────────
    print("\n" + "=" * 72)
    print("SECTION 4: Conditional Branch Template")
    print("=" * 72)

    wf_branch = conditional_branch(
        name="data.route_by_freshness",
        condition=should_use_realtime,
        true_pipeline="data.realtime_process",
        false_pipeline="data.batch_process",
        domain="data",
        description="Route fresh data to realtime, stale to batch",
    )
    print(f"\nConditional workflow: {wf_branch.name}")
    print(f"  Steps: {[s.name for s in wf_branch.steps]}")
    for step in wf_branch.steps:
        print(f"    {step.name}: type={step.step_type.value}", end="")
        if step.step_type.value == "choice":
            print(f", then={step.then_step}, else={step.else_step}", end="")
        elif step.pipeline_name:
            print(f", pipeline={step.pipeline_name}", end="")
        print()

    # ─────────────────────────────────────────────────────────────────
    print("\n" + "=" * 72)
    print("SECTION 5: Retry Wrapper Template")
    print("=" * 72)

    # Basic retry
    wf_retry = retry_wrapper(
        name="api.resilient_fetch",
        target_pipeline="api.fetch_external",
        max_retries=5,
        domain="api",
        tags=["resilience", "api"],
    )
    print(f"\nBasic retry: {wf_retry.name}")
    print(f"  Steps: {[s.name for s in wf_retry.steps]}")
    attempt_step = wf_retry.steps[0]
    print(f"  Retry policy: max_attempts={attempt_step.retry_policy.max_attempts}")
    print(f"  Error policy: {attempt_step.on_error.value}")

    # Retry with fallback
    wf_fallback = retry_wrapper(
        name="fetch.with_fallback",
        target_pipeline="primary.data_source",
        fallback_pipeline="secondary.data_source",
        max_retries=3,
    )
    print(f"\nRetry + fallback: {wf_fallback.name}")
    print(f"  Steps: {[s.name for s in wf_fallback.steps]}")
    print(f"  Failure policy: {wf_fallback.execution_policy.on_failure.value}")

    # ─────────────────────────────────────────────────────────────────
    print("\n" + "=" * 72)
    print("SECTION 6: Scheduled Batch Template")
    print("=" * 72)

    # Full scheduled batch: wait → execute → validate → notify
    wf_batch = scheduled_batch(
        name="nightly.report",
        wait_seconds=3600,  # 1 hour
        execute_pipeline="report.generate_nightly",
        validate_handler=validate_batch,
        notify_handler=send_notification,
        domain="reports",
        tags=["scheduled", "nightly"],
    )
    print(f"\nScheduled batch: {wf_batch.name}")
    print(f"  Steps: {[s.name for s in wf_batch.steps]}")
    for step in wf_batch.steps:
        print(f"    {step.name}: type={step.step_type.value}", end="")
        if step.duration_seconds:
            print(f", wait={step.duration_seconds}s", end="")
        if step.pipeline_name:
            print(f", pipeline={step.pipeline_name}", end="")
        if step.depends_on:
            print(f", depends_on={list(step.depends_on)}", end="")
        print()

    # Minimal batch: wait → execute
    wf_simple_batch = scheduled_batch(
        name="hourly.sync",
        wait_seconds=60,
        execute_pipeline="sync.incremental",
    )
    print(f"\nMinimal batch: {wf_simple_batch.name}")
    print(f"  Steps: {[s.name for s in wf_simple_batch.steps]}")

    # ─────────────────────────────────────────────────────────────────
    print("\n" + "=" * 72)
    print("SECTION 7: Custom Templates")
    print("=" * 72)

    # Register a custom template
    def audit_workflow(
        *,
        name: str,
        scan_pipeline: str,
        report_pipeline: str,
        domain: str = "audit",
    ) -> Workflow:
        """Custom template for audit workflows."""
        return Workflow(
            name=name,
            steps=[
                Step.pipeline("scan", scan_pipeline),
                Step.lambda_("validate", validate_quality, depends_on=("scan",)),
                Step.pipeline("report", report_pipeline, depends_on=("validate",)),
            ],
            domain=domain,
            tags=["audit", "compliance"],
        )

    register_template("audit_workflow", audit_workflow)
    print(f"\nRegistered custom template: 'audit_workflow'")
    print(f"Available templates: {list_templates()}")

    # Use it via registry lookup
    factory = get_template("audit_workflow")
    wf_audit = factory(
        name="quarterly.compliance",
        scan_pipeline="compliance.scan_portfolio",
        report_pipeline="compliance.generate_report",
    )
    print(f"\nCreated from template: {wf_audit.name}")
    print(f"  Steps: {[s.name for s in wf_audit.steps]}")
    print(f"  Tags: {wf_audit.tags}")

    # Templates compose into normal workflows — can be serialized
    d = wf_audit.to_dict()
    print(f"\nSerialized to dict with {len(d['steps'])} steps")
    print(f"  Step types: {[s['type'] for s in d['steps']]}")

    print("\n" + "=" * 72)
    print("All workflow template demonstrations complete!")
    print("=" * 72)


if __name__ == "__main__":
    main()
