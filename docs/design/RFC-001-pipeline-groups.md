# RFC-001: Pipeline Groups and Simple DAG Orchestration

> **Status:** Draft  
> **Author:** Principal Architect  
> **Date:** 2026-01-09  
> **Tier Placement:** Advanced (Tier 3), with opt-in complexity  

---

## Executive Summary

This RFC proposes adding **first-class pipeline grouping and simple DAG semantics** to spine-core. The design introduces a layered, opt-in orchestration architecture that cleanly separates definition, persistence, execution, and presentation—aligning with spine-core's existing framework philosophy.

**Key Deliverables:**
1. Pipeline Groups: Named collections of related pipelines with dependency edges
2. Two interchangeable definition formats: YAML schema and Python DSL
3. Execution policies: sequential (default), parallel with concurrency limits
4. Runnable plan resolution from group specs
5. REST API for CRUD + run + status
6. UI integration with expandable groups and aggregated status

**What This Is NOT:**
- Not a full Airflow/Temporal/Dagster replacement
- No dynamic DAG generation (v1)
- No event triggers (v1)
- No cross-group dependencies (v1)
- No automatic retries at group level (use existing DLQ)

---

## 1. Gap Analysis

### 1.1 What Already Exists

| Capability | Location | Notes |
|------------|----------|-------|
| **Pipeline Registry** | `spine.framework.registry` | `@register_pipeline` decorator, `get_pipeline()`, `list_pipelines()` |
| **Sequential Runner** | `spine.framework.runner.PipelineRunner` | `run_all()` method already runs pipelines in sequence with stop-on-failure |
| **Execution Context** | `spine.core.execution.ExecutionContext` | `batch_id` links related executions; `child()` creates sub-contexts |
| **Dispatcher** | `spine.framework.dispatcher.Dispatcher` | Unified submission interface across tiers |
| **Backfill Orchestrator** | `finra.otc_transparency.BackfillRangePipeline` | Ad-hoc multi-pipeline orchestration (ingest→normalize→aggregate→rolling) |
| **Scheduler** | `market-spine-advanced/.../scheduler.py` | Cron-based scheduling with `next_run_at` |
| **calc_dependencies table** | `core_calc_dependencies` | Schema exists for calc DAG tracking (not yet populated) |
| **LocalBackend** | `market-spine-intermediate/.../local.py` | Thread-based concurrent execution |
| **OrchestratorBackend Protocol** | `...backends/protocol.py` | `submit()`, `cancel()`, `health()`, `start()`, `stop()` |

### 1.2 What's Missing (Gap)

| Gap | Impact | Notes |
|-----|--------|-------|
| **Named Pipeline Groups** | No way to define related pipelines as a logical unit | `BackfillRangePipeline` is hardcoded, not reusable |
| **Declarative Specs** | No YAML/DSL for group definitions | Groups are procedural, not data-driven |
| **Dependency Graph Resolution** | No topological sort for pipeline ordering | `run_all()` is flat sequence, not DAG |
| **Group-level Status** | No aggregation of child execution statuses | Must query each execution individually |
| **Parallel Execution Policy** | No `max_concurrency` at group level | Only individual pipeline concurrency via `logical_key` |
| **Group CRUD API** | No REST endpoints for group management | Would be new surface area |
| **Persistence Layer** | No storage for group specs | Must choose DB vs YAML files |
| **UI Integration** | No expandable group rows in pipeline list | Frontend knows nothing about grouping |

### 1.3 Overlaps and Conflicts

| Overlap | Risk | Mitigation |
|---------|------|------------|
| `batch_id` vs Group Run ID | Confusion about which links executions | Group run creates its own `batch_id`; document relationship |
| `BackfillRangePipeline` vs Groups | Existing orchestrator may conflict | Migrate to group-based definition or keep as domain-specific |
| `core_calc_dependencies` vs Group deps | Different abstractions for dependencies | Calc deps are data lineage; group deps are execution order |
| `ScheduleManager` vs Group scheduling | Should groups be schedulable? | v1: Schedule individual groups like pipelines |

