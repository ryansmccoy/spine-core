# Architecture: Context-First Design

> **Document**: Detailed architecture for Orchestration v2

## Design Philosophy

### Why Context-First?

AWS Step Functions popularized a key insight: **workflow state is THE fundamental primitive**. Every step receives the current state and returns transformations to that state. This enables:

1. **Composability**: Steps don't need to know about each other
2. **Testability**: Steps are pure functions of (context, config) → result
3. **Observability**: Context captures full execution history
4. **Resumability**: Context + checkpoint = restart from any point

### Comparison with Existing Approaches

| Approach | How Steps Communicate | Pros | Cons |
|----------|----------------------|------|------|
| **Direct calls** | A calls B directly | Simple | Tight coupling |
| **Message queue** | A publishes, B subscribes | Decoupled | Complex setup |
| **Database** | A writes, B reads | Persistent | Slow, implicit |
| **Context passing** | Runner passes context | Explicit, testable | Needs runner |

We chose **context passing** because:
- Explicit data flow (no hidden dependencies)
- Pure functions (easy to test)
- Runner controls execution (retry, timeout, logging)
- Natural fit for financial data pipelines

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           User Code                                      │
│   workflow = Workflow(steps=[...])                                       │
│   result = runner.execute(workflow, params={...})                        │
└─────────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                        WorkflowRunner                                    │
│   ┌─────────────────────────────────────────────────────────────────┐   │
│   │  1. Create initial WorkflowContext                               │   │
│   │  2. For each step:                                               │   │
│   │     a. Check dependencies/conditions                             │   │
│   │     b. Execute step with context                                 │   │
│   │     c. Update context with step output                           │   │
│   │     d. Handle errors per policy                                  │   │
│   │  3. Return WorkflowResult                                        │   │
│   └─────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
                                   │
                    ┌──────────────┼──────────────┐
                    │              │              │
                    ▼              ▼              ▼
            ┌───────────┐  ┌───────────┐  ┌───────────┐
            │LambdaStep │  │PipelineStep│ │ChoiceStep │
            │(function) │  │(registry) │  │(condition)│
            └───────────┘  └───────────┘  └───────────┘
                    │              │              │
                    └──────────────┼──────────────┘
                                   │
                                   ▼
                          ┌───────────────┐
                          │  StepResult   │
                          │  - success    │
                          │  - output     │
                          │  - updates    │
                          └───────────────┘
```

## Component Details

### WorkflowContext

The central data structure that flows through execution:

```python
@dataclass
class WorkflowContext:
    # Identity
    run_id: str                       # Unique per execution
    trace_id: str                     # For distributed tracing
    batch_id: str | None              # Group related executions
    
    # Timing
    started_at: datetime
    
    # Data
    params: dict[str, Any]            # User-provided parameters
    step_outputs: dict[str, Any]      # {step_name: output_dict}
    metadata: dict[str, Any]          # System metadata
    
    # Resumption
    checkpoint: CheckpointState | None
    
    # Financial data specific
    partition: PartitionKey | None    # {date, tier, venue, ...}
    as_of_date: date | None           # Business date
    capture_id: str | None            # For idempotency
```

### StepResult

Universal result envelope:

```python
@dataclass
class StepResult:
    # Required
    success: bool
    
    # Output (added to context.step_outputs[step_name])
    output: dict[str, Any]
    
    # Context mutations (merged into context.params)
    context_updates: dict[str, Any] = field(default_factory=dict)
    
    # Error info
    error: str | None = None
    error_category: str | None = None  # For retry logic
    
    # Quality (financial data specific)
    quality: QualityMetrics | None = None
    
    # Observability
    events: list[dict] = field(default_factory=list)
    
    # Routing (for choice steps)
    next_step: str | None = None
```

### Step Types

```python
# Base protocol
class Step(Protocol):
    name: str
    def execute(self, context: WorkflowContext, config: dict) -> StepResult: ...

# Lambda step - inline function
@dataclass
class LambdaStep:
    name: str
    handler: Callable[[WorkflowContext, dict], StepResult]
    config: dict = field(default_factory=dict)
    on_error: ErrorPolicy = ErrorPolicy.STOP
    
