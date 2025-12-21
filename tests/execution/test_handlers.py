"""Tests for spine.execution.handlers — built-in example handlers.

Tests cover all 5 task handlers (echo, sleep, add, fail, transform) and
the etl_stub operation handler. These are pure functions registered into
the global HandlerRegistry.
"""

from __future__ import annotations

import pytest

# Importing registers the handlers into the global registry
import spine.execution.handlers  # noqa: F401
from spine.execution.registry import get_default_registry


def _get(kind: str, name: str):
    """Lookup a handler from the default registry."""
    return get_default_registry().get(kind, name)


class TestEchoHandler:
    def test_echo_returns_params(self):
        handler = _get("task", "echo")
        assert handler is not None
        result = handler({"key": "value", "n": 42})
        assert result == {"echoed": {"key": "value", "n": 42}}

    def test_echo_empty_params(self):
        handler = _get("task", "echo")
        result = handler({})
        assert result == {"echoed": {}}


class TestSleepHandler:
    def test_sleep_default(self):
        handler = _get("task", "sleep")
        assert handler is not None
        result = handler({"seconds": 0.001})
        assert result["slept"] == 0.001

    def test_sleep_returns_duration(self):
        handler = _get("task", "sleep")
        result = handler({"seconds": 0})
        assert "slept" in result


class TestAddHandler:
    def test_add_two_numbers(self):
        handler = _get("task", "add")
        result = handler({"a": 3, "b": 7})
        assert result == {"a": 3, "b": 7, "result": 10}

    def test_add_defaults_to_zero(self):
        handler = _get("task", "add")
        result = handler({})
        assert result == {"a": 0, "b": 0, "result": 0}

    def test_add_floats(self):
        handler = _get("task", "add")
        result = handler({"a": 1.5, "b": 2.5})
        assert result["result"] == 4.0


class TestFailHandler:
    def test_fail_raises(self):
        handler = _get("task", "fail")
        with pytest.raises(RuntimeError, match="intentional test failure"):
            handler({})

    def test_fail_custom_message(self):
        handler = _get("task", "fail")
        with pytest.raises(RuntimeError, match="custom error"):
            handler({"message": "custom error"})


class TestTransformHandler:
    def test_transform_upper(self):
        handler = _get("task", "transform")
        result = handler({"value": "hello", "operation": "upper"})
        assert result["result"] == "HELLO"
        assert result["original"] == "hello"
        assert result["operation"] == "upper"

    def test_transform_lower(self):
        handler = _get("task", "transform")
        result = handler({"value": "HELLO", "operation": "lower"})
        assert result["result"] == "hello"

    def test_transform_reverse(self):
        handler = _get("task", "transform")
        result = handler({"value": "abc", "operation": "reverse"})
        assert result["result"] == "cba"

    def test_transform_unknown_op(self):
        handler = _get("task", "transform")
        result = handler({"value": "abc", "operation": "unknown"})
        assert result["result"] == "abc"

    def test_transform_default_upper(self):
        handler = _get("task", "transform")
        result = handler({"value": "test"})
        assert result["result"] == "TEST"


class TestEtlStubOperation:
    def test_etl_stub_runs(self):
        handler = _get("operation", "etl_stub")
        assert handler is not None
        result = handler({"phase_delay": 0, "records": 50})
        assert result["operation"] == "etl_stub"
        assert result["total_records"] == 50
        assert len(result["phases"]) == 3

    def test_etl_stub_phases(self):
        handler = _get("operation", "etl_stub")
        result = handler({"phase_delay": 0, "records": 100})
        phases = result["phases"]
        assert phases[0]["phase"] == "extract"
        assert phases[1]["phase"] == "transform"
        assert phases[2]["phase"] == "load"

    def test_etl_stub_defaults(self):
        handler = _get("operation", "etl_stub")
        result = handler({})
        assert result["total_records"] == 100


class TestRegistryContents:
    """Verify handler registration."""

    def test_tasks_registered(self):
        registry = get_default_registry()
        for name in ("echo", "sleep", "add", "fail", "transform"):
            assert registry.has("task", name), f"Task {name} not registered"

    def test_operation_registered(self):
        registry = get_default_registry()
        assert registry.has("operation", "etl_stub")
