"""
Spine Orchestration - Pipeline grouping and workflow execution.

This module provides two orchestration models:

1. **PipelineGroups** (v1): Static DAG of registered pipelines
   - PipelineGroup: Named collection with dependency edges
   - GroupRunner: Executes groups with parallel/sequential policies
   - No data passing between steps

2. **Workflows** (v2): Context-aware step execution
   - Workflow: Ordered steps with context passing
   - WorkflowRunner: Executes with data flow between steps
   - Lambda steps (inline functions) + pipeline steps
   - Quality gates and conditional branching (tier-dependent)

Both models coexist. Use PipelineGroups for simple orchestration,
Workflows when you need data passing, validation, or routing.

Tier availability:
- Basic: Workflow, Step (lambda, pipeline), WorkflowRunner
- Intermediate: + ChoiceStep (conditional branching)
- Advanced: + WaitStep, MapStep, Checkpointing, Resume

Example (v2 Workflow):
    from spine.orchestration import (
        Workflow,
        Step,
        StepResult,
        WorkflowRunner,
    )

    def validate_fn(ctx, config):
        count = ctx.get_output("ingest", "record_count", 0)
        if count < 100:
            return StepResult.fail("Too few records")
        return StepResult.ok(output={"validated": True})

    workflow = Workflow(
        name="finra.weekly_refresh",
        steps=[
            Step.pipeline("ingest", "finra.otc_transparency.ingest_week"),
            Step.lambda_("validate", validate_fn),
            Step.pipeline("normalize", "finra.otc_transparency.normalize_week"),
        ],
    )

    runner = WorkflowRunner()
    result = runner.execute(workflow, params={"tier": "NMS_TIER_1"})

Example (v1 PipelineGroup - still supported):
    from spine.orchestration import PipelineGroup, PipelineStep, GroupRunner

    group = PipelineGroup(
        name="finra.weekly_refresh",
        steps=[
            PipelineStep("ingest", "finra.otc_transparency.ingest_week"),
            PipelineStep("normalize", "finra.otc_transparency.normalize_week", depends_on=["ingest"]),
        ],
    )

    runner = GroupRunner()
    result = runner.execute(group, params={...})
"""

# =============================================================================
# v1: PipelineGroups (static DAG, no data passing)
# =============================================================================

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
    StepExecution as GroupStepExecution,
    StepStatus as GroupStepStatus,
    get_runner as get_group_runner,
)

# Backwards-compatible aliases
StepStatus = GroupStepStatus

# =============================================================================
# v2: Workflows (context-aware, data passing)
# =============================================================================

from spine.orchestration.workflow_context import WorkflowContext
from spine.orchestration.step_result import (
    StepResult,
    QualityMetrics,
    ErrorCategory,
)
from spine.orchestration.step_types import (
    Step,
    StepType,
    ErrorPolicy,
    RetryPolicy,
)
from spine.orchestration.workflow import Workflow
from spine.orchestration.workflow_runner import (
    WorkflowRunner,
    WorkflowResult,
    WorkflowStatus,
    StepExecution,
    get_workflow_runner,
)

# Tracked runner (with database persistence)
from spine.orchestration.tracked_runner import (
    TrackedWorkflowRunner,
    get_workflow_state,
    list_workflow_failures,
)


__all__ = [
    # ==========================================================================
    # v1: PipelineGroups
    # ==========================================================================
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
    # Group Runner
    "GroupRunner",
    "GroupExecutionResult",
    "GroupExecutionStatus",
    "GroupStepExecution",
    "GroupStepStatus",
    "StepStatus",  # Backwards-compatible alias
    "get_group_runner",
    # ==========================================================================
    # v2: Workflows
    # ==========================================================================
    # Context
    "WorkflowContext",
    # Step Result
    "StepResult",
    "QualityMetrics",
    "ErrorCategory",
    # Step Types
    "Step",
    "StepType",
    "ErrorPolicy",
    "RetryPolicy",
    # Workflow
    "Workflow",
    # Workflow Runner
    "WorkflowRunner",
    "WorkflowResult",
    "WorkflowStatus",
    "StepExecution",
    "get_workflow_runner",
    # Tracked Runner (database persistence)
    "TrackedWorkflowRunner",
    "get_workflow_state",
    "list_workflow_failures",
]
