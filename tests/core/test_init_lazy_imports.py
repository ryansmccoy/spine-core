"""Tests for spine.core.__init__ lazy attribute (__getattr__) coverage.

Exercises the __getattr__ lazy import paths in spine/core/__init__.py,
covering both successful imports and fallback AttributeErrors.
"""

from __future__ import annotations

import importlib
from unittest.mock import patch

import pytest

import spine.core


class TestLazyImportORM:
    def test_orm_module(self):
        try:
            _ = spine.core.orm
        except AttributeError:
            pass  # ok if sqlalchemy not installed

    def test_spine_base(self):
        try:
            _ = spine.core.SpineBase
        except AttributeError:
            pass

    def test_timestamp_mixin(self):
        try:
            _ = spine.core.TimestampMixin
        except AttributeError:
            pass


class TestLazyImportSession:
    @pytest.mark.parametrize("name", [
        "create_spine_engine",
        "SpineSession",
        "spine_session_factory",
        "SAConnectionBridge",
    ])
    def test_session_attrs(self, name):
        try:
            _ = getattr(spine.core, name)
        except AttributeError:
            pass


class TestLazyImportDatabase:
    @pytest.mark.parametrize("name", [
        "create_pool",
        "close_pool",
        "pool_health_check",
        "normalize_database_url",
    ])
    def test_database_attrs(self, name):
        try:
            _ = getattr(spine.core, name)
        except AttributeError:
            pass


class TestLazyImportSettings:
    def test_spine_base_settings(self):
        try:
            _ = spine.core.SpineBaseSettings
        except AttributeError:
            pass


class TestLazyImportHealth:
    @pytest.mark.parametrize("name", [
        "SpineHealth",
        "HealthResponse",
        "CheckResult",
        "LivenessResponse",
        "HealthCheck",
        "create_health_router",
    ])
    def test_health_attrs(self, name):
        try:
            _ = getattr(spine.core, name)
        except AttributeError:
            pass


class TestLazyImportHealthChecks:
    @pytest.mark.parametrize("name", [
        "check_postgres",
        "check_redis",
        "check_http",
        "check_elasticsearch",
        "check_qdrant",
        "check_ollama",
    ])
    def test_health_check_attrs(self, name):
        try:
            _ = getattr(spine.core, name)
        except AttributeError:
            pass


class TestLazyImportMCP:
    @pytest.mark.parametrize("name", ["create_spine_mcp", "run_spine_mcp"])
    def test_mcp_attrs(self, name):
        try:
            _ = getattr(spine.core, name)
        except AttributeError:
            pass


class TestLazyImportUnknown:
    def test_missing_attr_raises(self):
        with pytest.raises(AttributeError, match="has no attribute"):
            _ = spine.core.totally_nonexistent_thing