---

## 2. Roadmap Placement: Advanced Tier

### 2.1 Justification

| Factor | Basic | Intermediate | **Advanced** | Full |
|--------|-------|--------------|--------------|------|
| Cognitive Load | Low | Medium | **Medium-High** | High |
| Backend Requirement | Sync | LocalBackend | **Local + Celery** | Plugin system |
| Database | SQLite | PostgreSQL | **PostgreSQL** | PostgreSQL |
| Concurrency | None | Thread pool | **Concurrency guards** | Multi-tenant |
| Target User | Solo dev | Small team | **Platform team** | Enterprise |

**Pipeline Groups belong in Advanced because:**

1. **Requires concurrency guards**: Parallel execution needs `logical_key` semantics from Advanced
2. **Requires event sourcing**: Group status aggregation benefits from `execution_events`
3. **Requires DLQ**: Failed group pipelines should flow to dead letter queue
4. **Natural evolution**: Advanced already has `BackfillRangePipeline` patterns
5. **Intermediate is simpler**: Teams using Intermediate likely don't need DAG complexity yet

### 2.2 Opt-In Philosophy

Pipeline Groups are **opt-in**:
- Existing `spine run <pipeline>` works unchanged
- Groups are a new abstraction layered on top
- No migration required for existing pipelines
- Can be adopted gradually per-domain

---

## 3. Architecture-Aligned Design

### 3.1 Conceptual Model

```
┌─────────────────────────────────────────────────────────────┐
│                    PipelineGroup                             │
│                                                              │
│  name: "finra.weekly_refresh"                                │
│  description: "Weekly FINRA data refresh"                    │
│  version: 1                                                  │
│                                                              │
│  ┌─────────────┐     ┌─────────────┐     ┌─────────────┐   │
│  │   ingest    │ ──▶ │  normalize  │ ──▶ │  aggregate  │   │
│  └─────────────┘     └─────────────┘     └─────────────┘   │
│                                                ↓             │
│                                          ┌─────────────┐    │
│                                          │   rolling   │    │
│                                          └─────────────┘    │
│                                                              │
│  policy:                                                     │
│    execution: sequential (default)                           │
│    on_failure: stop (default)                               │
└─────────────────────────────────────────────────────────────┘
```

**What a Pipeline Group IS:**
- A named, versioned collection of pipelines
- Has explicit dependency edges (or implicit sequential order)
- Has execution policies (sequential/parallel, stop/continue on failure)
- Produces a single Group Run with aggregated status
- Is a unit of deployment and scheduling

**What a Pipeline Group is NOT:**
- Not a replacement for pipeline logic (pipelines stay in domains)
- Not a dynamic DAG (structure is static at definition time)
- Not cross-domain (each group belongs to one domain)
- Not a workflow engine (no conditionals, loops, or branching)

### 3.2 Definition Layer

#### 3.2.1 YAML Schema

```yaml
# groups/finra_weekly_refresh.yaml
apiVersion: spine.io/v1
kind: PipelineGroup
metadata:
  name: finra.weekly_refresh
  description: Weekly FINRA OTC data refresh
  domain: finra.otc_transparency
  version: 1
  tags:
    - finra
    - weekly
spec:
  # Parameters that apply to all pipelines (can be overridden)
  defaults:
    tier: "{{ params.tier }}"
    week_ending: "{{ params.week_ending }}"
    force: false
  
  # Pipeline stages (ordered by dependencies or sequence)
  pipelines:
    - name: ingest
      pipeline: finra.otc_transparency.ingest_week
      params:
        source_type: api
      # No depends_on = runs first
    
    - name: normalize
      pipeline: finra.otc_transparency.normalize_week
      depends_on:
        - ingest
    
    - name: aggregate
      pipeline: finra.otc_transparency.aggregate_week
      depends_on:
        - normalize
    
    - name: rolling
      pipeline: finra.otc_transparency.compute_rolling
      depends_on:
        - aggregate
  
  # Execution policy
  policy:
    execution: sequential  # or "parallel"
    max_concurrency: 4     # only applies if execution=parallel
    on_failure: stop       # or "continue"
    timeout_minutes: 60    # optional group timeout
```

