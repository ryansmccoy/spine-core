"""
FastAPI application factory.

``create_app()`` wires middleware, routers, error handlers, and
lifespan events into a single ``FastAPI`` instance.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from spine.api.deps import get_settings
from spine.api.middleware.errors import unhandled_exception_handler
from spine.api.middleware.request_id import RequestIDMiddleware
from spine.api.middleware.timing import TimingMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan — startup / shutdown hooks."""

    from spine.core.logging import get_logger

    from spine.api.settings import SpineCoreAPISettings
    from spine.core.connection import create_connection

    log = get_logger("spine.api")
    log.info("spine-core API starting", version=app.version)

    # Auto-initialize database on startup
    conn = None
    try:
        settings = app.state.settings if hasattr(app.state, "settings") else SpineCoreAPISettings()

        conn, info = create_connection(
            settings.database_url,
            init_schema=True,
            data_dir=settings.data_dir,
        )
        log.info("database initialized", backend=info.backend)
    except Exception as e:
        log.warning("database auto-init failed", error=str(e))
    finally:
        if conn is not None and hasattr(conn, "close"):
            try:
                conn.close()
            except Exception:
                pass

    # Register example workflows so the frontend has data to show
    try:
        from spine.api.example_workflows import register_example_workflows
        n = register_example_workflows()
        if n:
            log.info("example_workflows_loaded", count=n)
    except Exception as e:
        log.debug("example_workflow_registration_skipped", error=str(e))

    yield
    log.info("spine-core API shutting down")

def create_app(
    *,
    settings: SpineCoreAPISettings | None = None,  # noqa: F821  (forward ref)
) -> FastAPI:
    """Build and return a fully-configured FastAPI application.

    Parameters
    ----------
    settings : SpineCoreAPISettings | None
        Override settings (useful for testing).  When ``None`` the cached
        singleton from :func:`get_settings` is used.
    """

    settings = settings or get_settings()

    app = FastAPI(
        title=settings.api_title,
        version=settings.api_version,
        lifespan=lifespan,
        docs_url=f"{settings.api_prefix}/docs",
        redoc_url=f"{settings.api_prefix}/redoc",
        openapi_url=f"{settings.api_prefix}/openapi.json",
    )

    # Stash settings on app state for middleware access
    app.state.settings = settings

    # Override DI so endpoints use the provided settings
    app.dependency_overrides[get_settings] = lambda: settings

    # ── Middleware (outermost → innermost) ────────────────────────────
    app.add_middleware(TimingMiddleware)
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Exception handlers ───────────────────────────────────────────
    app.add_exception_handler(Exception, unhandled_exception_handler)

    # ── Routers ──────────────────────────────────────────────────────
    from spine.api.routers import (
        alerts,
        anomalies,
        database,
        deploy,
        discovery,
        dlq,
        events,
        quality,
        runs,
        schedules,
        sources,
        stats,
        webhooks,
        workflows,
    )
    from spine.core.health import create_health_router

    prefix = settings.api_prefix

    # Health endpoints at root level (no prefix) for container healthchecks
    app.include_router(
        create_health_router("spine-core", version=settings.api_version),
        tags=["health"],
    )

    app.include_router(discovery.router, prefix=prefix, tags=["discovery"])
    app.include_router(database.router, prefix=prefix, tags=["database"])
    app.include_router(workflows.router, prefix=prefix, tags=["workflows"])
    app.include_router(runs.router, prefix=prefix, tags=["runs"])
    app.include_router(schedules.router, prefix=prefix, tags=["schedules"])
    app.include_router(dlq.router, prefix=prefix, tags=["dlq"])
    app.include_router(anomalies.router, prefix=prefix, tags=["anomalies"])
    app.include_router(quality.router, prefix=prefix, tags=["quality"])
    app.include_router(stats.router, prefix=prefix, tags=["stats"])
    app.include_router(webhooks.router, prefix=prefix, tags=["webhooks"])
    app.include_router(alerts.router, prefix=prefix, tags=["alerts"])
    app.include_router(sources.router, prefix=prefix, tags=["sources"])
    app.include_router(events.router, prefix=prefix, tags=["events"])
    app.include_router(deploy.router, prefix=prefix, tags=["deploy"])

    # ── Metrics endpoint (root-level, Prometheus format) ─────────
    from fastapi.responses import PlainTextResponse

    @app.get("/metrics", tags=["observability"], include_in_schema=True)
    async def metrics_endpoint() -> PlainTextResponse:
        """Export Prometheus-compatible metrics."""
        from spine.observability.metrics import get_metrics_registry

        registry = get_metrics_registry()
        return PlainTextResponse(
            content=registry.export_prometheus(),
            media_type="text/plain; version=0.0.4; charset=utf-8",
        )

    return app
