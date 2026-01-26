# Commit Plan: RFC-001 Phase 1 Implementation

This document outlines the recommended commit structure for merging the Phase 1 scaffolding into main.

## Branch Strategy

```
feature/orchestration-phase1
  └── PR #XXX → main
```

## Commit Sequence

### Commit 1: Add orchestration exceptions
```
feat(orchestration): add exception hierarchy for pipeline groups

- Add GroupError base exception inheriting from SpineError
- Add CycleDetectedError with cycle path reporting
- Add GroupNotFoundError, StepNotFoundError, DependencyError
- Add InvalidGroupSpecError for schema validation
- Add PlanResolutionError for planner failures

Files:
  + packages/spine-core/src/spine/orchestration/exceptions.py
```

### Commit 2: Add core data models
```
feat(orchestration): add PipelineGroup and related data models

- Add PipelineStep with depends_on and params
- Add ExecutionPolicy with mode, concurrency, failure handling
- Add PipelineGroup with steps and defaults
- Add PlannedStep and ExecutionPlan for resolved plans
- Add GroupRunStatus, FailurePolicy, ExecutionMode enums
- Support both flat dict and YAML-style nested dict parsing

Files:
  + packages/spine-core/src/spine/orchestration/models.py
```

### Commit 3: Add group registry
```
feat(orchestration): add group registration system

- Add register_group() function and decorator
- Add get_group(), list_groups(), group_exists() queries
- Add clear_group_registry() for testing
- Mirror patterns from spine.framework.registry

Files:
  + packages/spine-core/src/spine/orchestration/registry.py
```

### Commit 4: Add DAG planner with topological sort
```
feat(orchestration): add PlanResolver with DAG validation

- Add topological sort using Kahn's algorithm
- Add cycle detection using three-color DFS
- Add dependency validation (missing step detection)
- Add parameter merging (defaults < run_params < step.params)
- Generate batch_id via spine.core.execution.new_batch_id()

Files:
  + packages/spine-core/src/spine/orchestration/planner.py
```

### Commit 5: Add YAML loader
```
feat(orchestration): add YAML loading and validation

- Add load_group_from_yaml() for single file loading
- Add load_groups_from_directory() for bulk loading
- Add group_to_yaml() for serialization
- Add validate_yaml_schema() for schema validation
- Support apiVersion spine.io/v1 format

Files:
  + packages/spine-core/src/spine/orchestration/loader.py
```

### Commit 6: Add module exports
```
feat(orchestration): expose public API in __init__.py

- Export all models (PipelineGroup, PipelineStep, ExecutionPolicy, etc.)
- Export registry functions (register_group, get_group, etc.)
- Export PlanResolver and exceptions
- Export loader functions

Files:
  + packages/spine-core/src/spine/orchestration/__init__.py
```

### Commit 7: Add comprehensive test suite
```
test(orchestration): add unit tests for orchestration module

- Add model creation and serialization tests
- Add registry operation tests
- Add topological sort ordering tests
- Add cycle detection tests (simple, self-loop, long chain)
- Add missing dependency detection tests
- Add parameter merging precedence tests
- Add integration tests (full workflow, YAML format)

Files:
  + packages/spine-core/tests/test_orchestration.py
```

### Commit 8: Add examples and documentation
```
docs(orchestration): add examples and implementation notes

- Add YAML example: finra_weekly_refresh.yaml
- Add Python DSL example: example_python_dsl.py
- Add Phase 1 implementation notes
- Add commit plan document

Files:
  + packages/spine-core/examples/groups/finra_weekly_refresh.yaml
  + packages/spine-core/examples/groups/example_python_dsl.py
  + docs/design/PHASE1_IMPLEMENTATION_NOTES.md
  + docs/design/COMMIT_PLAN_ORCHESTRATION.md
```

## Squash Merge Option

For a cleaner history, consider squashing into 3 commits:

1. **feat(orchestration): add pipeline groups and DAG orchestration**
   - Commits 1-6: All code files

2. **test(orchestration): add comprehensive test suite**
   - Commit 7: Tests

3. **docs(orchestration): add examples and documentation**
   - Commit 8: Examples and docs

## PR Description Template

```markdown
## Summary

Implements Phase 1 of RFC-001: Pipeline Groups and Simple DAG Orchestration.

This PR adds the core scaffolding for grouping pipelines into named groups
with declarative dependencies. It enables:

- Defining groups via YAML or Python DSL
- DAG validation (cycle detection, dependency validation)
- Plan resolution with topological ordering
- Parameter merging (defaults < run_params < step.params)

## What's Included

- `spine.orchestration` module with:
  - Data models: PipelineGroup, PipelineStep, ExecutionPolicy
  - Registry: register_group(), get_group(), list_groups()
  - Planner: PlanResolver with DAG validation
  - Loader: YAML parsing with schema validation
- Comprehensive test suite (XX tests)
- Examples for YAML and Python DSL usage
- Implementation notes and commit plan

## What's NOT Included (Future Phases)

- GroupRunner execution (Phase 2)
- Celery/LocalBackend integration (Phase 2)
- Status tracking and DLQ (Phase 2)
- ScheduleManager integration (Phase 3)
- Cross-group dependencies (Phase 4)

## Testing

```bash
cd packages/spine-core
pytest tests/test_orchestration.py -v
```

## Related

- RFC: docs/design/RFC-001-pipeline-groups.md
- Design Notes: docs/design/PHASE1_IMPLEMENTATION_NOTES.md
```

## Post-Merge Checklist

- [ ] Update CHANGELOG.md
- [ ] Tag release if appropriate (e.g., v0.2.0)
- [ ] Create Phase 2 tracking issue
- [ ] Update roadmap in README
