"""
Tests for the FastAPI application factory.
"""

from __future__ import annotations

import pytest

from spine.api.app import create_app
from spine.api.settings import SpineCoreAPISettings


class TestCreateApp:
    def test_returns_fastapi_instance(self):
        from fastapi import FastAPI
        app = create_app()
        assert isinstance(app, FastAPI)

    def test_has_openapi_url(self):
        app = create_app()
        assert app.openapi_url is not None
        assert "/api/v1/openapi.json" in app.openapi_url

    def test_custom_settings(self):
        s = SpineCoreAPISettings(api_prefix="/v2", api_title="Custom")
        app = create_app(settings=s)
        assert app.title == "Custom"

    def test_routes_registered(self):
        """Verify key routes are present."""
        app = create_app()
        paths = [r.path for r in app.routes]
        assert any("/api/v1/health" in p for p in paths)
        assert any("/api/v1/capabilities" in p for p in paths)
        assert any("/api/v1/workflows" in p for p in paths)
        assert any("/api/v1/runs" in p for p in paths)
        assert any("/api/v1/schedules" in p for p in paths)
        assert any("/api/v1/database" in p for p in paths)

    def test_cors_middleware_present(self):
        """App should have CORSMiddleware in middleware stack."""
        app = create_app()
        middleware_classes = [m.cls.__name__ for m in app.user_middleware]
        assert "CORSMiddleware" in middleware_classes

    def test_settings_on_state(self):
        s = SpineCoreAPISettings(debug=True)
        app = create_app(settings=s)
        assert app.state.settings.debug is True
