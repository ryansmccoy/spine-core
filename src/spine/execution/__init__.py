"""Spine Execution — unified work submission, tracking, and resilience.

WHY
───
Pipelines, tasks, and workflows all need the same lifecycle: submit,
track, retry-on-failure, and report.  Rather than each project
reimplementing this, ``spine.execution`` provides a single contract
(``WorkSpec → EventDispatcher → RunRecord``) that works across
every runtime (threads, processes, Celery, containers).

ARCHITECTURE
────────────
::

    WorkSpec (what to run)
      │
      ▼
    EventDispatcher (submit / query / cancel)
      ├── HandlerRegistry ─ name → handler lookup
      ├── Executor        ─ runtime adapter (how it runs)
      │     ├─ MemoryExecutor    (in-process, testing)
      │     ├─ LocalExecutor     (ThreadPool)
      │     ├─ AsyncLocalExecutor (asyncio semaphore)
      │     ├─ ProcessExecutor   (ProcessPool, GIL escape)
      │     ├─ CeleryExecutor    (distributed, experimental)
      │     └─ StubExecutor      (no-op, dry-run)
      ├── RunRecord       ─ execution state + timestamps
      └── RunEvent        ─ immutable event-sourced history
      │
      ▼
    Resilience layer
      ├── RetryStrategy     ─ exponential / linear / constant backoff
      ├── CircuitBreaker    ─ fail-fast on downstream failures
      ├── RateLimiter       ─ token-bucket / sliding-window
      ├── ConcurrencyGuard  ─ DB-level lock (no duplicate runs)
      └── DeadlineContext   ─ per-step and per-workflow timeouts
      │
      ▼
    Infrastructure
      ├── ExecutionLedger   ─ persistent execution storage
      ├── DLQManager        ─ dead-letter queue for failed work
      ├── ExecutionRepository ─ analytics + maintenance queries
      ├── BatchExecutor     ─ coordinated multi-pipeline runs
      ├── AsyncBatchExecutor ─ asyncio fan-out / fan-in
      └── WorkerLoop        ─ polling loop for background work

    Sub-packages
      ├── executors/        ─ Executor protocol + 6 implementations
      ├── runtimes/         ─ container-level RuntimeAdapter + JobEngine
      └── packaging/        ─ PEP 441 zip-app bundler

MODULE MAP (recommended reading order)
──────────────────────────────────────
Contracts & Models
  1. spec.py              ─ WorkSpec + factory helpers
  2. runs.py              ─ RunRecord, RunStatus, state-machine
  3. events.py            ─ RunEvent (event-sourced history)
  4. models.py            ─ Execution, ExecutionEvent, DeadLetter

Submission & Dispatch
  5. registry.py          ─ HandlerRegistry, register_task/pipeline
  6. dispatcher.py        ─ EventDispatcher (THE public API)
  7. handlers.py          ─ built-in example handlers

Infrastructure
  8. context.py           ─ ExecutionContext, tracked_execution
  9. ledger.py            ─ ExecutionLedger (persistent storage)
 10. repository.py        ─ analytics + maintenance queries
 11. concurrency.py       ─ ConcurrencyGuard (DB-level locking)
 12. dlq.py               ─ DLQManager (dead-letter queue)

Resilience
 13. retry.py             ─ ExponentialBackoff, with_retry
 14. circuit_breaker.py   ─ CircuitBreaker + registry
 15. rate_limit.py        ─ TokenBucket, SlidingWindow, Keyed, Composite
 16. timeout.py           ─ DeadlineContext, with_deadline

Batch & Async
 17. batch.py             ─ BatchExecutor (thread-pool fan-out)
 18. async_batch.py       ─ AsyncBatchExecutor (asyncio fan-out)

Workers & Integration
 19. worker.py            ─ WorkerLoop (polling background worker)
 20. workflow_executor.py ─ bridge: dispatcher → orchestration runner
 21. fastapi.py           ─ /runs REST API router
 22. health.py            ─ ExecutionHealthChecker
 23. tasks.py             ─ Celery task stubs

Executors (sub-package)
 24. executors/protocol.py    ─ Executor protocol
 25. executors/memory.py      ─ in-process (testing)
 26. executors/local.py       ─ ThreadPool
 27. executors/async_local.py ─ asyncio semaphore
 28. executors/process.py     ─ ProcessPool (GIL escape)
 29. executors/celery.py      ─ distributed (experimental)
 30. executors/stub.py        ─ no-op (dry-run)

Example::

    from spine.execution import EventDispatcher, task_spec, register_task
    from spine.execution.executors import MemoryExecutor

    @register_task("send_email")
    async def send_email(params):
        return {"sent": True}

    dispatcher = EventDispatcher(executor=MemoryExecutor())
    run_id = await dispatcher.submit_task("send_email", {"to": "user@example.com"})
    run = await dispatcher.get_run(run_id)
    print(run.status)  # RunStatus.COMPLETED
"""

# Canonical contracts
from .async_batch import (
    AsyncBatchExecutor,
    AsyncBatchItem,
    AsyncBatchResult,
)
from .batch import (
    BatchBuilder,
    BatchExecutor,
    BatchItem,
    BatchResult,
)
from .circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerRegistry,
    CircuitState,
    CircuitStats,
    get_circuit_breaker,
)
from .concurrency import ConcurrencyGuard
from .context import (
    ExecutionContext,
    TrackedExecution,
    tracked_execution_async,
)

