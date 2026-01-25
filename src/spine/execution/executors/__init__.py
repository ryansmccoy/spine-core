"""Executor adapters - the ONLY backend concept in spine-core.

This module provides executor adapters for different runtime environments.
All executors implement the same protocol, making spine-core runtime-agnostic.

Available executors:
- MemoryExecutor: Synchronous in-process (testing, development)
- LocalExecutor: ThreadPool-based (development, small-scale production)
- CeleryExecutor: Distributed via Celery (production)
- StubExecutor: No-op (testing dispatcher logic)

Example:
    >>> from spine.execution.executors import MemoryExecutor, Executor
    >>>
    >>> # All executors have the same interface
    >>> executor: Executor = MemoryExecutor()
    >>> ref = await executor.submit(spec)
    >>> status = await executor.get_status(ref)
"""

from .protocol import Executor
from .memory import MemoryExecutor
from .local import LocalExecutor
from .stub import StubExecutor

# CeleryExecutor is optional (requires celery package)
__all__ = [
    "Executor",
    "MemoryExecutor",
    "LocalExecutor",
    "StubExecutor",
]

try:
    from .celery import CeleryExecutor, CELERY_AVAILABLE
    __all__.append("CeleryExecutor")
    __all__.append("CELERY_AVAILABLE")
except ImportError:
    CELERY_AVAILABLE = False
