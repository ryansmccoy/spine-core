"""
Health and capabilities operations.

Provides service health status and runtime capability introspection.
"""

from __future__ import annotations

from spine.ops.context import OperationContext
from spine.ops.database import check_database_health
from spine.ops.responses import Capabilities, HealthStatus
from spine.ops.result import OperationResult, start_timer


def get_health(ctx: OperationContext) -> OperationResult[HealthStatus]:
    """Aggregate health status across subsystems."""
    timer = start_timer()

    db_result = check_database_health(ctx)
    db_health = db_result.data

    checks: dict[str, str] = {}
    status = "healthy"

    if db_health and db_health.connected:
        checks["database"] = "ok"
    else:
        checks["database"] = "fail"
        status = "unhealthy"

    return OperationResult.ok(
        HealthStatus(
            status=status,
            database=db_health,
            checks=checks,
            version="0.3.1",
        ),
        warnings=db_result.warnings,
        elapsed_ms=timer.elapsed_ms,
    )


def get_capabilities(ctx: OperationContext) -> OperationResult[Capabilities]:
    """Introspect runtime capabilities based on available backends."""
    timer = start_timer()

    # For now, report defaults.  Phase 6 will wire this to SpineContainer
    # component detection.
    caps = Capabilities(
        tier="standard",
        sync_execution=True,
        async_execution=True,
        scheduling=True,
        rate_limiting=True,
        execution_history=True,
        dlq=True,
    )
    return OperationResult.ok(caps, elapsed_ms=timer.elapsed_ms)