# Dispatcher
from .dispatcher import EventDispatcher
from .dlq import DLQManager
from .events import RunEvent
from .health import (
    ExecutionHealthChecker,
    HealthCheckResult,
    HealthReport,
    HealthStatus,
    HealthThresholds,
)

# Execution infrastructure
from .ledger import ExecutionLedger

# Execution models
from .models import (
    EXECUTION_VALID_TRANSITIONS,
    ConcurrencyLock,
    DeadLetter,
    EventType,
    Execution,
    ExecutionEvent,
    ExecutionStatus,
    InvalidTransitionError,
    TriggerSource,
    validate_execution_transition,
)
from .rate_limit import (
    CompositeRateLimiter,
    KeyedRateLimiter,
    RateLimiter,
    SlidingWindowLimiter,
    TokenBucketLimiter,
)

# Registry
from .registry import (
    HandlerRegistry,
    get_default_registry,
    register_handler,
    register_pipeline,
    register_step,
    register_task,
    register_workflow,
    reset_default_registry,
)
from .repository import ExecutionRepository

# Advanced execution patterns
from .retry import (
    ConstantBackoff,
    ExponentialBackoff,
    LinearBackoff,
    NoRetry,
    RetryContext,
    RetryStrategy,
    with_retry,
)

# Runnable protocol (v0.4)
from .runnable import PipelineRunResult, Runnable
from .runs import RUN_VALID_TRANSITIONS, RunRecord, RunStatus, RunSummary, validate_run_transition
from .spec import WorkSpec, pipeline_spec, step_spec, task_spec, workflow_spec

# Timeout enforcement (NEW)
from .timeout import (
    DeadlineContext,
    TimeoutExpired,
    check_deadline,
    get_remaining_deadline,
    run_with_timeout,
    timeout,
    with_deadline,
    with_deadline_async,
)

# FastAPI (optional)
try:
    from .fastapi import FASTAPI_AVAILABLE, create_runs_router
except ImportError:
    FASTAPI_AVAILABLE = False
    create_runs_router = None  # type: ignore

# Worker loop
from .worker import WorkerLoop, get_active_workers, get_worker_stats

# Backward compat alias (events.EventType was removed; models.EventType is canonical)
ExecutionEventType = EventType

__all__ = [
    # Contracts
    "WorkSpec",
    "task_spec",
    "pipeline_spec",
    "workflow_spec",
    "step_spec",
    "RunRecord",
    "RunStatus",
    "RunSummary",
    "RunEvent",
    "EventType",
    # Dispatcher
    "EventDispatcher",
    # Registry
    "HandlerRegistry",
    "get_default_registry",
    "reset_default_registry",
    "register_handler",
    "register_task",
    "register_pipeline",
    "register_workflow",
    "register_step",
    # Execution models
    "Execution",
    "ExecutionEvent",
    "ExecutionStatus",
    "ExecutionEventType",
    "TriggerSource",
    "DeadLetter",
    "ConcurrencyLock",
    # State machine
    "InvalidTransitionError",
    "EXECUTION_VALID_TRANSITIONS",
    "validate_execution_transition",
    "RUN_VALID_TRANSITIONS",
    "validate_run_transition",
    # Execution infrastructure
    "ExecutionLedger",
    "ConcurrencyGuard",
    "DLQManager",
    "ExecutionRepository",
    # Retry strategies
    "RetryStrategy",
    "ExponentialBackoff",
    "LinearBackoff",
    "ConstantBackoff",
    "NoRetry",
    "RetryContext",
    "with_retry",
    # Circuit breaker
    "CircuitBreaker",
    "CircuitState",
    "CircuitStats",
    "CircuitBreakerRegistry",
    "get_circuit_breaker",
    # Rate limiting
    "RateLimiter",
    "TokenBucketLimiter",
    "SlidingWindowLimiter",
    "KeyedRateLimiter",
    "CompositeRateLimiter",
    # Tracked execution context
    "ExecutionContext",
    "TrackedExecution",
    "tracked_execution_async",
    # Health checks
    "HealthStatus",
    "HealthThresholds",
    "HealthCheckResult",
    "HealthReport",
    "ExecutionHealthChecker",
    # Batch execution
    "BatchItem",
    "BatchResult",
    "BatchBuilder",
    "BatchExecutor",
    # Async batch execution (v0.4)
    "AsyncBatchExecutor",
    "AsyncBatchItem",
    "AsyncBatchResult",
    # Runnable protocol (v0.4)
    "Runnable",
    "PipelineRunResult",
    # Timeout enforcement (NEW)
    "TimeoutExpired",
    "DeadlineContext",
    "with_deadline",
    "with_deadline_async",
    "timeout",
    "run_with_timeout",
    "get_remaining_deadline",
    "check_deadline",
    # FastAPI
    "create_runs_router",
    "FASTAPI_AVAILABLE",
    # Worker
    "WorkerLoop",
    "get_active_workers",
    "get_worker_stats",
]
