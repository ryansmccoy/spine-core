"""
FastAPI application factory and configuration.

This module creates the FastAPI application instance and configures
middleware, exception handlers, and router mounting.
"""

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from market_spine import __version__
from market_spine.db import init_connection_provider

from .routes import health, v1


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """
    Application lifespan manager.

    Handles startup and shutdown events:
    - Startup: Initialize database connection provider
    - Shutdown: Cleanup resources (if any)
    """
    # Startup
    init_connection_provider()
    yield
    # Shutdown (no cleanup needed for Basic tier)


def create_app() -> FastAPI:
    """
    Create and configure the FastAPI application.

    Returns:
        Configured FastAPI application instance
    """
    app = FastAPI(
        title="Market Spine API",
        description="Analytics Pipeline System - REST API",
        version=__version__,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # Mount routers
    app.include_router(health.router)
    app.include_router(v1.router, prefix="/v1")

    return app


# Create default application instance
app = create_app()