#### 3.2.2 Python DSL

```python
# Alternative: Define in Python (for dynamic parameter calculation)
from spine.orchestration import PipelineGroup, PipelineStep

group = PipelineGroup(
    name="finra.weekly_refresh",
    domain="finra.otc_transparency",
    version=1,
)

# Fluent API
group.add("ingest", "finra.otc_transparency.ingest_week")
group.add("normalize", "finra.otc_transparency.normalize_week", depends_on=["ingest"])
group.add("aggregate", "finra.otc_transparency.aggregate_week", depends_on=["normalize"])
group.add("rolling", "finra.otc_transparency.compute_rolling", depends_on=["aggregate"])

# Or declarative
group = PipelineGroup.from_steps(
    name="finra.weekly_refresh",
    steps=[
        PipelineStep("ingest", "finra.otc_transparency.ingest_week"),
        PipelineStep("normalize", "finra.otc_transparency.normalize_week", depends_on=["ingest"]),
        PipelineStep("aggregate", "finra.otc_transparency.aggregate_week", depends_on=["normalize"]),
        PipelineStep("rolling", "finra.otc_transparency.compute_rolling", depends_on=["aggregate"]),
    ],
)

# Register with framework
from spine.orchestration import register_group
register_group(group)
```

### 3.3 Persistence Strategy

#### 3.3.1 Feature Flag Approach

```python
# config.py
class OrchestrationSettings(BaseSettings):
    # Where to store group definitions
    group_storage: Literal["database", "yaml"] = "yaml"
    
    # Path for YAML storage (relative to project root)
    groups_path: str = "groups/"
    
    # Whether to validate YAML against schema on load
    validate_groups: bool = True
```

#### 3.3.2 Database Schema (when `group_storage=database`)

```sql
-- migrations/005_pipeline_groups.sql

CREATE TABLE pipeline_groups (
    id TEXT PRIMARY KEY,                -- ULID
    name TEXT NOT NULL UNIQUE,          -- e.g., "finra.weekly_refresh"
    domain TEXT NOT NULL,               -- e.g., "finra.otc_transparency"
    version INT NOT NULL DEFAULT 1,
    description TEXT,
    spec JSONB NOT NULL,                -- Full YAML content as JSON
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by TEXT,
    is_active BOOLEAN NOT NULL DEFAULT true
);

CREATE INDEX idx_pipeline_groups_domain ON pipeline_groups(domain);
CREATE INDEX idx_pipeline_groups_active ON pipeline_groups(is_active) WHERE is_active = true;

-- Group run tracking
CREATE TABLE group_runs (
    id TEXT PRIMARY KEY,                -- ULID
    group_id TEXT NOT NULL REFERENCES pipeline_groups(id),
    group_name TEXT NOT NULL,           -- Denormalized for query efficiency
    group_version INT NOT NULL,
    params JSONB,
    status TEXT NOT NULL DEFAULT 'pending',  -- pending, running, completed, failed, cancelled
    trigger_source TEXT NOT NULL,       -- cli, api, scheduler
    batch_id TEXT NOT NULL,             -- Links to execution.batch_id
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_group_runs_status ON group_runs(status);
CREATE INDEX idx_group_runs_batch_id ON group_runs(batch_id);

-- Junction: which executions belong to which group run
CREATE TABLE group_run_executions (
    group_run_id TEXT NOT NULL REFERENCES group_runs(id),
    execution_id TEXT NOT NULL REFERENCES executions(id),
    step_name TEXT NOT NULL,            -- e.g., "ingest", "normalize"
    sequence_order INT NOT NULL,        -- Order in execution plan
    PRIMARY KEY (group_run_id, execution_id)
);
```

#### 3.3.3 YAML Storage (when `group_storage=yaml`)

