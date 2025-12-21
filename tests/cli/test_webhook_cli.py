"""Tests for ``spine-core webhook`` CLI commands."""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from spine.cli.webhook import app

runner = CliRunner()


@dataclass
class _WebhookTarget:
    """Simple stand-in for webhook target to support format strings."""
    kind: str
    name: str
    description: str


class TestWebhookList:
    @patch("spine.ops.webhooks.list_registered_webhooks")
    def test_list_empty(self, mock_list):
        mock_list.return_value = []

        result = runner.invoke(app, ["list"])
        assert result.exit_code == 0
        assert "No webhook" in result.output

    @patch("spine.ops.webhooks.list_registered_webhooks")
    def test_list_with_targets(self, mock_list):
        target = _WebhookTarget(kind="workflow", name="etl.daily", description="Daily ETL")
        mock_list.return_value = [target]

        result = runner.invoke(app, ["list"])
        assert result.exit_code == 0
        assert "workflow" in result.output
        assert "etl.daily" in result.output

    @patch("spine.ops.webhooks.list_registered_webhooks")
    def test_list_multiple(self, mock_list):
        t1 = _WebhookTarget(kind="workflow", name="wf-a", description="A")
        t2 = _WebhookTarget(kind="operation", name="pl-b", description="B")
        mock_list.return_value = [t1, t2]

        result = runner.invoke(app, ["list"])
        assert result.exit_code == 0
        assert "wf-a" in result.output
        assert "pl-b" in result.output


class TestWebhookRegister:
    @patch("spine.ops.webhooks.register_webhook")
    def test_register_default(self, mock_register):
        result = runner.invoke(app, ["register", "my-workflow"])
        assert result.exit_code == 0
        assert "Registered" in result.output
        mock_register.assert_called_once_with("my-workflow", kind="workflow", description="")

    @patch("spine.ops.webhooks.register_webhook")
    def test_register_operation(self, mock_register):
        result = runner.invoke(app, ["register", "my-operation", "--kind", "operation"])
        assert result.exit_code == 0
        mock_register.assert_called_once_with("my-operation", kind="operation", description="")

    @patch("spine.ops.webhooks.register_webhook")
    def test_register_with_description(self, mock_register):
        result = runner.invoke(app, [
            "register", "daily-etl",
            "--kind", "workflow",
            "--description", "Run daily ETL",
        ])
        assert result.exit_code == 0
        mock_register.assert_called_once_with(
            "daily-etl", kind="workflow", description="Run daily ETL",
        )
