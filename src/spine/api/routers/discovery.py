"""
Discovery router — health, capabilities, and service introspection.

Provides system-level endpoints for service discovery, health checks,
and capability advertisement. Used by frontends to determine available
features and verify connectivity.

Endpoints:
    GET /health         System health with database connectivity check
    GET /capabilities   Server feature flags and tier information

Doc-Types: API_REFERENCE
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter

from spine.api.deps import OpContext
from spine.api.middleware.errors import problem_response, status_for_error_code
from spine.api.schemas.common import SuccessResponse
from spine.api.schemas.domains import CapabilitiesSchema, HealthStatusSchema

router = APIRouter()


def _dc_to_dict(obj: Any) -> dict[str, Any]:
    """Safely convert a dataclass to dict."""
    if hasattr(obj, "__dataclass_fields__"):
        return asdict(obj)
    return obj if isinstance(obj, dict) else {}


@router.get("/health", response_model=SuccessResponse[HealthStatusSchema])
def get_health(ctx: OpContext):
    """System health with database connectivity check.

    Returns overall system status and individual dependency health.
    Use for monitoring dashboards and automated health probes.

    Args:
        ctx: Operation context with database connection.

    Returns:
        SuccessResponse containing HealthStatusSchema.

    Example:
        GET /api/v1/health

        Response:
        {
            "data": {
                "status": "healthy",
                "database": {"connected": true, "backend": "postgresql"},
                "checks": {"db": {"status": "healthy", "latency_ms": 2.5}},
                "version": "0.5.0"
            }
        }
    """
    from spine.ops.health import get_health

    result = get_health(ctx)
    if not result.success:
        code = result.error.code if result.error else "INTERNAL"
        return problem_response(
            status=status_for_error_code(code),
            title="Health check failed",
            detail=result.error.message if result.error else "",
        )
    data = _dc_to_dict(result.data)
    return SuccessResponse(
        data=HealthStatusSchema(**data),
        elapsed_ms=result.elapsed_ms,
        warnings=result.warnings,
    )


@router.get("/capabilities", response_model=SuccessResponse[CapabilitiesSchema])
def get_capabilities(ctx: OpContext):
    """Advertise server capabilities (feature flags, tier info).

    Returns feature availability based on deployment tier.
    Use to conditionally enable/disable frontend features.

    Args:
        ctx: Operation context with database connection.

    Returns:
        SuccessResponse containing CapabilitiesSchema.

    Example:
        GET /api/v1/capabilities

        Response:
        {
            "data": {
                "tier": "standard",
                "sync_execution": true,
                "async_execution": true,
                "scheduling": true,
                "rate_limiting": false,
                "execution_history": true,
                "dlq": true
            }
        }
    """
    from spine.ops.health import get_capabilities

    result = get_capabilities(ctx)
    if not result.success:
        code = result.error.code if result.error else "INTERNAL"
        return problem_response(
            status=status_for_error_code(code),
            title="Capabilities lookup failed",
            detail=result.error.message if result.error else "",
        )
    data = _dc_to_dict(result.data)
    return SuccessResponse(
        data=CapabilitiesSchema(**data),
        elapsed_ms=result.elapsed_ms,
        warnings=result.warnings,
    )
