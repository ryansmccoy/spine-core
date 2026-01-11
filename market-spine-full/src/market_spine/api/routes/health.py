"""Health check endpoints."""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from market_spine.core.database import get_pool
from market_spine.execution.ledger import ExecutionLedger
from market_spine.execution.dlq import DLQManager
from market_spine.observability.logging import get_logger

router = APIRouter()
logger = get_logger(__name__)


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    timestamp: str
    version: str = "1.0.0"


class ReadinessResponse(BaseModel):
    """Readiness check response."""

    status: str
    database: str
    timestamp: str


class MetricsResponse(BaseModel):
    """Health metrics response."""

    status: str
    timestamp: str
    execution_stats: dict[str, Any]
    dead_letter_count: int


@router.get("/health", response_model=HealthResponse)
@router.get("/health/live", response_model=HealthResponse)
async def liveness():
    """Liveness probe - is the service running?"""
    return HealthResponse(
        status="ok",
        timestamp=datetime.utcnow().isoformat(),
    )


@router.get("/health/ready", response_model=ReadinessResponse)
async def readiness():
    """Readiness probe - can the service accept traffic?"""
    # Check database connection
    db_status = "ok"
    try:
        pool = get_pool()
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
    except Exception as e:
        logger.error("readiness_db_check_failed", error=str(e))
        db_status = f"error: {e}"

    overall_status = "ok" if db_status == "ok" else "degraded"

    return ReadinessResponse(
        status=overall_status,
        database=db_status,
        timestamp=datetime.utcnow().isoformat(),
    )


@router.get("/health/metrics", response_model=MetricsResponse)
async def health_metrics():
    """Get health metrics from the execution ledger."""
    try:
        ledger = ExecutionLedger()
        stats = ledger.get_metrics()

        dlq = DLQManager()
        dead_letters = dlq.list_dead_letters(include_resolved=False)

        return MetricsResponse(
            status="ok",
            timestamp=datetime.utcnow().isoformat(),
            execution_stats=stats,
            dead_letter_count=len(dead_letters),
        )
    except Exception as e:
        logger.error("health_metrics_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
