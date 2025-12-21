"""Tests for spine.core.config.container — lazy DI container.

Covers SpineContainer lazy property creation, lifecycle management,
context manager protocol, and the global convenience singleton.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from spine.core.config.container import SpineContainer, get_container


class TestSpineContainer:
    def test_init_with_no_settings(self):
        c = SpineContainer()
        assert c._settings is None
        assert c._engine is None
        assert c._scheduler is None
        assert c._cache is None
        assert c._executor is None
        assert c._event_bus is None

    def test_init_with_settings(self):
        settings = MagicMock()
        c = SpineContainer(settings)
        assert c._settings is settings

    @patch("spine.core.config.container.get_settings")
    def test_settings_lazy_creation(self, mock_get):
        mock_get.return_value = MagicMock()
        c = SpineContainer()
        s = c.settings
        mock_get.assert_called_once()
        assert s is mock_get.return_value

    def test_settings_uses_provided(self):
        settings = MagicMock()
        c = SpineContainer(settings)
        assert c.settings is settings

    @patch("spine.core.config.container.create_database_engine")
    def test_engine_lazy(self, mock_create):
        mock_create.return_value = MagicMock()
        s = MagicMock()
        c = SpineContainer(s)
        engine = c.engine
        mock_create.assert_called_once_with(s)
        assert engine is mock_create.return_value

    @patch("spine.core.config.container.create_database_engine")
    def test_engine_cached(self, mock_create):
        mock_create.return_value = MagicMock()
        c = SpineContainer(MagicMock())
        e1 = c.engine
        e2 = c.engine
        assert e1 is e2
        mock_create.assert_called_once()

    @patch("spine.core.config.container.create_scheduler_backend")
    def test_scheduler_lazy(self, mock_create):
        mock_create.return_value = MagicMock()
        c = SpineContainer(MagicMock())
        sched = c.scheduler
        mock_create.assert_called_once()
        assert sched is mock_create.return_value

    @patch("spine.core.config.container.create_cache_client")
    def test_cache_lazy(self, mock_create):
        mock_create.return_value = MagicMock()
        c = SpineContainer(MagicMock())
        cache = c.cache
        mock_create.assert_called_once()
        assert cache is mock_create.return_value

    @patch("spine.core.config.container.create_worker_executor")
    def test_executor_lazy(self, mock_create):
        mock_create.return_value = MagicMock()
        c = SpineContainer(MagicMock())
        exc = c.executor
        mock_create.assert_called_once()
        assert exc is mock_create.return_value

    @patch("spine.core.config.container.create_event_bus")
    def test_event_bus_lazy(self, mock_create):
        bus = MagicMock()
        mock_create.return_value = bus
        c = SpineContainer(MagicMock())
        with patch("spine.core.events.set_event_bus"):
            result = c.event_bus
        assert result is bus

    @patch("spine.core.config.container.create_event_bus")
    def test_event_bus_registers_global(self, mock_create):
        bus = MagicMock()
        mock_create.return_value = bus
        c = SpineContainer(MagicMock())
        with patch("spine.core.events.set_event_bus") as mock_set:
            c.event_bus
            mock_set.assert_called_once_with(bus)


class TestSpineContainerClose:
    def test_close_disposes_engine(self):
        c = SpineContainer(MagicMock())
        c._engine = MagicMock()
        c.close()
        c._engine.dispose.assert_called_once()

    def test_close_stops_scheduler(self):
        c = SpineContainer(MagicMock())
        c._scheduler = MagicMock()
        c.close()
        c._scheduler.stop.assert_called_once()

    def test_close_handles_missing_stop(self):
        c = SpineContainer(MagicMock())
        sched = MagicMock(spec=[])  # no stop method
        c._scheduler = sched
        c.close()  # should not raise

    def test_close_handles_dispose_error(self):
        c = SpineContainer(MagicMock())
        c._engine = MagicMock()
        c._engine.dispose.side_effect = RuntimeError("boom")
        c.close()  # should not raise

    def test_close_noop_when_nothing_created(self):
        c = SpineContainer(MagicMock())
        c.close()  # should not raise


class TestSpineContainerContextManager:
    def test_enter_returns_self(self):
        c = SpineContainer(MagicMock())
        assert c.__enter__() is c

    def test_exit_calls_close(self):
        c = SpineContainer(MagicMock())
        c._engine = MagicMock()
        c.__exit__(None, None, None)
        c._engine.dispose.assert_called_once()

    def test_with_statement(self):
        with SpineContainer(MagicMock()) as c:
            assert isinstance(c, SpineContainer)


class TestGetContainer:
    @patch("spine.core.config.container._global_container", None)
    @patch("spine.core.config.container.get_settings")
    def test_creates_singleton(self, mock_settings):
        mock_settings.return_value = MagicMock()
        c = get_container()
        assert isinstance(c, SpineContainer)

    @patch("spine.core.config.container._global_container", None)
    @patch("spine.core.config.container.get_settings")
    def test_returns_same_instance(self, mock_settings):
        mock_settings.return_value = MagicMock()
        c1 = get_container()
        c2 = get_container()
        assert c1 is c2