# Pipeline step - wraps registered pipeline
@dataclass  
class PipelineStep:
    name: str
    pipeline: str  # Registry key
    params: dict = field(default_factory=dict)
    on_error: ErrorPolicy = ErrorPolicy.STOP
    
# Choice step - conditional branching
@dataclass
class ChoiceStep:
    name: str
    condition: Callable[[WorkflowContext], bool]
    then_step: str
    else_step: str | None = None
```

### WorkflowRunner

The execution engine:

```python
class WorkflowRunner:
    def execute(
        self,
        workflow: Workflow,
        params: dict | None = None,
        checkpoint: CheckpointState | None = None,
        dry_run: bool = False,
    ) -> WorkflowResult:
        """Execute a workflow."""
        
        # 1. Create initial context
        context = WorkflowContext.new(
            params=params,
            checkpoint=checkpoint,
        )
        
        # 2. Execute steps
        for step in self._resolve_execution_order(workflow, context):
            if dry_run:
                # Record what WOULD happen
                continue
                
            # Execute step
            result = self._execute_step(step, context)
            
            # Update context
            context = context.with_step_output(step.name, result.output)
            context = context.with_updates(result.context_updates)
            
            # Handle failure
            if not result.success:
                if step.on_error == ErrorPolicy.STOP:
                    break
        
        # 3. Return result
        return WorkflowResult(...)
```

## Layer Integration

### How It Fits in spine-core

```
packages/spine-core/src/spine/
├── core/                          # Core primitives (unchanged)
│   ├── execution.py               # ExecutionContext
│   ├── manifest.py                # WorkManifest
│   └── ...
│
├── framework/                     # Framework (unchanged)
│   ├── dispatcher.py              # Dispatcher
│   ├── pipelines/                 # Pipeline base
│   └── registry.py                # @register_pipeline
│
└── orchestration/                 # Orchestration (ENHANCED)
    ├── models.py                  # PipelineGroup, PipelineStep (v1, kept)
    ├── runner.py                  # GroupRunner (v1, kept)
    ├── context.py                 # WorkflowContext (NEW)
    ├── steps/                     # Step types (NEW)
    │   ├── base.py                # Step protocol
    │   ├── lambda_step.py         
    │   ├── pipeline_step.py       
    │   └── choice_step.py         
    ├── workflow.py                # Workflow definition (NEW)
    ├── workflow_runner.py         # WorkflowRunner (NEW)
    └── checkpoint.py              # CheckpointState (NEW)
```

### v1 and v2 Coexistence

Both systems work side-by-side:

```python
# v1 imports (still work)
from spine.orchestration import (
    PipelineGroup,
    PipelineStep,
    GroupRunner,
    PlanResolver,
)

# v2 imports (new)
from spine.orchestration import (
    Workflow,
    Step,
    WorkflowRunner,
    WorkflowContext,
)
```

## Design Decisions

### D1: Immutable Context (not mutable)

**Decision**: Context uses "immutable + merge" pattern.

**Rationale**:
- Prevents accidental mutation bugs
- Enables checkpoint/resume (serialize any point)
- Pure functions are easier to test
- Thread-safe for future parallel execution

**Trade-off**: Slightly more verbose (`ctx.with_updates()` vs `ctx.data[key] = val`)

### D2: Pipeline Adapter (not replacement)

**Decision**: Existing pipelines wrapped via `PipelineStep`, not replaced.

**Rationale**:
- Zero migration required for existing code
- Heavy operations (DB, API) stay in pipelines
- Lambdas are for lightweight logic (validation, routing)
- Gradual adoption possible

### D3: Separate Runner (not extend GroupRunner)

**Decision**: New `WorkflowRunner` parallel to `GroupRunner`.

**Rationale**:
- Different execution model (context passing vs independent)
- Avoids breaking changes to v1
- Cleaner separation of concerns
- Can eventually deprecate v1

### D4: Quality Metrics in Result

**Decision**: `StepResult.quality` field for data quality metrics.

**Rationale**:
- Financial data pipelines need quality gates
- Quality metrics flow through context
- Downstream steps can check upstream quality
- Alerts can fire on quality degradation
