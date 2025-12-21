"""Tests for ``spine-core events`` CLI commands."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from spine.cli.events import app

runner = CliRunner()


class TestEventsStatus:
    @patch("spine.core.events.get_event_bus")
    def test_status_text(self, mock_bus_factory):
        bus = MagicMock()
        type(bus).__name__ = "InMemoryEventBus"
        bus.subscription_count = 3
        bus._closed = False
        mock_bus_factory.return_value = bus

        result = runner.invoke(app, ["status"])
        assert result.exit_code == 0
        assert "InMemoryEventBus" in result.output
        assert "3" in result.output

    @patch("spine.core.events.get_event_bus")
    def test_status_json(self, mock_bus_factory):
        bus = MagicMock()
        type(bus).__name__ = "InMemoryEventBus"
        bus.subscription_count = 0
        bus._closed = True
        mock_bus_factory.return_value = bus

        result = runner.invoke(app, ["status", "--json"])
        assert result.exit_code == 0
        assert "InMemoryEventBus" in result.output

    @patch("spine.core.events.get_event_bus")
    def test_status_no_subscription_count(self, mock_bus_factory):
        bus = MagicMock(spec=[])
        type(bus).__name__ = "CustomBus"
        mock_bus_factory.return_value = bus

        result = runner.invoke(app, ["status"])
        assert result.exit_code == 0
        assert "CustomBus" in result.output


class TestEventsPublish:
    @patch("spine.core.events.get_event_bus")
    @patch("spine.core.events.Event")
    def test_publish_simple(self, mock_event_cls, mock_bus_factory):
        event = MagicMock()
        event.event_id = "evt-1"
        event.event_type = "run.started"
        mock_event_cls.return_value = event

        bus = MagicMock()
        bus.publish = AsyncMock()
        mock_bus_factory.return_value = bus

        result = runner.invoke(app, ["publish", "run.started"])
        assert result.exit_code == 0

    @patch("spine.core.events.get_event_bus")
    @patch("spine.core.events.Event")
    def test_publish_with_payload(self, mock_event_cls, mock_bus_factory):
        event = MagicMock()
        event.event_id = "evt-2"
        event.event_type = "run.completed"
        mock_event_cls.return_value = event

        bus = MagicMock()
        bus.publish = AsyncMock()
        mock_bus_factory.return_value = bus

        result = runner.invoke(app, [
            "publish", "run.completed",
            "--payload", '{"run_id": "abc"}',
            "--source", "test-cli",
        ])
        assert result.exit_code == 0

    @patch("spine.core.events.get_event_bus")
    @patch("spine.core.events.Event")
    def test_publish_json_output(self, mock_event_cls, mock_bus_factory):
        event = MagicMock()
        event.event_id = "evt-3"
        event.event_type = "test.event"
        mock_event_cls.return_value = event

        bus = MagicMock()
        bus.publish = AsyncMock()
        mock_bus_factory.return_value = bus

        result = runner.invoke(app, ["publish", "test.event", "--json"])
        assert result.exit_code == 0
        assert "event_id" in result.output

    def test_publish_invalid_payload(self):
        result = runner.invoke(app, ["publish", "test.event", "--payload", "not-json"])
        assert result.exit_code == 1
