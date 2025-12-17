"""Tests for spine.core.health — models, check logic, and router factory."""

from __future__ import annotations

import asyncio
import time

import pytest

from spine.core.health import (
    CheckResult,
    HealthCheck,
    HealthResponse,
    LivenessResponse,
    SpineHealth,
    _compute_status,
    _run_checks,
)


# ── Model unit tests ────────────────────────────────────────────────────


class TestCheckResult:
    def test_healthy(self):
        cr = CheckResult(status="healthy", latency_ms=1.5)
        assert cr.status == "healthy"
        assert cr.error is None

    def test_unhealthy_with_error(self):
        cr = CheckResult(status="unhealthy", error="connection refused")
        assert cr.error == "connection refused"


class TestHealthResponse:
    def test_defaults(self):
        hr = HealthResponse(service="test-svc", version="0.1.0")
        assert hr.status == "healthy"
        assert hr.service == "test-svc"
        assert hr.uptime_s >= 0
        assert hr.timestamp  # non-empty ISO string
        assert hr.checks == {}

    def test_with_checks(self):
        hr = HealthResponse(
            status="degraded",
            service="x",
            version="1.0",
            checks={"pg": CheckResult(status="healthy", latency_ms=2.0)},
        )
        assert hr.checks["pg"].latency_ms == 2.0

    def test_serialization_roundtrip(self):
        hr = HealthResponse(service="svc", version="1.0")
        data = hr.model_dump()
        assert data["status"] == "healthy"
        hr2 = HealthResponse.model_validate(data)
        assert hr2.service == "svc"


class TestLivenessResponse:
    def test_always_alive(self):
        lr = LivenessResponse()
        assert lr.status == "alive"


class TestSpineHealthLegacy:
    def test_backwards_compat(self):
        sh = SpineHealth(name="test", version="0.1.0", status="ok")
        assert sh.name == "test"
        assert sh.uptime_s >= 0


# ── Check logic tests ───────────────────────────────────────────────────


async def _ok_check():
    return True


async def _fail_check():
    raise RuntimeError("boom")


async def _slow_check():
    await asyncio.sleep(10)
    return True


class TestRunChecks:
    @pytest.mark.asyncio
    async def test_all_healthy(self):
        checks = [HealthCheck("a", _ok_check), HealthCheck("b", _ok_check)]
        results = await _run_checks(checks)
        assert results["a"].status == "healthy"
        assert results["b"].status == "healthy"
        assert results["a"].latency_ms is not None

    @pytest.mark.asyncio
    async def test_failure(self):
        checks = [HealthCheck("bad", _fail_check)]
        results = await _run_checks(checks)
        assert results["bad"].status == "unhealthy"
        assert "boom" in results["bad"].error

    @pytest.mark.asyncio
    async def test_timeout(self):
        checks = [HealthCheck("slow", _slow_check, timeout_s=0.1)]
        results = await _run_checks(checks)
        assert results["slow"].status == "unhealthy"
        assert results["slow"].error == "timeout"


class TestComputeStatus:
    def test_all_healthy(self):
        checks = [HealthCheck("a", _ok_check)]
        results = {"a": CheckResult(status="healthy")}
        assert _compute_status(results, checks) == "healthy"

    def test_required_down(self):
        checks = [HealthCheck("db", _ok_check, required=True)]
        results = {"db": CheckResult(status="unhealthy")}
        assert _compute_status(results, checks) == "unhealthy"

    def test_optional_down(self):
        checks = [HealthCheck("cache", _ok_check, required=False)]
        results = {"cache": CheckResult(status="unhealthy")}
        assert _compute_status(results, checks) == "degraded"

    def test_mixed(self):
        checks = [
            HealthCheck("db", _ok_check, required=True),
            HealthCheck("cache", _ok_check, required=False),
        ]
        results = {
            "db": CheckResult(status="healthy"),
            "cache": CheckResult(status="unhealthy"),
        }
        assert _compute_status(results, checks) == "degraded"

    def test_required_and_optional_down(self):
        checks = [
            HealthCheck("db", _ok_check, required=True),
            HealthCheck("cache", _ok_check, required=False),
        ]
        results = {
            "db": CheckResult(status="unhealthy"),
            "cache": CheckResult(status="unhealthy"),
        }
        assert _compute_status(results, checks) == "unhealthy"

    def test_no_checks(self):
        assert _compute_status({}, []) == "healthy"


# ── Router factory tests ────────────────────────────────────────────────


class TestCreateHealthRouter:
    """Tests that require fastapi (optional dep)."""

    @pytest.fixture
    def client(self):
        """Create a TestClient with the health router mounted."""
        try:
            from fastapi import FastAPI
            from fastapi.testclient import TestClient
        except ImportError:
            pytest.skip("fastapi not installed")

        from spine.core.health import create_health_router

        app = FastAPI()
        router = create_health_router(
            service_name="test-service",
            version="1.2.3",
            checks=[
                HealthCheck("ok-dep", _ok_check, required=True),
                HealthCheck("opt-dep", _ok_check, required=False),
            ],
        )
        app.include_router(router)
        return TestClient(app)

    def test_health_endpoint(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["service"] == "test-service"
        assert data["version"] == "1.2.3"
        assert "ok-dep" in data["checks"]
        assert data["checks"]["ok-dep"]["status"] == "healthy"

    def test_ready_endpoint(self, client):
        resp = client.get("/health/ready")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"

    def test_live_endpoint(self, client):
        resp = client.get("/health/live")
        assert resp.status_code == 200
        assert resp.json()["status"] == "alive"

    def test_unhealthy_returns_503(self):
        try:
            from fastapi import FastAPI
            from fastapi.testclient import TestClient
        except ImportError:
            pytest.skip("fastapi not installed")

        from spine.core.health import create_health_router

        app = FastAPI()
        router = create_health_router(
            service_name="sick",
            version="0.0.1",
            checks=[HealthCheck("db", _fail_check, required=True)],
        )
        app.include_router(router)
        client = TestClient(app)

        resp = client.get("/health")
        assert resp.status_code == 503
        assert resp.json()["status"] == "unhealthy"

    def test_degraded_ready_returns_503(self):
        try:
            from fastapi import FastAPI
            from fastapi.testclient import TestClient
        except ImportError:
            pytest.skip("fastapi not installed")

        from spine.core.health import create_health_router

        app = FastAPI()
        router = create_health_router(
            service_name="meh",
            version="0.0.1",
            checks=[HealthCheck("cache", _fail_check, required=False)],
        )
        app.include_router(router)
        client = TestClient(app)

        resp = client.get("/health/ready")
        assert resp.status_code == 503
        assert resp.json()["status"] == "degraded"

    def test_no_checks_is_healthy(self):
        try:
            from fastapi import FastAPI
            from fastapi.testclient import TestClient
        except ImportError:
            pytest.skip("fastapi not installed")

        from spine.core.health import create_health_router

        app = FastAPI()
        router = create_health_router(service_name="bare", version="0.0.1", checks=[])
        app.include_router(router)
        client = TestClient(app)

        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"
        assert resp.json()["checks"] == {}