```
project-root/
├── groups/
│   ├── finra/
│   │   ├── weekly_refresh.yaml
│   │   └── backfill.yaml
│   └── market_data/
│       └── daily_prices.yaml
```

- Loaded at startup (cached)
- Changes detected via file watcher (optional) or CLI reload
- Version controlled in git

### 3.4 Execution Model

#### 3.4.1 Plan Resolution

```python
# spine/orchestration/planner.py

@dataclass
class ExecutionPlan:
    """Resolved plan for executing a pipeline group."""
    group_name: str
    group_version: int
    batch_id: str
    steps: list[PlannedStep]
    policy: ExecutionPolicy

@dataclass
class PlannedStep:
    """A single step in the execution plan."""
    step_name: str
    pipeline_name: str
    params: dict[str, Any]
    depends_on: list[str]  # Step names
    sequence_order: int    # Topologically sorted order

class PlanResolver:
    """Resolves a PipelineGroup into an ExecutionPlan."""
    
    def resolve(
        self,
        group: PipelineGroup,
        params: dict[str, Any],
    ) -> ExecutionPlan:
        """
        Resolve group definition + runtime params into executable plan.
        
        1. Validate all pipelines exist in registry
        2. Validate dependency graph is a DAG (no cycles)
        3. Topological sort steps
        4. Merge default params with step params
        5. Return executable plan
        """
        # Validate pipelines exist
        for step in group.steps:
            try:
                get_pipeline(step.pipeline)
            except KeyError:
                raise PlanResolutionError(
                    f"Pipeline '{step.pipeline}' not found for step '{step.name}'"
                )
        
        # Validate DAG (detect cycles)
        self._validate_dag(group.steps)
        
        # Topological sort
        sorted_steps = self._topological_sort(group.steps)
        
        # Build planned steps with merged params
        planned = []
        for order, step in enumerate(sorted_steps):
            merged_params = {
                **group.defaults,
                **params,
                **step.params,
            }
            planned.append(PlannedStep(
                step_name=step.name,
                pipeline_name=step.pipeline,
                params=merged_params,
                depends_on=step.depends_on,
                sequence_order=order,
            ))
        
        return ExecutionPlan(
            group_name=group.name,
            group_version=group.version,
            batch_id=new_batch_id(f"group_{group.name}"),
            steps=planned,
            policy=group.policy,
        )
```

#### 3.4.2 Plan Executor

```python
# spine/orchestration/executor.py

class GroupExecutor:
    """Executes a resolved plan."""
    
    def __init__(self, dispatcher: Dispatcher):
        self.dispatcher = dispatcher
    
    def execute(self, plan: ExecutionPlan) -> GroupRunResult:
        """
        Execute plan according to policy.
        
        Sequential: Run steps one-by-one in topological order
        Parallel: Run independent steps concurrently (respecting deps)
        """
        if plan.policy.execution == "sequential":
            return self._execute_sequential(plan)
        else:
            return self._execute_parallel(plan)
    
    def _execute_sequential(self, plan: ExecutionPlan) -> GroupRunResult:
        """Simple sequential execution with stop-on-failure."""
        results: dict[str, Execution] = {}
        
        for step in plan.steps:
            execution = self.dispatcher.submit(
                pipeline=step.pipeline_name,
                params=step.params,
                trigger_source=TriggerSource.SCHEDULER,
                batch_id=plan.batch_id,
            )
            
            results[step.step_name] = execution
            
            if execution.status == PipelineStatus.FAILED:
                if plan.policy.on_failure == "stop":
                    break
        
        return GroupRunResult(
            plan=plan,
            executions=results,
            status=self._aggregate_status(results),
        )
    
    def _execute_parallel(self, plan: ExecutionPlan) -> GroupRunResult:
        """
        Parallel execution respecting dependencies.
        
        Uses ThreadPoolExecutor with max_concurrency limit.
        Steps wait for their dependencies before starting.
        """
        from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
        
        results: dict[str, Execution] = {}
        completed: set[str] = set()
        futures: dict[Future, str] = {}
        
        with ThreadPoolExecutor(max_workers=plan.policy.max_concurrency) as executor:
            while len(completed) < len(plan.steps):
                # Find ready steps (all deps completed successfully)
                ready = [
                    step for step in plan.steps
                    if step.step_name not in completed
                    and step.step_name not in futures.values()
                    and all(dep in completed for dep in step.depends_on)
                ]
                
                # Submit ready steps
                for step in ready:
                    if len(futures) >= plan.policy.max_concurrency:
                        break
                    future = executor.submit(self._run_step, step, plan.batch_id)
                    futures[future] = step.step_name
                
                # Wait for at least one to complete
                if futures:
                    done, _ = wait(futures.keys(), return_when=FIRST_COMPLETED)
                    for future in done:
                        step_name = futures.pop(future)
                        execution = future.result()
                        results[step_name] = execution
                        completed.add(step_name)
                        
                        # Check failure policy
                        if execution.status == PipelineStatus.FAILED:
                            if plan.policy.on_failure == "stop":
                                # Cancel remaining futures
                                for f in futures:
                                    f.cancel()
                                break
        
        return GroupRunResult(
            plan=plan,
            executions=results,
            status=self._aggregate_status(results),
        )
```

