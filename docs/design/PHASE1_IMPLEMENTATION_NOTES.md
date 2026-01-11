# Phase 1 Implementation Notes: Pipeline Groups & DAG Orchestration

## Overview

This document captures the architectural decisions, integration points, and implementation details for Phase 1 of RFC-001 (Pipeline Groups and Simple DAG Orchestration).

## Module Structure

```
packages/spine-core/src/spine/orchestration/
├── __init__.py        # Public API exports
├── exceptions.py      # Exception hierarchy (inherits from SpineError)
├── models.py          # Data models (PipelineGroup, PipelineStep, ExecutionPolicy, etc.)
├── registry.py        # Group registration (mirrors spine.framework.registry pattern)
├── planner.py         # DAG validation and plan resolution
└── loader.py          # YAML loading and validation
```

## Integration Points

### 1. Exception Hierarchy

All orchestration exceptions inherit from `spine.framework.exceptions.SpineError`:

```
SpineError (spine.framework.exceptions)
└── GroupError (spine.orchestration.exceptions)
    ├── GroupNotFoundError
    ├── CycleDetectedError
    ├── PlanResolutionError
    ├── StepNotFoundError
    ├── InvalidGroupSpecError
    └── DependencyError
```

### 2. Registry Pattern

The group registry mirrors the pipeline registry pattern from `spine.framework.registry`:

| Pipeline Registry | Group Registry |
|-------------------|----------------|
| `@register_pipeline` | `@register_group` |
| `get_pipeline()` | `get_group()` |
| `list_pipelines()` | `list_groups()` |
| `clear_registry()` | `clear_group_registry()` |

### 3. Batch ID Integration

Plan resolution integrates with `spine.core.execution.new_batch_id()`:

```python
from spine.core.execution import new_batch_id

# Auto-generated batch ID format:
# group_{group_name}_{timestamp}_{random}
batch_id = new_batch_id(f"group_{group.name}")
```

### 4. Logging

Uses structlog following existing spine patterns:

```python
import structlog
logger = structlog.get_logger(__name__)

logger.info("group_registered", name=group.name, steps=len(group.steps))
logger.debug("plan_resolved", batch_id=plan.batch_id, steps=plan.step_count)
```

## Key Design Decisions

### D1: Static DAGs Only

**Decision**: No runtime DAG modification or dynamic branching.

**Rationale**: Keeps implementation simple and predictable. The dependency graph is fully resolved at plan creation time.

**Trade-off**: Less flexibility than Airflow-style dynamic tasks, but avoids complexity and makes debugging easier.

### D2: Kahn's Algorithm for Topological Sort

**Decision**: Use Kahn's algorithm (BFS-based) rather than DFS-based topological sort.

**Rationale**: 
- Produces stable, deterministic ordering
- Naturally handles parallel execution levels
- Easier to reason about for debugging

### D3: Three-Color DFS for Cycle Detection

**Decision**: Use three-color (WHITE/GRAY/BLACK) DFS for cycle detection.

**Rationale**:
- Well-understood algorithm
- Reports the actual cycle path for debugging
- O(V+E) time complexity

### D4: Parameter Merge Precedence

**Decision**: `group.defaults < run_params < step.params`

**Rationale**:
- Step-specific overrides should always win
- Runtime params allow ad-hoc overrides
- Defaults provide sensible baselines

### D5: YAML API Version

**Decision**: Use Kubernetes-style `apiVersion: spine.io/v1` format.

**Rationale**:
- Familiar to DevOps teams
- Built-in versioning for future schema evolution
- Clear kind discrimination for multi-type YAML files

## Validation Strategy

### Phase 1 (Current)
- Step name uniqueness
- Dependency reference validity (within group)
- Cycle detection
- Schema validation for YAML

### Phase 2 (Future - Advanced Tier)
- Pipeline existence validation via `get_pipeline()`
- Cross-group dependency validation
- Concurrency guard validation

## Testing Coverage

| Test Category | Coverage |
|--------------|----------|
| Model creation/serialization | ✅ |
| Registry operations | ✅ |
| Topological sort ordering | ✅ |
| Cycle detection (simple, self, long) | ✅ |
| Missing dependency detection | ✅ |
| Parameter merging precedence | ✅ |
| YAML loading | ✅ |
| Integration (end-to-end) | ✅ |

## Open Questions

### Q1: Cross-Group Dependencies
**Status**: Deferred to Phase 3

Should groups be able to depend on other groups? Current thinking is to support this via a higher-level "workflow" concept rather than complicating the group model.

### Q2: Retry Semantics
**Status**: Deferred to Phase 2

How should step retries interact with `on_failure: continue`? Proposal: Step-level retry counts with optional exponential backoff, configured in ExecutionPolicy.

### Q3: Partial Re-runs
**Status**: Deferred to Phase 3

How to re-run a group starting from a failed step? Proposal: Support `resume_from_step` parameter in execution.

## Future Phases

### Phase 2: Execution Engine (Advanced Tier)
- `GroupRunner` class with actual execution
- Integration with `Dispatcher.submit()`
- Celery backend support
- Status tracking via `GroupExecution` table

### Phase 3: Scheduling & Monitoring
- `ScheduleManager` integration
- Concurrency guards across groups
- Prometheus metrics
- Dashboard API endpoints

### Phase 4: Cross-Group Workflows
- `Workflow` abstraction
- Group-level dependencies
- DAG visualization API
