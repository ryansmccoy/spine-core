"""Built-in Example Handlers — reference task and pipeline implementations.

WHY
───
New users and integration tests need concrete handlers to exercise
the execution stack.  These register into the global
:class:`~spine.execution.registry.HandlerRegistry` on import,
so the WorkerLoop can resolve them by name immediately.

ARCHITECTURE
────────────
::

    Handlers (auto-registered on import):
      task:echo          ─ echo params unchanged
      task:sleep         ─ sleep for N seconds
      task:add           ─ add a + b
      task:fail          ─ always raises (DLQ / retry testing)
      task:transform     ─ apply a transform function
      pipeline:etl_stub  ─ simulates extract → transform → load

Usage::

    import spine.execution.handlers   # registers into global registry
    from spine.execution.worker import WorkerLoop
    WorkerLoop(db_path="spine.db").start()

Related modules:
    registry.py — HandlerRegistry these register into
    worker.py   — WorkerLoop that resolves handlers by name
"""

from __future__ import annotations

import logging
import time
from typing import Any

from spine.execution.registry import get_default_registry, register_pipeline, register_task

logger = logging.getLogger(__name__)

_registry = get_default_registry()


# ── Task handlers ────────────────────────────────────────────────────────


@register_task("echo", description="Return the input params unchanged.")
def echo_handler(params: dict[str, Any]) -> dict[str, Any]:
    """Echo — returns whatever params were passed in."""
    logger.info("echo handler invoked with %d param(s)", len(params))
    return {"echoed": params}


@register_task("sleep", description="Sleep for N seconds (default 1).")
def sleep_handler(params: dict[str, Any]) -> dict[str, Any]:
    """Sleep — useful for testing long-running tasks and timeouts."""
    seconds = float(params.get("seconds", 1))
    logger.info("sleep handler sleeping for %.1fs", seconds)
    time.sleep(seconds)
    return {"slept": seconds}


@register_task("add", description="Add two numbers a + b.")
def add_handler(params: dict[str, Any]) -> dict[str, Any]:
    """Add — demonstrates a simple compute task."""
    a = params.get("a", 0)
    b = params.get("b", 0)
    result = a + b
    logger.info("add handler: %s + %s = %s", a, b, result)
    return {"a": a, "b": b, "result": result}


@register_task("fail", description="Always raises RuntimeError (testing).")
def fail_handler(params: dict[str, Any]) -> dict[str, Any]:
    """Fail — always raises, useful for testing retry / DLQ flow."""
    message = params.get("message", "intentional test failure")
    raise RuntimeError(message)


@register_task("transform", description="Apply a simple string transformation.")
def transform_handler(params: dict[str, Any]) -> dict[str, Any]:
    """Transform — uppercase / lowercase / reverse a string value."""
    value = str(params.get("value", ""))
    operation = params.get("operation", "upper")
    if operation == "upper":
        result = value.upper()
    elif operation == "lower":
        result = value.lower()
    elif operation == "reverse":
        result = value[::-1]
    else:
        result = value
    return {"original": value, "operation": operation, "result": result}


# ── Pipeline handlers ────────────────────────────────────────────────────


@register_pipeline("etl_stub", description="Simulate an ETL pipeline with 3 phases.")
def etl_stub_handler(params: dict[str, Any]) -> dict[str, Any]:
    """ETL stub — simulates extract → transform → load with configurable delays."""
    delay = float(params.get("phase_delay", 0.01))
    record_count = int(params.get("records", 100))

    phases: list[dict[str, Any]] = []

    # Extract
    time.sleep(delay)
    phases.append({"phase": "extract", "records": record_count})

    # Transform
    time.sleep(delay)
    transformed = record_count  # No actual filtering for the stub
    phases.append({"phase": "transform", "input": record_count, "output": transformed})

    # Load
    time.sleep(delay)
    phases.append({"phase": "load", "records": transformed})

    return {
        "pipeline": "etl_stub",
        "phases": phases,
        "total_records": transformed,
    }
