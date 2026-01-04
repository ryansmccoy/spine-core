"""FastAPI application."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import make_asgi_app

from market_spine.api.middleware import RateLimitMiddleware, RequestContextMiddleware
from market_spine.api.routes import dlq, executions, health
from market_spine.core.database import close_pool, init_pool
from market_spine.observability.logging import configure_logging, get_logger
from market_spine.observability.tracing import configure_tracing, instrument_fastapi

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan handler."""
    # Startup
    configure_logging()
    configure_tracing()
    init_pool()
    logger.info("application_started")

    yield

    # Shutdown
    close_pool()
    logger.info("application_stopped")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Market Spine",
        description="Production-grade analytics pipeline system",
        version="1.0.0",
        lifespan=lifespan,
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Request context middleware (for correlation IDs)
    app.add_middleware(RequestContextMiddleware)

    # Rate limiting middleware (excludes health/metrics by default)
    app.add_middleware(
        RateLimitMiddleware,
        max_tokens=100,
        refill_rate=10,
        exclude_paths=["/health", "/metrics"],
    )

    # Include routers
    app.include_router(health.router, tags=["Health"])
    app.include_router(executions.router, prefix="/executions", tags=["Executions"])
    app.include_router(dlq.router, prefix="/dead-letters", tags=["Dead Letters"])

    # Domain routers are registered dynamically via domains/

    # Mount Prometheus metrics
    metrics_app = make_asgi_app()
    app.mount("/metrics", metrics_app)

    # OpenTelemetry instrumentation
    instrument_fastapi(app)

    return app


# Create app instance
app = create_app()
