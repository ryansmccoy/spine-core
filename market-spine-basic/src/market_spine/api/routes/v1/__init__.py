"""
API v1 router.

Aggregates all v1 endpoints under a single router for versioned mounting.
"""

from fastapi import APIRouter

from .capabilities import router as capabilities_router
from .pipelines import router as pipelines_router

router = APIRouter()

# Mount sub-routers
router.include_router(capabilities_router)
router.include_router(pipelines_router)
