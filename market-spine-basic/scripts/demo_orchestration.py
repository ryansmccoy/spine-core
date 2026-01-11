#!/usr/bin/env python3
"""
Demo: Orchestration with Real FINRA Pipelines

This script demonstrates the orchestration module working with real
FINRA OTC transparency pipelines in the market-spine-basic environment.

Usage:
    # From market-spine-basic directory:
    uv run python scripts/demo_orchestration.py

What this demonstrates:
1. Defining a pipeline group using Python DSL
2. Registering the group
3. Resolving into an executable plan with real pipeline validation
4. Displaying the execution plan
5. (Optional) Future: Actually executing the plan

Note: This is Phase 1 - we can plan but not yet execute.
      Execution will come in Phase 2 (GroupRunner).
"""

from datetime import date, timedelta
from spine.core import WeekEnding
from spine.orchestration import (
    PipelineGroup,
    PipelineStep,
    ExecutionPolicy,
    ExecutionMode,
    FailurePolicy,
    register_group,
    get_group,
    list_groups,
    PlanResolver,
)
from spine.framework.registry import list_pipelines


def print_header(title: str):
    """Print a formatted section header."""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def print_section(title: str):
    """Print a formatted subsection header."""
    print(f"\n{title}")
    print("-" * 50)


def demo_list_available_pipelines():
    """Show what pipelines are available."""
    print_header("AVAILABLE PIPELINES")
    
    pipelines = list_pipelines()
    finra_pipelines = [p for p in pipelines if "finra.otc_transparency" in p]
    
    print(f"\nFound {len(finra_pipelines)} FINRA OTC Transparency pipelines:\n")
    for pipeline in sorted(finra_pipelines):
        print(f"  • {pipeline}")
    
    return finra_pipelines


def demo_define_group():
    """Define a pipeline group using Python DSL."""
    print_header("DEFINE PIPELINE GROUP")
    
    # Calculate last Friday (typical week_ending)
    today = date.today()
    week_ending = WeekEnding.from_any_date(today)
    
    print(f"\nCreating FINRA Weekly Refresh group for week ending {week_ending}...")
    
    group = PipelineGroup(
        name="finra.weekly_refresh",
        domain="finra.otc_transparency",
        description="Weekly FINRA OTC transparency data refresh",
        version=1,
        defaults={
            "tier": "NMS_TIER_1",
            "week_ending": str(week_ending),
        },
        steps=[
            PipelineStep(
                name="ingest",
                pipeline="finra.otc_transparency.ingest_week",
                params={
                    "source": "fixture",  # Use fixture data for demo
                },
            ),
            PipelineStep(
                name="normalize",
                pipeline="finra.otc_transparency.normalize_week",
                depends_on=["ingest"],
            ),
            PipelineStep(
                name="aggregate",
                pipeline="finra.otc_transparency.aggregate_week",
                depends_on=["normalize"],
            ),
            PipelineStep(
                name="rolling",
                pipeline="finra.otc_transparency.compute_rolling",
                depends_on=["aggregate"],
            ),
        ],
        policy=ExecutionPolicy(
            mode=ExecutionMode.SEQUENTIAL,
            on_failure=FailurePolicy.STOP,
            timeout_minutes=30,
        ),
    )
    
    print(f"\n✓ Group defined: {group.name}")
    print(f"  Domain: {group.domain}")
    print(f"  Steps: {len(group.steps)}")
    print(f"  Policy: {group.policy.mode.value} execution")
    
    return group


def demo_register_group(group: PipelineGroup):
    """Register the group."""
    print_header("REGISTER GROUP")
    
    print(f"\nRegistering group: {group.name}")
    register_group(group)
    
    # Verify registration
    all_groups = list_groups()
    print(f"\n✓ Group registered successfully")
    print(f"  Total groups in registry: {len(all_groups)}")
    
    # Retrieve to confirm
    retrieved = get_group(group.name)
    print(f"  Retrieved: {retrieved.name} (v{retrieved.version})")