### 3.5 API Surface

#### 3.5.1 Group Management

```python
# api/routes/groups.py

router = APIRouter(prefix="/groups", tags=["groups"])

@router.get("/")
async def list_groups(
    domain: str | None = None,
    active_only: bool = True,
) -> list[GroupSummary]:
    """List all pipeline groups."""
    ...

@router.get("/{group_name}")
async def get_group(group_name: str) -> GroupDetail:
    """Get group definition with steps."""
    ...

@router.post("/")
async def create_group(body: CreateGroupRequest) -> GroupDetail:
    """Create a new group (database storage only)."""
    ...

@router.put("/{group_name}")
async def update_group(group_name: str, body: UpdateGroupRequest) -> GroupDetail:
    """Update group definition (creates new version)."""
    ...

@router.delete("/{group_name}")
async def delete_group(group_name: str) -> None:
    """Soft-delete group (set is_active=false)."""
    ...
```

#### 3.5.2 Group Execution

```python
@router.post("/{group_name}/run")
async def run_group(
    group_name: str,
    body: RunGroupRequest,
) -> GroupRunResponse:
    """
    Trigger group execution.
    
    Returns immediately with group_run_id.
    Poll /groups/runs/{group_run_id} for status.
    """
    ...

@router.get("/runs")
async def list_group_runs(
    group_name: str | None = None,
    status: str | None = None,
    limit: int = 50,
) -> list[GroupRunSummary]:
    """List group runs with optional filters."""
    ...

@router.get("/runs/{group_run_id}")
async def get_group_run(group_run_id: str) -> GroupRunDetail:
    """
    Get group run with all child executions.
    
    Response includes:
    - Overall status (aggregated)
    - Per-step status and execution_id
    - Timing information
    """
    ...

@router.post("/runs/{group_run_id}/cancel")
async def cancel_group_run(group_run_id: str) -> None:
    """Cancel a running group (best-effort)."""
    ...
```

#### 3.5.3 Response Schemas

```python
# api/schemas/groups.py

class GroupSummary(BaseModel):
    name: str
    domain: str
    version: int
    description: str | None
    step_count: int
    is_active: bool

class GroupDetail(GroupSummary):
    spec: dict  # Full YAML/JSON spec
    created_at: datetime
    updated_at: datetime

class GroupRunSummary(BaseModel):
    id: str
    group_name: str
    status: str  # pending, running, completed, failed, cancelled
    trigger_source: str
    started_at: datetime | None
    completed_at: datetime | None
    duration_seconds: float | None

class StepStatus(BaseModel):
    step_name: str
    pipeline_name: str
    execution_id: str | None
    status: str
    started_at: datetime | None
    completed_at: datetime | None
    error: str | None

class GroupRunDetail(GroupRunSummary):
    group_version: int
    params: dict
    batch_id: str
    steps: list[StepStatus]
    error: str | None
```

