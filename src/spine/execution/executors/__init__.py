"""Executor adapters - the ONLY backend concept in spine-core.

This module provides executor adapters for different runtime environments.
All executors implement the same protocol, making spine-core runtime-agnostic.

Available executors:
- MemoryExecutor: Synchronous in-process (testing, development)
- LocalExecutor: ThreadPool-based (development, small-scale production)
- AsyncLocalExecutor: asyncio-native with semaphore concurrency (I/O-bound)
- ProcessExecutor: ProcessPool for CPU-bound work (escapes the GIL)
- CeleryExecutor: Distributed via Celery (production)
- StubExecutor: No-op (testing dispatcher logic)

Example:
    >>> from spine.execution.executors import MemoryExecutor, Executor
    >>>
    >>> # All executors have the same interface
    >>> executor: Executor = MemoryExecutor()
    >>> ref = await executor.submit(spec)
    >>> status = await executor.get_status(ref)

Manifesto:
    Executor backends must be swappable.  This package provides
    local, async, process-pool, Celery, memory, and stub
    implementations behind a single protocol so deployments
    choose the right backend without changing application code.

Tags:
    spine-core, execution, executors, backend-abstraction, swappable

Doc-Types:
    api-reference
"""

from .async_local import AsyncLocalExecutor
from .local import LocalExecutor
from .memory import MemoryExecutor
from .process import ProcessExecutor
from .protocol import Executor
from .stub import StubExecutor

# CeleryExecutor is optional (requires celery package)
__all__ = [
    "Executor",
    "MemoryExecutor",
    "LocalExecutor",
    "AsyncLocalExecutor",
    "ProcessExecutor",
    "StubExecutor",
]

try:
    from .celery import CELERY_AVAILABLE, CeleryExecutor  # noqa: F401

    __all__.append("CeleryExecutor")
    __all__.append("CELERY_AVAILABLE")
except ImportError:
    CELERY_AVAILABLE = False
