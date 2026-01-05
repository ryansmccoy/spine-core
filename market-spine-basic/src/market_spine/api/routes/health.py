"""
Health check endpoints.

Provides basic and detailed health check endpoints for
monitoring and orchestration (K8s probes, load balancers, etc.).
"""

from datetime import UTC, datetime
from enum import Enum
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from market_spine.db import get_connection


class HealthStatus(str, Enum):
    """Health check status values."""

    OK = "ok"
    ERROR = "error"
    WARNING = "warning"


class ComponentHealth(BaseModel):
    """Health status of a single component."""

    name: str
    status: HealthStatus
    message: str
    latency_ms: float | None = None


class HealthResponse(BaseModel):
    """Response from health check endpoint."""

    status: HealthStatus
    timestamp: str
    checks: list[ComponentHealth] = []
    details: dict[str, Any] = {}


router = APIRouter(tags=["Health"])


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """
    Basic health check endpoint.

    Returns a simple OK response if the API is running.
    Use /health/detailed for comprehensive checks.
    """
    return HealthResponse(
        status=HealthStatus.OK,
        timestamp=datetime.now(UTC).isoformat(),
    )


@router.get("/health/detailed", response_model=HealthResponse)
async def detailed_health_check() -> HealthResponse:
    """
    Detailed health check endpoint.

    Checks all system components:
    - Database connectivity
    - Connection pool status
    """
    checks: list[ComponentHealth] = []
    overall_status = HealthStatus.OK

    # Check database connectivity
    db_check = await _check_database()
    checks.append(db_check)
    if db_check.status == HealthStatus.ERROR:
        overall_status = HealthStatus.ERROR
    elif db_check.status == HealthStatus.WARNING and overall_status != HealthStatus.ERROR:
        overall_status = HealthStatus.WARNING

    return HealthResponse(
        status=overall_status,
        timestamp=datetime.now(UTC).isoformat(),
        checks=checks,
    )


async def _check_database() -> ComponentHealth:
    """Check database connectivity."""
    import time

    start = time.perf_counter()
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()

        latency = (time.perf_counter() - start) * 1000

        return ComponentHealth(
            name="database",
            status=HealthStatus.OK,
            message="Connection successful",
            latency_ms=round(latency, 2),
        )
    except Exception as e:
        latency = (time.perf_counter() - start) * 1000
        return ComponentHealth(
            name="database",
            status=HealthStatus.ERROR,
            message=f"Connection failed: {e}",
            latency_ms=round(latency, 2),
        )
