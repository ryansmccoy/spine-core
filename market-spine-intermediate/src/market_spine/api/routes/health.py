"""Health check endpoints."""

from fastapi import APIRouter

from market_spine.config import get_settings
from market_spine.db import get_connection

router = APIRouter()


@router.get("/health")
async def health_check():
    """Basic health check."""
    return {"status": "healthy"}


@router.get("/health/ready")
async def readiness_check():
    """
    Readiness check - verifies database connectivity.
    """
    try:
        with get_connection() as conn:
            conn.execute("SELECT 1")
        db_status = "connected"
    except Exception as e:
        db_status = f"error: {str(e)}"

    settings = get_settings()

    return {
        "status": "ready" if db_status == "connected" else "not_ready",
        "database": db_status,
        "backend": settings.backend_type,
    }


@router.get("/health/live")
async def liveness_check():
    """Liveness check - basic process health."""
    return {"status": "alive"}
