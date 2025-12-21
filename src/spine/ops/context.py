"""
Request-scoped context for operations.

Every operation function receives an :class:`OperationContext` as its first
argument.  The context carries the database connection, caller identity,
dry-run flag, and arbitrary metadata.  It is *not* the same as
``spine.execution.context.ExecutionContext`` (which tracks operation runs at
the infrastructure level).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from spine.core.protocols import Connection


@dataclass
class OperationContext:
    """Context passed to every operation function.

    Attributes:
        conn: Database connection satisfying :class:`spine.core.protocols.Connection`.
        request_id: Unique ID for this operation invocation (auto-generated).
        caller: Origin of the request — ``"api"``, ``"cli"``, ``"sdk"``, or
            ``"scheduler"``.
        user: Optional authenticated user identifier.
        dry_run: When ``True``, operations return a preview without side effects.
        metadata: Arbitrary key/value pairs forwarded to logging and tracing.
    """

    conn: Connection
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    caller: str = "sdk"
    user: str | None = None
    dry_run: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