### 3.6 UI Implications

#### 3.6.1 Pipelines View Changes

```
┌─────────────────────────────────────────────────────────────────┐
│ Pipelines                                           [Run Group] │
├─────────────────────────────────────────────────────────────────┤
│ ▼ finra.weekly_refresh (Group)           ● Completed   2m 34s  │
│   ├─ ingest_week                         ● Completed      45s  │
│   ├─ normalize_week                      ● Completed      18s  │
│   ├─ aggregate_week                      ● Completed      32s  │
│   └─ compute_rolling                     ● Completed      59s  │
│                                                                 │
│ ▶ market_data.daily_ingest (Group)       ○ Pending            │
│                                                                 │
│   finra.otc_transparency.ingest_week     ● Completed      45s  │
│   reference.exchange_calendar.sync       ● Completed       2s  │
└─────────────────────────────────────────────────────────────────┘
```

**UI Features:**
- Expandable group rows (triangle toggle)
- Nested pipeline list within groups
- Aggregated status badge (uses worst child status)
- "Run Group" action triggers `/groups/{name}/run`
- Individual pipelines can still be run directly
- Status polling via `/groups/runs/{id}` (no WebSocket in v1)

#### 3.6.2 Status Aggregation Rules

| Child Statuses | Group Status |
|----------------|--------------|
| All completed | ✅ Completed |
| Any running | 🔄 Running |
| Any failed (none running) | ❌ Failed |
| All pending | ⏳ Pending |
| Any cancelled | 🚫 Cancelled |

---

## 4. How This Avoids Becoming Airflow/Temporal

| Feature | spine-core Groups | Airflow/Temporal |
|---------|-------------------|------------------|
| **DAG Complexity** | Static, simple deps | Dynamic, complex |
| **Scheduling** | Cron via existing ScheduleManager | Built-in scheduler with catchup |
| **Retries** | Defer to DLQ | Automatic retry policies |
| **Branching** | ❌ Not supported | Full conditionals |
| **Loops** | ❌ Not supported | Foreach, while |
| **External Events** | ❌ Not supported (v1) | Sensors, triggers |
| **Cross-Group Deps** | ❌ Not supported (v1) | DAG dependencies |
| **UI** | Minimal, status-focused | Full DAG visualization |
| **State** | Per-execution in DB | Full task state machine |
| **Workers** | Existing backends | Dedicated worker fleet |

**Design Philosophy:**
> "Pipeline Groups are for **organizing** related pipelines, not for **orchestrating** complex workflows."

If you need:
- Dynamic branching → Use a domain-specific orchestrator pipeline
- Event triggers → Use external scheduler (cron, k8s CronJob)
- Complex retries → Use DLQ + manual replay
- Cross-domain DAGs → Model as separate groups or orchestrator pipeline

---

## 5. Incremental Adoption Strategy

### 5.1 Migration Path

**Week 1-2: Core Abstractions**
1. Add `PipelineGroup`, `PipelineStep`, `ExecutionPolicy` dataclasses to `spine.orchestration`
2. Add `PlanResolver` with DAG validation and topological sort
3. Add unit tests for plan resolution

**Week 3-4: Persistence Layer**
1. Add migrations for `pipeline_groups`, `group_runs`, `group_run_executions`
2. Implement `GroupRepository` with CRUD operations
3. Add YAML loader with schema validation
4. Feature flag for storage choice

**Week 5-6: Execution Layer**
1. Add `GroupExecutor` with sequential execution
2. Integrate with existing `Dispatcher`
3. Add parallel execution (uses `ThreadPoolExecutor`)
4. Add status aggregation

**Week 7-8: API + CLI**
1. Add FastAPI routes for groups
2. Add `spine groups list`, `spine groups run <name>`, `spine groups status <id>`
3. Add OpenAPI schemas

**Week 9-10: UI Integration**
1. Add expandable group rows to Pipelines view
2. Add "Run Group" action
3. Add status polling

