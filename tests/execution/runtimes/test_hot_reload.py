"""Tests for Idea #7 — Hot-Reload Adapter.

Covers:
- Config change detection (hash-based)
- Adapter replacement on config change
- Manual update_config / force_reload
- Config source polling
- on_reload callback
- Protocol delegation (submit/status/cancel/logs/cleanup)
- Health check with reload metadata
- Check interval throttling
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from spine.execution.runtimes._types import (
    ContainerJobSpec,
    JobStatus,
    RuntimeCapabilities,
)
from spine.execution.runtimes.hot_reload import HotReloadAdapter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_adapter(config: dict[str, Any] | None = None) -> MagicMock:
    """Create a mock adapter with standard async methods."""
    adapter = MagicMock()
    adapter.name = f"mock-{config.get('version', '0') if config else '0'}"
    adapter.capabilities = RuntimeCapabilities(
        supports_gpu=False,
        supports_volumes=True,
    )
    adapter.submit = AsyncMock(return_value="container-123")
    adapter.status = AsyncMock(return_value=JobStatus(state="running"))
    adapter.cancel = AsyncMock(return_value=True)
    adapter.logs = AsyncMock(return_value=iter(["log line 1"]))
    adapter.cleanup = AsyncMock(return_value=None)
    adapter.health_check = AsyncMock(return_value={"status": "healthy"})
    return adapter


def _make_spec() -> ContainerJobSpec:
    return ContainerJobSpec(name="test-job", image="test:latest")


_adapters_created: list[dict] = []


def _tracking_factory(config: dict[str, Any]) -> MagicMock:
    """Factory that tracks what configs it was called with."""
    _adapters_created.append(config)
    return _make_mock_adapter(config)


# ---------------------------------------------------------------------------
# Config change detection
# ---------------------------------------------------------------------------

class TestConfigChangeDetection:
    def test_no_change_returns_false(self):
        hot = HotReloadAdapter(
            initial_config={"key": "val"},
            adapter_factory=_make_mock_adapter,
        )
        result = hot.update_config({"key": "val"})
        assert result is False
        assert hot.reload_count == 0

    def test_change_returns_true(self):
        hot = HotReloadAdapter(
            initial_config={"key": "old"},
            adapter_factory=_make_mock_adapter,
        )
        result = hot.update_config({"key": "new"})
        assert result is True
        assert hot.reload_count == 1

    def test_current_config_reflects_update(self):
        hot = HotReloadAdapter(
            initial_config={"v": 1},
            adapter_factory=_make_mock_adapter,
        )
        hot.update_config({"v": 2})
        assert hot.current_config == {"v": 2}

    def test_current_config_is_deep_copy(self):
        hot = HotReloadAdapter(
            initial_config={"nested": {"a": 1}},
            adapter_factory=_make_mock_adapter,
        )
        cfg = hot.current_config
        cfg["nested"]["a"] = 999
        assert hot.current_config["nested"]["a"] == 1


# ---------------------------------------------------------------------------
# Adapter replacement
# ---------------------------------------------------------------------------

class TestAdapterReplacement:
    def test_factory_called_on_reload(self):
        created = []

        def tracking_factory(cfg):
            created.append(cfg)
            return _make_mock_adapter(cfg)

        hot = HotReloadAdapter(
            initial_config={"v": 1},
            adapter_factory=tracking_factory,
        )
        assert len(created) == 1

        hot.update_config({"v": 2})
        assert len(created) == 2
        assert created[-1] == {"v": 2}

    def test_inner_adapter_changes(self):
        hot = HotReloadAdapter(
            initial_config={"version": "1"},
            adapter_factory=_make_mock_adapter,
        )
        old_inner = hot.inner
        hot.update_config({"version": "2"})
        assert hot.inner is not old_inner

    def test_force_reload(self):
        hot = HotReloadAdapter(
            initial_config={"v": 1},
            adapter_factory=_make_mock_adapter,
        )
        old_inner = hot.inner
        hot.force_reload()
        assert hot.inner is not old_inner
        assert hot.reload_count == 1


# ---------------------------------------------------------------------------
# on_reload callback
# ---------------------------------------------------------------------------

class TestOnReloadCallback:
    def test_callback_invoked_on_change(self):
        calls = []

        def on_reload(old, new):
            calls.append((old, new))

        hot = HotReloadAdapter(
            initial_config={"v": 1},
            adapter_factory=_make_mock_adapter,
            on_reload=on_reload,
        )
        hot.update_config({"v": 2})

        assert len(calls) == 1
        assert calls[0] == ({"v": 1}, {"v": 2})

    def test_callback_error_does_not_prevent_reload(self):
        def bad_callback(old, new):
            raise RuntimeError("callback failed")

        hot = HotReloadAdapter(
            initial_config={"v": 1},
            adapter_factory=_make_mock_adapter,
            on_reload=bad_callback,
        )
        # Should not raise
        hot.update_config({"v": 2})
        assert hot.reload_count == 1


# ---------------------------------------------------------------------------
# Config source polling
# ---------------------------------------------------------------------------

class TestConfigSourcePolling:
    def test_source_polled_on_submit(self):
        call_count = {"n": 0}

        def source():
            call_count["n"] += 1
            return {"v": call_count["n"]}

        hot = HotReloadAdapter(
            initial_config={"v": 0},
            adapter_factory=_make_mock_adapter,
            config_source=source,
            check_interval_seconds=0,  # Always check
        )

        spec = _make_spec()
        asyncio.run(hot.submit(spec))

        assert call_count["n"] >= 1
        assert hot.reload_count >= 1

    def test_throttled_by_interval(self):
        call_count = {"n": 0}

        def source():
            call_count["n"] += 1
            return {"v": 0}  # Same config, no reload

        hot = HotReloadAdapter(
            initial_config={"v": 0},
            adapter_factory=_make_mock_adapter,
            config_source=source,
            check_interval_seconds=9999,  # Long interval
        )

        spec = _make_spec()
        asyncio.run(hot.submit(spec))  # First call triggers check
        c1 = call_count["n"]
        asyncio.run(hot.submit(spec))  # Should be throttled
        c2 = call_count["n"]

        # Second call should not trigger another source check
        assert c2 == c1

    def test_source_error_is_handled(self):
        def bad_source():
            raise ConnectionError("config server down")

        hot = HotReloadAdapter(
            initial_config={"v": 1},
            adapter_factory=_make_mock_adapter,
            config_source=bad_source,
            check_interval_seconds=0,
        )

        spec = _make_spec()
        # Should not raise
        asyncio.run(hot.submit(spec))
        assert hot.reload_count == 0  # No reload on error


# ---------------------------------------------------------------------------
# Protocol delegation
# ---------------------------------------------------------------------------

class TestDelegation:
    def test_submit_delegates(self):
        adapter = _make_mock_adapter()
        hot = HotReloadAdapter(
            initial_config={},
            adapter_factory=lambda cfg: adapter,
        )
        spec = _make_spec()
        result = asyncio.run(hot.submit(spec))

        assert result == "container-123"
        adapter.submit.assert_called_once_with(spec)

    def test_status_delegates(self):
        adapter = _make_mock_adapter()
        hot = HotReloadAdapter(
            initial_config={},
            adapter_factory=lambda cfg: adapter,
        )
        result = asyncio.run(hot.status("ref-1"))

        assert result.state == "running"
        adapter.status.assert_called_once_with("ref-1")

    def test_cancel_delegates(self):
        adapter = _make_mock_adapter()
        hot = HotReloadAdapter(
            initial_config={},
            adapter_factory=lambda cfg: adapter,
        )
        result = asyncio.run(hot.cancel("ref-1"))
        assert result is True

    def test_cleanup_delegates(self):
        adapter = _make_mock_adapter()
        hot = HotReloadAdapter(
            initial_config={},
            adapter_factory=lambda cfg: adapter,
        )
        asyncio.run(hot.cleanup("ref-1"))
        adapter.cleanup.assert_called_once_with("ref-1")


# ---------------------------------------------------------------------------
# Name and health check
# ---------------------------------------------------------------------------

class TestNameAndHealth:
    def test_name_wraps_inner(self):
        hot = HotReloadAdapter(
            initial_config={"version": "1"},
            adapter_factory=_make_mock_adapter,
        )
        assert "hot_reload" in hot.name
        assert "mock-1" in hot.name

    def test_health_check_includes_reload_info(self):
        hot = HotReloadAdapter(
            initial_config={"v": 1},
            adapter_factory=_make_mock_adapter,
        )
        hot.update_config({"v": 2})
        health = asyncio.run(hot.health_check())

        assert "hot_reload" in health
        assert health["hot_reload"]["reload_count"] == 1
        assert "config_hash" in health["hot_reload"]


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_empty_config(self):
        hot = HotReloadAdapter(
            initial_config={},
            adapter_factory=_make_mock_adapter,
        )
        assert hot.reload_count == 0
        assert hot.current_config == {}

    def test_complex_config_hashing(self):
        hot = HotReloadAdapter(
            initial_config={"nested": {"a": [1, 2, 3]}, "b": True},
            adapter_factory=_make_mock_adapter,
        )
        # Same content, different order — should be same hash
        result = hot.update_config({"b": True, "nested": {"a": [1, 2, 3]}})
        assert result is False

    def test_multiple_reloads(self):
        hot = HotReloadAdapter(
            initial_config={"v": 0},
            adapter_factory=_make_mock_adapter,
        )
        for i in range(1, 6):
            hot.update_config({"v": i})
        assert hot.reload_count == 5
        assert hot.current_config == {"v": 5}
