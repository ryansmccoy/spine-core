"""
Spine Orchestration — Workflow execution engine.

WHY
───
Raw pipelines (``Runnable.submit_pipeline_sync``) execute one unit of work.
Orchestration layers **multiple** units into a directed workflow with context
passing, conditional branching, error policies, and optional persistence.

ARCHITECTURE
────────────
::

    Workflow (DAG of Steps)
      ├── Step.lambda_()          ─ inline handler
      ├── Step.pipeline()         ─ wraps registered Pipeline
      ├── Step.from_function()    ─ plain-function adapter
      ├── Step.choice()           ─ conditional branch
      ├── Step.wait()             ─ timed pause
      └── Step.map()              ─ fan-out / fan-in

    WorkflowRunner         ─ executes sequentially or parallel (DAG)
    TrackedWorkflowRunner  ─ + database persistence
    WorkflowContext        ─ immutable context flowing step-to-step
    StepResult             ─ ok / fail / skip with quality metrics

    Supporting:
      templates.py         ─ pre-built workflow patterns
      workflow_yaml.py     ─ YAML ↔ Python round-trip
      playground.py        ─ interactive debugger with snapshots
      recorder.py          ─ capture & replay for regression testing
      linter.py            ─ static analysis of workflow graphs
      visualizer.py        ─ Mermaid, ASCII, and summary renderers

MODULE MAP (recommended reading order)
──────────────────────────────────────
1. exceptions.py         ─ error hierarchy
2. step_result.py        ─ StepResult + QualityMetrics
3. step_types.py         ─ Step dataclass + factory methods
4. step_adapters.py      ─ plain-function → step handler adapter
5. workflow_context.py   ─ immutable context object
6. workflow.py           ─ Workflow dataclass + dependency helpers
7. workflow_runner.py    ─ sequential + parallel execution engine
8. workflow_registry.py  ─ global name → Workflow lookup
9. tracked_runner.py     ─ database-backed runner wrapper
10. managed_workflow.py  ─ high-level import-and-manage API
11. templates.py         ─ pre-built workflow patterns
12. workflow_yaml.py     ─ YAML serialization / deserialization
13. playground.py        ─ interactive step-by-step debugger
14. container_runnable.py ─ DI-container Runnable bridge

Tier availability:
- Basic: Workflow, Step (lambda, pipeline, from_function), WorkflowRunner
- Intermediate: + ChoiceStep (conditional branching)
- Advanced: + WaitStep, MapStep, Checkpointing, Resume

Example (classic — framework-aware handler):
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

Example (plain function — framework-agnostic):
    from spine.orchestration import Workflow, Step, workflow_step

    @workflow_step(name="validate")
    def validate_records(record_count: int, threshold: int = 100) -> dict:
        passed = record_count >= threshold
        return {"passed": passed, "count": record_count}

    # Direct call (notebook, script, market-spine — no framework):
    validate_records(record_count=42)

    # As a workflow step:
    workflow = Workflow(
        name="my.pipeline",
        steps=[
            Step.from_function("ingest", fetch_data),
            validate_records.as_step(),
        ],
    )
"""

from spine.orchestration.step_adapters import (
    WorkflowStepMeta,
    adapt_function,
    get_step_meta,
    is_workflow_step,
    workflow_step,
)

from spine.orchestration.exceptions import (
    CycleDetectedError,
    GroupError,
    GroupNotFoundError,
    InvalidGroupSpecError,
    PlanResolutionError,
    StepNotFoundError,
)
from spine.orchestration.step_result import (
    ErrorCategory,
    QualityMetrics,
    StepResult,
)
from spine.orchestration.step_types import (
    ErrorPolicy,
    RetryPolicy,
    Step,
    StepType,
    resolve_callable_ref,
)

# Tracked runner (with database persistence)
from spine.orchestration.tracked_runner import (
    TrackedWorkflowRunner,
    get_workflow_state,
    list_workflow_failures,
)

# Managed workflows (high-level import-and-manage API)
from spine.orchestration.managed_workflow import (
    ManagedPipeline,
    ManagedWorkflow,
    manage,
)

from spine.orchestration.workflow import (
    ExecutionMode,
    FailurePolicy,
    Workflow,
    WorkflowExecutionPolicy,
)
from spine.orchestration.workflow_context import WorkflowContext
from spine.orchestration.workflow_registry import (
    WorkflowNotFoundError,
    clear_workflow_registry,
    get_workflow,
    list_workflows,
    register_workflow,
    workflow_exists,
)
from spine.orchestration.workflow_runner import (
    StepExecution,
    WorkflowResult,
    WorkflowRunner,
    WorkflowStatus,
    get_workflow_runner,
)

# workflow_yaml is lazy-loaded — requires pydantic (optional dep)
# Access WorkflowSpec or validate_yaml_workflow via __getattr__