### 5.2 Backward Compatibility

| Existing Feature | Impact | Migration |
|------------------|--------|-----------|
| `@register_pipeline` | ✅ Unchanged | None |
| `spine run <pipeline>` | ✅ Unchanged | None |
| `Dispatcher.submit()` | ✅ Unchanged | None |
| `BackfillRangePipeline` | ⚠️ Candidate for migration | Optional: convert to group |
| `batch_id` semantics | ✅ Enhanced | Groups use batch_id |
| Existing executions | ✅ Unchanged | No migration |

### 5.3 What's NOT Included in v1

| Feature | Why Excluded | Future Phase |
|---------|--------------|--------------|
| Dynamic DAGs | Complexity, maintenance burden | v2 maybe |
| Event triggers | Requires event bus | v2 |
| Cross-group deps | Complexity | v2 |
| Group-level retries | Use DLQ instead | v2 |
| WebSocket status | Polling is simpler | v2 |
| Graph visualization | UI complexity | v2 |
| Parameterized groups | Template complexity | v2 |

---

## 6. File Structure

```
packages/
└── spine-core/
    └── src/spine/
        ├── orchestration/              # NEW MODULE
        │   ├── __init__.py
        │   ├── models.py               # PipelineGroup, PipelineStep, ExecutionPolicy
        │   ├── registry.py             # register_group(), get_group(), list_groups()
        │   ├── loader.py               # YAML loader, schema validation
        │   ├── planner.py              # PlanResolver, topological sort
        │   ├── executor.py             # GroupExecutor
        │   └── exceptions.py           # GroupNotFoundError, CycleDetectedError, etc.
        └── framework/
            └── (existing unchanged)

market-spine-advanced/
├── migrations/
│   ├── 005_pipeline_groups.sql         # NEW
│   ├── 006_group_runs.sql              # NEW
│   └── 007_group_run_executions.sql    # NEW
├── src/market_spine/
│   ├── api/routes/
│   │   └── groups.py                   # NEW
│   ├── repositories/
│   │   └── groups.py                   # NEW
│   └── services/
│       └── groups.py                   # NEW
└── groups/                             # NEW - YAML storage
    └── finra/
        └── weekly_refresh.yaml

trading-desktop/
└── src/
    ├── components/
    │   └── PipelineGroupRow.tsx        # NEW
    └── hooks/
        └── useGroupStatus.ts           # NEW - polling hook
```

---

## 7. Final Recommendation

### 7.1 Decision

**Implement in Advanced Tier, phased approach:**

| Phase | Scope | Timeline |
|-------|-------|----------|
| Phase 1 | Core abstractions + YAML loading | 2 weeks |
| Phase 2 | Sequential execution + CLI | 2 weeks |
| Phase 3 | API + persistence | 2 weeks |
| Phase 4 | Parallel execution | 1 week |
| Phase 5 | UI integration | 2 weeks |

### 7.2 Prerequisites

1. **Advanced tier migrations must be stable** - Groups depend on `executions` table
2. **LocalBackend must support concurrent executions** - Already exists in Intermediate
3. **Existing test coverage** - Don't break existing pipeline execution

### 7.3 Risks and Mitigations

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Over-engineering | Medium | High | Stick to simple DAG, no dynamic features |
| Adoption friction | Low | Medium | Clear migration docs, backward compatible |
| Performance bottleneck | Low | Medium | Parallel execution with limits |
| UI complexity | Medium | Medium | Simple expandable rows, no fancy graphs |

### 7.4 Success Metrics

1. **Adoption**: At least one domain uses groups within 30 days
2. **Reliability**: Group execution success rate ≥ 99%
3. **Performance**: Group overhead < 100ms per step
4. **Developer Experience**: New group definition < 15 minutes

---

## Appendix A: Example YAML Definitions

### A.1 FINRA Weekly Refresh

