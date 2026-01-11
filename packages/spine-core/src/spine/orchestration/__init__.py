"""
Spine Orchestration - Pipeline grouping and simple DAG execution.

This module provides first-class pipeline grouping with static DAG semantics:
- PipelineGroup: Named collection of related pipelines with dependency edges
- PipelineStep: Individual step within a group
- ExecutionPolicy: Sequential/parallel execution with failure handling
- PlanResolver: Resolves groups into executable plans with topological sort
- GroupRegistry: Register, get, and list pipeline groups

This is an opt-in layer on top of the existing pipeline framework.
Existing `spine run <pipeline>` workflows are unchanged.

Example:
    from spine.orchestration import (
        PipelineGroup,
        PipelineStep,
        ExecutionPolicy,
        register_group,
        get_group,
    )

    # Define a group
    group = PipelineGroup(
        name="finra.weekly_refresh",
        domain="finra.otc_transparency",
        steps=[
            PipelineStep("ingest", "finra.otc_transparency.ingest_week"),
            PipelineStep("normalize", "finra.otc_transparency.normalize_week", depends_on=["ingest"]),
            PipelineStep("aggregate", "finra.otc_transparency.aggregate_week", depends_on=["normalize"]),
        ],
    )

    # Register it
    register_group(group)

    # Later, resolve into executable plan
    from spine.orchestration import PlanResolver
    resolver = PlanResolver()
    plan = resolver.resolve(group, params={"tier": "NMS_TIER_1", "week_ending": "2026-01-03"})
"""

from spine.orchestration.models import (
    ExecutionPolicy,
    ExecutionPlan,
    ExecutionMode,
    FailurePolicy,
    GroupRunStatus,
    PipelineGroup,
    PipelineStep,
    PlannedStep,
)
from spine.orchestration.exceptions import (
    GroupError,
    GroupNotFoundError,
    CycleDetectedError,
    PlanResolutionError,
    StepNotFoundError,
    InvalidGroupSpecError,
)
from spine.orchestration.registry import (
    register_group,
    get_group,
    list_groups,
    clear_group_registry,
    group_exists,
)
from spine.orchestration.planner import PlanResolver
from spine.orchestration.loader import (
    load_group_from_yaml,
    load_groups_from_directory,
    group_to_yaml,
)
from spine.orchestration.runner import (
    GroupRunner,
    GroupExecutionResult,
    GroupExecutionStatus,
    StepExecution,
    StepStatus,
    get_runner,
)

__all__ = [
    # Models
    "PipelineGroup",
    "PipelineStep",
    "ExecutionPolicy",
    "ExecutionMode",
    "FailurePolicy",
    "ExecutionPlan",
    "PlannedStep",
    "GroupRunStatus",
    # Exceptions
    "GroupError",
    "GroupNotFoundError",
    "CycleDetectedError",
    "PlanResolutionError",
    "StepNotFoundError",
    "InvalidGroupSpecError",
    # Registry
    "register_group",
    "get_group",
    "list_groups",
    "clear_group_registry",
    "group_exists",
    # Planner
    "PlanResolver",
    # Loader
    "load_group_from_yaml",
    "load_groups_from_directory",
    "group_to_yaml",
    # Runner
    "GroupRunner",
    "GroupExecutionResult",
    "GroupExecutionStatus",
    "StepExecution",
    "StepStatus",
    "get_runner",
]