def demo_resolve_plan(group_name: str):
    """Resolve the group into an executable plan."""
    print_header("RESOLVE EXECUTION PLAN")
    
    group = get_group(group_name)
    
    print(f"\nResolving group: {group.name}")
    print("  • Validating pipeline references...")
    print("  • Checking for cycles...")
    print("  • Performing topological sort...")
    print("  • Merging parameters...")
    
    # Resolve with pipeline validation enabled
    resolver = PlanResolver(validate_pipelines=True)
    plan = resolver.resolve(group)
    
    print(f"\n✓ Plan resolved successfully")
    print(f"  Batch ID: {plan.batch_id}")
    print(f"  Steps: {plan.step_count}")
    print(f"  Group version: {plan.group_version}")
    
    return plan


def demo_display_plan(plan):
    """Display the execution plan in detail."""
    print_header("EXECUTION PLAN DETAILS")
    
    print(f"\nGroup: {plan.group_name} (v{plan.group_version})")
    print(f"Batch ID: {plan.batch_id}")
    print(f"Execution: {plan.policy.mode.value}")
    print(f"On Failure: {plan.policy.on_failure.value}")
    print(f"\nSteps ({plan.step_count}):")
    print()
    
    for step in plan.steps:
        print(f"  [{step.sequence_order}] {step.step_name}")
        print(f"      Pipeline: {step.pipeline_name}")
        
        if step.depends_on:
            deps = ", ".join(step.depends_on)
            print(f"      Depends on: {deps}")
        else:
            print(f"      Depends on: none (root step)")
        
        print(f"      Parameters:")
        for key, value in sorted(step.params.items()):
            print(f"        • {key}: {value}")
        print()


def demo_plan_serialization(plan):
    """Demonstrate plan serialization."""
    print_header("PLAN SERIALIZATION")
    
    print("\nPlan can be serialized to dict/JSON for:")
    print("  • Persistence to database")
    print("  • API responses")
    print("  • Audit logs")
    print()
    
    plan_dict = plan.to_dict()
    
    print("Serialized keys:")
    for key in plan_dict.keys():
        print(f"  • {key}")
    
    # Show a sample
    print(f"\nSample - First step:")
    import json
    print(json.dumps(plan_dict["steps"][0], indent=2))


def demo_next_steps():
    """Explain what comes next."""
    print_header("WHAT'S NEXT?")
    
    print("""
This demo showed Phase 1 of the orchestration module:
  ✓ Define groups (Python DSL or YAML)
  ✓ Register groups
  ✓ Validate pipeline references
  ✓ Resolve dependency DAG
  ✓ Generate execution plan

PHASE 2 - Execution (Coming Soon):
  • GroupRunner class to actually execute plans
  • Integration with Dispatcher.submit()
  • Status tracking (running/completed/failed)
  • DLQ for failed steps
  • Resume from failed step

PHASE 3 - Scheduling:
  • Integration with ScheduleManager
  • Cron-based group execution
  • Concurrency guards
  • Monitoring and alerts

For now, you can manually run each pipeline using:
  uv run spine run run <pipeline_name> --params...

Example:
  uv run spine run run finra.otc_transparency.ingest_week \\
    --week-ending 2026-01-10 \\
    --tier NMS_TIER_1 \\
    --file data/fixtures/otc/week_2026-01-10.psv
""")


def main():
    """Run the complete demo."""
    print_header("SPINE ORCHESTRATION DEMO")
    print("\nDemonstrating Phase 1: Pipeline Groups & DAG Planning")
    print("Using real FINRA OTC Transparency pipelines")
    
    try:
        # Step 1: Show available pipelines
        finra_pipelines = demo_list_available_pipelines()
        
        if not finra_pipelines:
            print("\n⚠ Warning: No FINRA pipelines found.")
            print("Make sure spine-domains is installed:")
            print("  uv pip install -e packages/spine-domains")
            return
        
        # Step 2: Define a group
        group = demo_define_group()
        
        # Step 3: Register it
        demo_register_group(group)
        
        # Step 4: Resolve to plan
        plan = demo_resolve_plan(group.name)
        
        # Step 5: Display the plan
        demo_display_plan(plan)
        
        # Step 6: Show serialization
        demo_plan_serialization(plan)
        
        # Step 7: Next steps
        demo_next_steps()
        
        print("\n✓ Demo completed successfully!")
        
    except Exception as e:
        print(f"\n✗ Demo failed: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
