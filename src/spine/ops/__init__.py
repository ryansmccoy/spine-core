"""
Operations layer — pure business logic for spine-core.

The ops package provides typed request/response functions that wrap existing
adapters (execution, orchestration, framework) with consistent patterns:

- All functions accept ``OperationContext`` as first argument
- All functions return ``OperationResult[T]`` (never raise)
- All functions are transport-agnostic (no HTTP, no CLI knowledge)
- All functions support ``dry_run`` mode for safe previews

Usage::

    from spine.ops import OperationContext, OperationResult
    from spine.ops.database import initialize_database
    from spine.ops.runs import list_runs

    ctx = OperationContext(conn=my_connection)
    result = initialize_database(ctx)
    assert result.success
"""

from spine.ops.context import OperationContext
from spine.ops.result import OperationError, OperationResult, PagedResult
from spine.ops.sqlite_conn import SqliteConnection

__all__ = [
    "OperationContext",
    "OperationError",
    "OperationResult",
    "PagedResult",
    "SqliteConnection",
]
