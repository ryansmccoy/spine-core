"""FastAPI application factory."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import structlog

from market_spine.config import get_settings
from market_spine.db import init_db

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup
    logger.info("api_starting")
    init_db()

    yield

    # Shutdown
    logger.info("api_stopping")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title="Market Spine",
        description="Analytics pipeline orchestration for market computations",
        version="0.2.0",
        lifespan=lifespan,
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Configure properly for production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include routers
    from market_spine.api.routes import (
        health,
        executions,
        workflows,
        schedules,
        alerts,
        sources,
    )

    app.include_router(health.router, tags=["Health"])
    app.include_router(executions.router, prefix="/api/v1/executions", tags=["Executions"])
    app.include_router(workflows.router, prefix="/api/v1/workflows", tags=["Workflows"])
    app.include_router(schedules.router, prefix="/api/v1/schedules", tags=["Schedules"])
    app.include_router(alerts.router, prefix="/api/v1/alerts", tags=["Alerts"])
    app.include_router(sources.router, prefix="/api/v1/sources", tags=["Sources"])

    # Domain routers are registered dynamically via domains/

    return app


# Default app instance
app = create_app()
