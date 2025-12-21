"""
Tests for API settings.
"""

from __future__ import annotations

import pytest

from spine.api.settings import SpineCoreAPISettings


class TestSpineCoreAPISettings:
    def test_defaults(self):
        s = SpineCoreAPISettings()
        assert s.host == "0.0.0.0"
        assert s.port == 12000
        assert s.api_prefix == "/api/v1"
        assert s.debug is False
        assert s.cors_origins == ["http://localhost:3000", "http://localhost:5173", "http://localhost:12000"]
        assert s.rate_limit_enabled is False
        assert s.api_key is None

    def test_custom_values(self):
        s = SpineCoreAPISettings(
            port=9000,
            api_prefix="/v2",
            debug=True,
            rate_limit_rpm=60,
        )
        assert s.port == 9000
        assert s.api_prefix == "/v2"
        assert s.debug is True
        assert s.rate_limit_rpm == 60

    def test_database_url_default(self):
        s = SpineCoreAPISettings()
        assert "sqlite" in s.database_url

    def test_env_prefix(self):
        """Settings should read SPINE_ prefixed env vars."""
        assert SpineCoreAPISettings.model_config["env_prefix"] == "SPINE_"
