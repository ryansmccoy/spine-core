"""Canonical execution contract for spine-core.

This module provides ONE unified interface for executing all work types
(tasks, pipelines, workflows) across all runtime environments (local, Celery,
Airflow, K8s, etc.).

Key concepts:
- WorkSpec: what to run (kind, name, params)
- RunRecord: execution state (status, result, timestamps)
- RunEvent: event-sourced history
- Executor: runtime adapter (how work gets executed)
- Dispatcher: submission and query API
- HandlerRegistry: handler registration and lookup

Execution Infrastructure (NEW):
- Execution: Pipeline execution record with full lifecycle
- ExecutionLedger: Persistent storage for executions
- ConcurrencyGuard: Prevent overlapping pipeline runs
- DLQManager: Dead letter queue for failed executions
- ExecutionRepository: Analytics and maintenance queries

Example:
    >>> from spine.execution import Dispatcher, task_spec, register_task
    >>> from spine.execution.executors import MemoryExecutor
    >>>
    >>> @register_task("send_email")
    >>> async def send_email(params):
    ...     return {"sent": True}
    >>>
    >>> dispatcher = Dispatcher(executor=MemoryExecutor())
    >>> run_id = await dispatcher.submit_task("send_email", {"to": "user@example.com"})
    >>> run = await dispatcher.get_run(run_id)
    >>> print(run.status)  # RunStatus.COMPLETED
"""

# Canonical contracts
from .spec import WorkSpec, task_spec, pipeline_spec, workflow_spec, step_spec
from .runs import RunRecord, RunStatus, RunSummary
from .events import RunEvent, EventType

# Dispatcher
from .dispatcher import Dispatcher

# Registry
from .registry import (
    HandlerRegistry,
    get_default_registry,
    reset_default_registry,
    register_handler,
    register_task,
    register_pipeline,
    register_workflow,
    register_step,
)

# Execution models
from .models import (
    Execution,
    ExecutionEvent,
    ExecutionStatus,
    EventType as ExecutionEventType,  # Avoid conflict with events.EventType
    TriggerSource,
    DeadLetter,
    ConcurrencyLock,
)

# Execution infrastructure
from .ledger import ExecutionLedger
from .concurrency import ConcurrencyGuard
from .dlq import DLQManager
from .repository import ExecutionRepository

# Advanced execution patterns
from .retry import (
    RetryStrategy,
    ExponentialBackoff,
    LinearBackoff,
    ConstantBackoff,
    NoRetry,
    RetryContext,
    with_retry,
)
from .circuit_breaker import (
    CircuitBreaker,
    CircuitState,
    CircuitStats,
    CircuitBreakerRegistry,
    get_circuit_breaker,
)
from .rate_limit import (
    RateLimiter,
    TokenBucketLimiter,
    SlidingWindowLimiter,
    KeyedRateLimiter,
    CompositeRateLimiter,
)
from .context import (
    ExecutionContext,
    TrackedExecution,
    tracked_execution_async,
)
from .health import (
    HealthStatus,
    HealthThresholds,
    HealthCheckResult,
    HealthReport,
    ExecutionHealthChecker,
)
from .batch import (
    BatchItem,
    BatchResult,
    BatchBuilder,
    BatchExecutor,
)

# FastAPI (optional)
try:
    from .fastapi import create_runs_router, FASTAPI_AVAILABLE
except ImportError:
    FASTAPI_AVAILABLE = False
    create_runs_router = None  # type: ignore

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
    "Dispatcher",
    
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
    
    # FastAPI
    "create_runs_router",
    "FASTAPI_AVAILABLE",
]
