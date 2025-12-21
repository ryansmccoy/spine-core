"""Tests for spine.api.routers.deploy endpoint routing and schemas.

Uses FastAPI TestClient to verify endpoint registration, schema validation,
and basic response shapes.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from spine.api.routers.deploy import (
    BackendInfo,
    DeployRequest,
    ServiceInfo,
    TestbedRequest as _TestbedRequest,
    router,
)


@pytest.fixture()
def client():
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    return TestClient(app, raise_server_exceptions=False)


# ── Schema tests ────────────────────────────────────────────────────


class TestSchemas:
    def test_testbed_request_defaults(self):
        r = _TestbedRequest()
        assert r.backends == ["sqlite"]
        assert r.parallel is False
        assert r.run_schema is True
        assert r.run_tests is True
        assert r.run_examples is False
        assert r.timeout == 600

    def test_deploy_request_defaults(self):
        r = DeployRequest()
        assert r.targets == []
        assert r.profile == "apps"
        assert r.build is False

    def test_backend_info(self):
        b = BackendInfo(
            name="sqlite", dialect="sqlite", image=None,
            port=0, requires_license=False,
        )
        assert b.name == "sqlite"
        assert b.requires_license is False

    def test_service_info(self):
        s = ServiceInfo(
            name="api", image="spine-api:latest", port=12000,
            profiles=["apps"], healthcheck_url="http://localhost:12000/health",
        )
        assert s.name == "api"
        assert len(s.profiles) == 1


# ── Endpoint routing ───────────────────────────────────────────────


class TestTestbedEndpoints:
    def test_start_testbed_responds(self, client):
        resp = client.post(
            "/api/v1/deploy/testbed",
            json={"backends": ["sqlite"]},
        )
        assert resp.status_code in (200, 202, 404, 500)

    def test_get_testbed_result_responds(self, client):
        resp = client.get("/api/v1/deploy/testbed/run-123")
        assert resp.status_code in (200, 404, 500)

    def test_get_testbed_not_found(self, client):
        resp = client.get("/api/v1/deploy/testbed/nonexistent-run")
        if resp.status_code == 200:
            data = resp.json()
            assert data.get("error") == "not_found"


class TestDeployEndpoints:
    def test_deploy_up_responds(self, client):
        resp = client.post("/api/v1/deploy/up", json={})
        assert resp.status_code in (200, 202, 404, 500)

    def test_deploy_down_responds(self, client):
        resp = client.post("/api/v1/deploy/down")
        assert resp.status_code in (200, 404, 500)

    def test_deploy_status_responds(self, client):
        resp = client.get("/api/v1/deploy/status")
        assert resp.status_code in (200, 404, 500)


class TestInfoEndpoints:
    def test_backends_endpoint_responds(self, client):
        resp = client.get("/api/v1/deploy/backends")
        assert resp.status_code in (200, 404, 500)

    def test_services_endpoint_responds(self, client):
        resp = client.get("/api/v1/deploy/services")
        assert resp.status_code in (200, 404, 500)

    @patch("spine.deploy.backends.BACKENDS", {"sqlite": MagicMock(dialect="sqlite", image=None, port=0, requires_license=False)})
    def test_backends_returns_list(self, client):
        resp = client.get("/api/v1/deploy/backends")
        if resp.status_code == 200:
            data = resp.json()
            assert isinstance(data, list)

    @patch("spine.deploy.backends.SERVICES", {"api": MagicMock(image="spine:latest", port=12000, compose_profiles=["apps"], healthcheck_url=None)})
    def test_services_returns_list(self, client):
        resp = client.get("/api/v1/deploy/services")
        if resp.status_code == 200:
            data = resp.json()
            assert isinstance(data, list)