```yaml
apiVersion: spine.io/v1
kind: PipelineGroup
metadata:
  name: finra.weekly_refresh
  domain: finra.otc_transparency
  version: 1
  description: |
    Full weekly refresh for FINRA OTC transparency data.
    Runs ingest → normalize → aggregate → rolling for all tiers.
spec:
  defaults:
    tier: "{{ params.tier }}"
    week_ending: "{{ params.week_ending }}"
  
  pipelines:
    - name: ingest
      pipeline: finra.otc_transparency.ingest_week
      params:
        source_type: api
    
    - name: normalize
      pipeline: finra.otc_transparency.normalize_week
      depends_on: [ingest]
    
    - name: aggregate
      pipeline: finra.otc_transparency.aggregate_week
      depends_on: [normalize]
    
    - name: rolling
      pipeline: finra.otc_transparency.compute_rolling
      depends_on: [aggregate]
    
    - name: venue_share
      pipeline: finra.otc_transparency.compute_venue_share
      depends_on: [normalize]  # Parallel with aggregate
  
  policy:
    execution: parallel
    max_concurrency: 2
    on_failure: continue
```

### A.2 Market Data Daily Prices

```yaml
apiVersion: spine.io/v1
kind: PipelineGroup
metadata:
  name: market_data.daily_prices
  domain: market_data
  version: 1
  description: Daily price ingestion for configured symbols
spec:
  defaults:
    source: "alpha_vantage"
  
  pipelines:
    - name: calendar_sync
      pipeline: reference.exchange_calendar.sync
      params:
        exchange: XNYS
    
    - name: ingest_prices
      pipeline: market_data.ingest_prices
      depends_on: [calendar_sync]
      params:
        symbols: "{{ params.symbols }}"
  
  policy:
    execution: sequential
    on_failure: stop
```

---

## Appendix B: API Examples

### B.1 Create Group Run

```bash
POST /groups/finra.weekly_refresh/run
Content-Type: application/json

{
  "params": {
    "tier": "NMS_TIER_1",
    "week_ending": "2026-01-03"
  }
}
```

Response:
```json
{
  "id": "01JQXK3V2H...",
  "group_name": "finra.weekly_refresh",
  "status": "pending",
  "trigger_source": "api",
  "batch_id": "group_finra.weekly_refresh_20260109T120000_abc123",
  "steps": [
    {"step_name": "ingest", "status": "pending", "execution_id": null},
    {"step_name": "normalize", "status": "pending", "execution_id": null},
    {"step_name": "aggregate", "status": "pending", "execution_id": null},
    {"step_name": "rolling", "status": "pending", "execution_id": null}
  ]
}
```

### B.2 Get Group Run Status

```bash
GET /groups/runs/01JQXK3V2H...
```

Response:
```json
{
  "id": "01JQXK3V2H...",
  "group_name": "finra.weekly_refresh",
  "group_version": 1,
  "status": "running",
  "trigger_source": "api",
  "batch_id": "group_finra.weekly_refresh_20260109T120000_abc123",
  "started_at": "2026-01-09T12:00:05Z",
  "completed_at": null,
  "duration_seconds": 45.2,
  "steps": [
    {
      "step_name": "ingest",
      "pipeline_name": "finra.otc_transparency.ingest_week",
      "execution_id": "exec_001",
      "status": "completed",
      "started_at": "2026-01-09T12:00:05Z",
      "completed_at": "2026-01-09T12:00:30Z"
    },
    {
      "step_name": "normalize",
      "pipeline_name": "finra.otc_transparency.normalize_week",
      "execution_id": "exec_002",
      "status": "running",
      "started_at": "2026-01-09T12:00:31Z",
      "completed_at": null
    },
    {
      "step_name": "aggregate",
      "pipeline_name": "finra.otc_transparency.aggregate_week",
      "execution_id": null,
      "status": "pending",
      "started_at": null,
      "completed_at": null
    },
    {
      "step_name": "rolling",
      "pipeline_name": "finra.otc_transparency.compute_rolling",
      "execution_id": null,
      "status": "pending",
      "started_at": null,
      "completed_at": null
    }
  ]
}
```

---

*End of RFC-001*