from spine.orchestration.container_runnable import ContainerRunnable
from spine.orchestration.playground import StepSnapshot, WorkflowPlayground
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

# Linter (static analysis)
from spine.orchestration.linter import (
    LintDiagnostic,
    LintResult,
    Severity,
    clear_custom_rules,
    lint_workflow,
    list_lint_rules,
    register_lint_rule,
)

# Recorder (capture and replay)
from spine.orchestration.recorder import (
    RecordingRunner,
    ReplayResult,
    StepDiff,
    StepRecording,
    WorkflowRecording,
    replay,
)

# Visualizer (Mermaid, ASCII, summary)
from spine.orchestration.visualizer import (
    visualize_ascii,
    visualize_mermaid,
    visualize_summary,
)

# Composition operators
from spine.orchestration.composition import (
    chain,
    conditional,
    merge_workflows,
    parallel,
    retry,
)

# Dry-run analysis
from spine.orchestration.dry_run import (
    DryRunResult,
    DryRunStep,
    clear_cost_registry,
    dry_run,
    register_cost_estimate,
    register_estimator,
)

# Test harness
from spine.orchestration.testing import (
    FailingRunnable,
    ScriptedRunnable,
    StubRunnable,
    WorkflowAssertionError,
    assert_no_failures,
    assert_step_count,
    assert_step_output,
    assert_steps_ran,
    assert_workflow_completed,
    assert_workflow_failed,
    make_context,
    make_runner,
    make_workflow,
)

# LLM provider protocol
from spine.orchestration.llm import (
    BudgetExhaustedError,
    LLMProvider,
    LLMResponse,
    LLMRouter,
    Message,
    MockLLMProvider,
    Role,
    TokenBudget,
    TokenUsage,
)

__all__ = [
    # Exceptions
    "GroupError",
    "GroupNotFoundError",
    "CycleDetectedError",
    "PlanResolutionError",
    "StepNotFoundError",
    "InvalidGroupSpecError",
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
    "resolve_callable_ref",
    # Plain Function Adapters
    "adapt_function",
    "workflow_step",
    "is_workflow_step",
    "get_step_meta",
    "WorkflowStepMeta",
    # Workflow
    "Workflow",
    "WorkflowExecutionPolicy",
    "ExecutionMode",
    "FailurePolicy",
    # Workflow Registry
    "register_workflow",
    "get_workflow",
    "list_workflows",
    "workflow_exists",
    "clear_workflow_registry",
    "WorkflowNotFoundError",
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
    # Managed Workflows (high-level import-and-manage API)
    "ManagedWorkflow",
    "ManagedPipeline",
    "manage",
    # YAML support
    "WorkflowSpec",
    "validate_yaml_workflow",
    # Container bridge
    "ContainerRunnable",
    # Playground (interactive executor)
    "WorkflowPlayground",
    "StepSnapshot",
    # Templates
    "etl_pipeline",
    "fan_out_fan_in",
    "conditional_branch",
    "retry_wrapper",
    "scheduled_batch",
    "register_template",
    "get_template",
    "list_templates",
    # Linter (static analysis)
    "lint_workflow",
    "LintResult",
    "LintDiagnostic",
    "Severity",
    "register_lint_rule",
    "list_lint_rules",
    "clear_custom_rules",
    # Recorder (capture and replay)
    "RecordingRunner",
    "WorkflowRecording",
    "StepRecording",
    "replay",
    "ReplayResult",
    "StepDiff",
    # Visualizer
    "visualize_mermaid",
    "visualize_ascii",
    "visualize_summary",
    # Composition operators
    "chain",
    "parallel",
    "conditional",
    "retry",
    "merge_workflows",
    # Dry-run analysis
    "dry_run",
    "DryRunResult",
    "DryRunStep",
    "register_cost_estimate",
    "register_estimator",
    "clear_cost_registry",
    # Test harness
    "StubRunnable",
    "FailingRunnable",
    "ScriptedRunnable",
    "WorkflowAssertionError",
    "assert_workflow_completed",
    "assert_workflow_failed",
    "assert_step_output",
    "assert_step_count",
    "assert_no_failures",
    "assert_steps_ran",
    "make_workflow",
    "make_context",
    "make_runner",
    # LLM provider protocol
    "LLMProvider",
    "LLMResponse",
    "LLMRouter",
    "Message",
    "MockLLMProvider",
    "Role",
    "TokenUsage",
    "TokenBudget",
    "BudgetExhaustedError",
]


# Lazy imports for optional-dependency modules
_LAZY_IMPORTS = {
    "WorkflowSpec": "spine.orchestration.workflow_yaml",
    "validate_yaml_workflow": "spine.orchestration.workflow_yaml",
}


def __getattr__(name: str):
    if name in _LAZY_IMPORTS:
        import importlib

        module = importlib.import_module(_LAZY_IMPORTS[name])
        return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
