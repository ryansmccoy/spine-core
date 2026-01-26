# 📋 COPY-PASTE PROMPT: Annotate Spine-Core Classes

**Copy everything below and send to an LLM with file editing access:**

---

## TASK: Add Extended Docstrings to Spine-Core Classes

You are a documentation automation agent. Add rich extended docstrings to Python classes in the Spine-Core project.

### Project Context

**Spine-Core** is the shared framework primitives used across all Spine ecosystem projects.

**The Project Origin (Why It Exists):**
The project was extracted in **January 2026** when EntitySpine, FeedSpine, and Capture-Spine all started duplicating the same patterns: Result[T] for error handling, workflow orchestration, execution dispatching, and error taxonomies. Spine-Core consolidates these into one dependency so all Spine projects share the same foundation. The key insight: **common patterns should live in one place**, not be copy-pasted across projects.

**Core Principles (use in Manifesto sections):**
1. **Result[T] everywhere** - All operations return Ok(value) or Err(error), never raise exceptions
2. **Error taxonomy** - Structured error categories (Validation, Network, Storage, etc.)
3. **Workflow orchestration** - DAG-based step execution with dependency resolution
4. **Executor abstraction** - Run locally, Celery, or memory with same interface
5. **Zero external deps** - Core module has no dependencies beyond stdlib

### Extended Docstring Format

```python
class ClassName:
    """
    One-line summary.
    
    Extended description (2-3 sentences).
    
    Manifesto:
        Why this class exists. Reference spine-core principles.
        Explain how it unifies patterns across projects.
    
    Architecture:
        ```
        ASCII diagram showing usage across projects
        ```
        Used by: EntitySpine, FeedSpine, Capture-Spine
        Dependencies: None (stdlib only) or specific deps
    
    Features:
        - Feature 1
        - Feature 2
    
    Examples:
        >>> from spine.core import Result, Ok, Err
        >>> result = Ok(42)
        >>> result.is_ok()
        True
    
    Performance:
        - Construction: O(1)
        - Pattern matching: O(1)
    
    Guardrails:
        - Do NOT raise exceptions in spine-core code
          ✅ Instead: Return Err(error)
    
    Tags:
        - result_pattern
        - shared_framework
    
    Doc-Types:
        - MANIFESTO (section: "Error Handling", priority: 10)
        - ARCHITECTURE (section: "Core Primitives", priority: 10)
    """
```

### Files to Annotate (Feature-Based + Chronological Order)

**Selection methodology**: Organized by architectural layer, from core primitives up to orchestration. Core module is first because it has zero dependencies and is used by everything else.

---

## 🔴 PHASE 1: CORE MODULE - The Foundation (Do First)

*Zero-dependency primitives used by all Spine projects*

| Order | File | Classes | Why First |
|-------|------|---------|-----------|
| 1 | `core/result.py` | Result, Ok, Err (2) | **THE RESULT PATTERN** - replaces exceptions everywhere |
| 2 | `core/errors.py` | SpineError, ErrorCategory, ValidationError... (31!) | **ERROR TAXONOMY** - structured error types |
| 3 | `core/idempotency.py` | IdempotencyKey, IdempotencyStore (4) | Exactly-once execution |
| 4 | `core/storage.py` | StorageProtocol, StorageResult (4) | Storage abstraction |
| 5 | `core/quality.py` | QualityScore, QualityMetric (6) | Data quality scoring |
| 6 | `core/manifest.py` | Manifest, ManifestEntry (3) | Data manifests |
| 7 | `core/rejects.py` | Reject, RejectStore (3) | Rejected record handling |
| 8 | `core/temporal.py` | TemporalRange (1) | Time range utilities |
| 9 | `core/rolling.py` | RollingWindow, RollingStats (2) | Rolling aggregations |
| 10 | `core/execution.py` | ExecutionContext (1) | Execution context |

---

## 🟠 PHASE 2: FRAMEWORK MODULE - Shared Infrastructure

*Cross-cutting concerns: alerts, sources, pipelines, logging*

| Order | File | Classes | Feature |
|-------|------|---------|---------|
| 11 | `framework/exceptions.py` | FrameworkError, ConfigError (5) | Framework exceptions |
| 12 | `framework/dispatcher.py` | Dispatcher, DispatchResult (4) | Event dispatching |
| 13 | `framework/params.py` | Params, ParamSpec (3) | Parameter handling |
| 14 | `framework/runner.py` | Runner (1) | Generic runner |
| 15 | `framework/db.py` | Database (1) | Database abstraction |

---

## 🟡 PHASE 3: FRAMEWORK/ALERTS - Alerting System

*Unified alerting across all Spine projects*

