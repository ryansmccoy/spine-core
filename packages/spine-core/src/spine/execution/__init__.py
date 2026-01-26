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
    
    # FastAPI
    "create_runs_router",
    "FASTAPI_AVAILABLE",
]
