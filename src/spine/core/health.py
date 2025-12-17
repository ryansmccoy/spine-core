"""Standardized health check utilities for the Spine ecosystem.

Provides:

- **Response models** — ``HealthResponse``, ``CheckResult``, ``LivenessResponse``
  used as the canonical JSON envelope across *every* Spine HTTP service.
- **``HealthCheck``** — a declarative description of a single dependency check
  (Postgres, Redis, Ollama …) with ``required`` / ``timeout_s`` knobs.
- **``create_health_router()``** — a one-liner that gives any FastAPI app three
  K8s-style endpoints: ``/health``, ``/health/ready``, ``/health/live``.
- **``SpineHealth``** — the original lightweight model (retained for backwards
  compatibility with non-HTTP callers).

Quick start::

    from spine.core.health import create_health_router, HealthCheck
    from spine.core.health_checks import check_postgres, check_redis

    router = create_health_router(
        service_name="genai-spine",
        version="0.2.0",
        checks=[
            HealthCheck("postgres", partial(check_postgres, db_url)),
            HealthCheck("redis", partial(check_redis, redis_url), required=False),
        ],
    )
    app.include_router(router)
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

try:
    from pydantic import BaseModel, Field
except ImportError as _exc:
    raise ImportError(
        "spine.core.health requires pydantic. "
        "Install it with: pip install spine-core[models]"
    ) from _exc

# Module-level start time — set when the service first imports this module.
_START_TIME = time.monotonic()


# ── Response Models ──────────────────────────────────────────────────────


class CheckResult(BaseModel):
    """Result of a single dependency health check."""

    status: Literal["healthy", "degraded", "unhealthy"]
    latency_ms: float | None = None
    error: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class HealthResponse(BaseModel):
    """Standard health response envelope — every Spine API returns this from ``GET /health``.

    Fields
    ──────
    status    : ``healthy`` | ``degraded`` | ``unhealthy``
    service   : Human-readable service name
    version   : Semver string
    uptime_s  : Seconds since startup
    timestamp : ISO-8601 UTC
    checks    : Per-dependency breakdown (name → CheckResult)
    """

    status: Literal["healthy", "degraded", "unhealthy"] = "healthy"
    service: str = ""
    version: str = ""
    uptime_s: float = Field(default_factory=lambda: round(time.monotonic() - _START_TIME, 1))
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    checks: dict[str, CheckResult] = Field(default_factory=dict)


class LivenessResponse(BaseModel):
    """Response for liveness probes — always returns ``{"status": "alive"}``."""

    status: str = "alive"


# ── Legacy Model (backwards compat) ─────────────────────────────────────


class SpineHealth(BaseModel):
    """Original lightweight health envelope (non-HTTP callers).

    Retained for backwards compatibility.  New HTTP services should use
    ``create_health_router()`` and ``HealthResponse`` instead.
    """

    name: str
    version: str
    status: Literal["ok", "degraded", "error"] = "ok"
    uptime_s: float = Field(default_factory=lambda: round(time.monotonic() - _START_TIME, 1))
    details: dict[str, Any] = Field(default_factory=dict)


# ── Health Check Definition ──────────────────────────────────────────────


@dataclass
class HealthCheck:
    """Declarative description of a single dependency health check.

    Parameters
    ----------
    name : str
        Dependency name (e.g. ``"postgres"``, ``"redis"``, ``"ollama"``).
    check_fn : () -> Awaitable[bool]
        Async callable.  Should return ``True`` or raise on failure.
    required : bool
        If *True* (default), failure makes the overall status ``unhealthy``.
        If *False*, failure only causes ``degraded``.
    timeout_s : float
        Max seconds to wait before the check is considered failed.
    """

    name: str
    check_fn: Callable[[], Awaitable[bool]]
    required: bool = True
    timeout_s: float = 5.0


# ── Internal helpers ─────────────────────────────────────────────────────


async def _run_checks(checks: list[HealthCheck]) -> dict[str, CheckResult]:
    """Execute all checks in parallel and return a mapping of name → result."""

    async def _one(hc: HealthCheck) -> tuple[str, CheckResult]:
        start = time.monotonic()
        try:
            await asyncio.wait_for(hc.check_fn(), timeout=hc.timeout_s)
            elapsed = (time.monotonic() - start) * 1000
            return hc.name, CheckResult(status="healthy", latency_ms=round(elapsed, 2))
        except TimeoutError:
            return hc.name, CheckResult(status="unhealthy", error="timeout")
        except Exception as exc:  # noqa: BLE001
            elapsed = (time.monotonic() - start) * 1000
            return hc.name, CheckResult(
                status="unhealthy",
                latency_ms=round(elapsed, 2),
                error=str(exc)[:200],
            )

    pairs = await asyncio.gather(*[_one(hc) for hc in checks])
    return dict(pairs)


def _compute_status(
    check_results: dict[str, CheckResult],
    checks: list[HealthCheck],
) -> Literal["healthy", "degraded", "unhealthy"]:
    """Derive aggregate status from individual check results."""
    check_map = {hc.name: hc for hc in checks}
    any_required_down = False
    any_optional_down = False

    for name, result in check_results.items():
        if result.status != "healthy":
            hc = check_map.get(name)
            if hc and hc.required:
                any_required_down = True
            else:
                any_optional_down = True

    if any_required_down:
        return "unhealthy"
    if any_optional_down:
        return "degraded"
    return "healthy"


# ── Router Factory ───────────────────────────────────────────────────────


def create_health_router(
    service_name: str,
    version: str,
    checks: list[HealthCheck] | None = None,
    prefix: str = "/health",
):
    """Create a FastAPI ``APIRouter`` with standardised health endpoints.

    Endpoints created
    -----------------
    ``GET {prefix}``         Primary health — runs all checks.
    ``GET {prefix}/ready``   Readiness probe — 503 if any required dep is down.
    ``GET {prefix}/live``    Liveness probe — always 200.

    Parameters
    ----------
    service_name : str
        Human-readable name (e.g. ``"genai-spine"``).
    version : str
        Service version string.
    checks : list[HealthCheck] | None
        Dependency checks to execute for ``/health`` and ``/health/ready``.
    prefix : str
        URL prefix (default ``"/health"``).

    Returns
    -------
    fastapi.APIRouter
    """
    # Late import so spine-core doesn't hard-depend on fastapi.
    from fastapi import APIRouter  # noqa: PLC0415
    from fastapi.responses import JSONResponse  # noqa: PLC0415

    router = APIRouter(tags=["health"])
    _checks: list[HealthCheck] = checks or []

    def _make_response(
        status: Literal["healthy", "degraded", "unhealthy"],
        check_results: dict[str, CheckResult],
    ) -> HealthResponse:
        return HealthResponse(
            status=status,
            service=service_name,
            version=version,
            uptime_s=round(time.monotonic() - _START_TIME, 1),
            timestamp=datetime.now(UTC).isoformat(),
            checks=check_results,
        )

    @router.get(prefix, response_model=HealthResponse)
    async def health() -> JSONResponse:
        """Primary health — runs all dependency checks."""
        check_results = await _run_checks(_checks)
        status = _compute_status(check_results, _checks)
        body = _make_response(status, check_results)
        code = 503 if status == "unhealthy" else 200
        return JSONResponse(content=body.model_dump(), status_code=code)

    @router.get(f"{prefix}/ready", response_model=HealthResponse)
    async def readiness() -> JSONResponse:
        """Readiness probe — 503 if any required dependency is down."""
        check_results = await _run_checks(_checks)
        status = _compute_status(check_results, _checks)
        code = 503 if status != "healthy" else 200
        body = _make_response(status, check_results)
        return JSONResponse(content=body.model_dump(), status_code=code)

    @router.get(f"{prefix}/live", response_model=LivenessResponse)
    async def liveness() -> LivenessResponse:
        """Liveness probe — always 200 if the process is running."""
        return LivenessResponse()

    return router
