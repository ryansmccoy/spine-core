"""Tests for auth and rate-limit middleware.

Uses the real FastAPI test client to exercise the middleware stack.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from spine.api.middleware.auth import AuthMiddleware
from spine.api.middleware.rate_limit import RateLimitMiddleware


# =============================================================================
# Auth middleware
# =============================================================================


def _make_app(api_key: str | None = None) -> FastAPI:
    """Create a minimal FastAPI app with auth middleware."""
    app = FastAPI()
    app.add_middleware(AuthMiddleware, api_key=api_key)

    @app.get("/api/v1/test")
    def _test():
        return {"status": "ok"}

    @app.get("/health/ready")
    def _health():
        return {"status": "healthy"}

    @app.get("/api/v1/docs")
    def _docs():
        return {"docs": True}

    @app.get("/metrics")
    def _metrics():
        return "ok"

    return app


class TestAuthMiddleware:
    """AuthMiddleware tests."""

    def test_no_key_configured_allows_all(self):
        client = TestClient(_make_app(api_key=None))
        resp = client.get("/api/v1/test")
        assert resp.status_code == 200

    def test_key_required_rejects_missing(self):
        client = TestClient(_make_app(api_key="secret-key"))
        resp = client.get("/api/v1/test")
        assert resp.status_code == 401
        assert "API key" in resp.json()["detail"]

    def test_key_required_accepts_valid_header(self):
        client = TestClient(_make_app(api_key="secret-key"))
        resp = client.get("/api/v1/test", headers={"X-API-Key": "secret-key"})
        assert resp.status_code == 200

    def test_key_required_accepts_query_param(self):
        client = TestClient(_make_app(api_key="secret-key"))
        resp = client.get("/api/v1/test?api_key=secret-key")
        assert resp.status_code == 200

    def test_key_required_rejects_wrong_key(self):
        client = TestClient(_make_app(api_key="secret-key"))
        resp = client.get("/api/v1/test", headers={"X-API-Key": "wrong-key"})
        assert resp.status_code == 401

    def test_health_bypassed(self):
        client = TestClient(_make_app(api_key="secret-key"))
        resp = client.get("/health/ready")
        assert resp.status_code == 200

    def test_metrics_bypassed(self):
        client = TestClient(_make_app(api_key="secret-key"))
        resp = client.get("/metrics")
        assert resp.status_code == 200

    def test_docs_bypassed(self):
        client = TestClient(_make_app(api_key="secret-key"))
        resp = client.get("/api/v1/docs")
        assert resp.status_code == 200


# =============================================================================
# Rate-limit middleware
# =============================================================================


def _make_rate_app(enabled: bool = True, rpm: int = 5) -> FastAPI:
    """Create a minimal FastAPI app with rate-limit middleware."""
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware, enabled=enabled, rpm=rpm)

    @app.get("/api/v1/test")
    def _test():
        return {"status": "ok"}

    return app


class TestRateLimitMiddleware:
    """RateLimitMiddleware tests."""

    def test_disabled_allows_unlimited(self):
        client = TestClient(_make_rate_app(enabled=False))
        for _ in range(20):
            resp = client.get("/api/v1/test")
            assert resp.status_code == 200

    def test_enabled_allows_within_limit(self):
        client = TestClient(_make_rate_app(enabled=True, rpm=5))
        for _ in range(5):
            resp = client.get("/api/v1/test")
            assert resp.status_code == 200

    def test_enabled_rejects_over_limit(self):
        client = TestClient(_make_rate_app(enabled=True, rpm=3))
        responses = [client.get("/api/v1/test") for _ in range(5)]
        statuses = [r.status_code for r in responses]
        assert 429 in statuses

    def test_rate_limit_headers_present(self):
        client = TestClient(_make_rate_app(enabled=True, rpm=10))
        resp = client.get("/api/v1/test")
        assert resp.status_code == 200
        assert "X-RateLimit-Limit" in resp.headers
        assert "X-RateLimit-Remaining" in resp.headers
        assert resp.headers["X-RateLimit-Limit"] == "10"

    def test_retry_after_on_429(self):
        client = TestClient(_make_rate_app(enabled=True, rpm=1))
        client.get("/api/v1/test")  # First request OK
        resp = client.get("/api/v1/test")  # Second should fail
        assert resp.status_code == 429
        assert "Retry-After" in resp.headers

    def test_429_response_body(self):
        client = TestClient(_make_rate_app(enabled=True, rpm=1))
        client.get("/api/v1/test")
        resp = client.get("/api/v1/test")
        assert resp.status_code == 429
        body = resp.json()
        assert body["status"] == 429
        assert "Rate limit" in body["detail"]