| Order | File | Classes | Feature |
|-------|------|---------|---------|
| 16 | `framework/alerts/protocol.py` | Alert, AlertLevel, AlertManager (11) | **ALERTING** - Slack, email, webhooks |

---

## 🟢 PHASE 4: FRAMEWORK/SOURCES - Data Sources

*Unified source abstraction for all data ingestion*

| Order | File | Classes | Feature |
|-------|------|---------|---------|
| 17 | `framework/sources/protocol.py` | Source, SourceConfig, SourceResult (8) | Source protocol |
| 18 | `framework/sources/file.py` | FileSource, DirectorySource (3) | File-based sources |

---

## 🔵 PHASE 5: ORCHESTRATION - Workflow DAGs

*DAG-based workflow execution with dependency resolution*

| Order | File | Classes | Feature |
|-------|------|---------|---------|
| 19 | `orchestration/models.py` | Step, Workflow, StepDependency (8) | **WORKFLOW MODELS** |
| 20 | `orchestration/exceptions.py` | WorkflowError, StepError (7) | Workflow exceptions |
| 21 | `orchestration/step_types.py` | StepType, ParallelStep, SequentialStep (5) | Step type definitions |
| 22 | `orchestration/step_result.py` | StepResult, StepStatus (3) | Step execution results |
| 23 | `orchestration/runner.py` | WorkflowRunner, StepRunner (5) | **THE RUNNER** - executes workflows |
| 24 | `orchestration/workflow_runner.py` | DAGRunner, DependencyResolver (4) | DAG execution |
| 25 | `orchestration/workflow_context.py` | WorkflowContext (1) | Workflow execution context |
| 26 | `orchestration/workflow.py` | WorkflowDefinition (1) | Workflow definition DSL |
| 27 | `orchestration/planner.py` | ExecutionPlanner (1) | Plan step execution order |
| 28 | `orchestration/registry.py` | StepRegistry (1) | Register step implementations |
| 29 | `orchestration/loader.py` | WorkflowLoader (1) | Load workflows from YAML |

---

## 🟣 PHASE 6: EXECUTION - Executor Abstraction (Added Feb 2026)

*Run the same code locally, in Celery, or in-memory tests*

| Order | File | Classes | Feature |
|-------|------|---------|---------|
| 30 | `execution/executors/protocol.py` | Executor (1) | **EXECUTOR PROTOCOL** |
| 31 | `execution/executors/local.py` | LocalExecutor (1) | Synchronous local execution |
| 32 | `execution/executors/memory.py` | MemoryExecutor (1) | In-memory for testing |
| 33 | `execution/executors/celery.py` | CeleryExecutor (1) | Celery distributed execution |
| 34 | `execution/executors/stub.py` | StubExecutor (1) | Stub for unit tests |
| 35 | `execution/runs.py` | Run, RunStatus, RunStore (3) | Execution run tracking |
| 36 | `execution/events.py` | ExecutionEvent, EventType (2) | Execution events |
| 37 | `execution/spec.py` | ExecutionSpec (1) | Execution specification |
| 38 | `execution/registry.py` | ExecutorRegistry (1) | Register executors |
| 39 | `execution/dispatcher.py` | ExecutionDispatcher (1) | Dispatch to executors |

---

## ⚪ PHASE 7: ADAPTERS & LOGGING

*Database adapters and structured logging*

| Order | File | Classes | Feature |
|-------|------|---------|---------|
| 40 | `core/adapters/database.py` | DatabaseAdapter, ConnectionPool (7) | Database connectivity |
| 41 | `framework/pipelines/base.py` | Pipeline, PipelineStage (3) | Pipeline abstraction |
| 42 | `framework/logging/context.py` | LogContext, StructuredLogger (2) | Structured logging |
| 43 | `framework/logging/timing.py` | Timer (1) | Timing utilities |

---

### Workflow

**Work in PHASES, not random files:**
1. Complete Phase 1 entirely (10 files) - this is THE foundation
2. Complete Phase 2 entirely (5 files) - framework infrastructure
3. Then proceed to Phase 3, 4, etc.

For each file:
1. Read the entire source file
2. Add extended docstrings to **all public classes**
3. Ensure Manifesto explains how this unifies patterns across Spine projects

### Quality Checklist (per phase)
- [ ] All classes in the phase are annotated
- [ ] Manifesto explains "used by EntitySpine, FeedSpine, Capture-Spine"
- [ ] Architecture shows cross-project usage
- [ ] Examples show typical usage patterns

### Start Now

**Begin with Phase 1, File 1: `core/result.py`** - the `Result[T]` pattern that ALL Spine projects use for error handling. This is THE fundamental abstraction.

---

**When done with each phase, report progress before continuing.**
