"""Tests for ``spine.core.transports.mcp`` — shared MCP server scaffold."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest


class TestCreateSpineMcp:
    @patch("spine.core.transports.mcp.FastMCP")
    def test_create_spine_mcp(self, mock_fastmcp_cls):
        from spine.core.transports.mcp import create_spine_mcp

        mock_server = MagicMock()
        mock_fastmcp_cls.return_value = mock_server

        async def fake_lifespan(server):
            yield {}

        result = create_spine_mcp(
            name="test-spine",
            instructions="Test spine MCP server",
            lifespan=fake_lifespan,
        )
        assert result is mock_server
        mock_fastmcp_cls.assert_called_once_with(
            "test-spine",
            instructions="Test spine MCP server",
            lifespan=fake_lifespan,
        )


class TestRunSpineMcp:
    @patch("spine.core.transports.mcp.logging")
    def test_run_stdio_default(self, mock_logging):
        from spine.core.transports.mcp import run_spine_mcp

        mcp = MagicMock()
        mcp.name = "test"

        with patch.object(sys, "argv", ["test"]):
            run_spine_mcp(mcp)

        mcp.run.assert_called_once_with(transport="stdio")

    @patch("spine.core.transports.mcp.logging")
    def test_run_http_transport(self, mock_logging):
        from spine.core.transports.mcp import run_spine_mcp

        mcp = MagicMock()
        mcp.name = "test"
        mcp.settings = MagicMock()

        with patch.object(sys, "argv", ["test", "--transport", "http"]):
            run_spine_mcp(mcp, default_port=8100)

        mcp.run.assert_called_once_with(transport="streamable-http")
        assert mcp.settings.port == 8100
        assert mcp.settings.host == "0.0.0.0"

    @patch("spine.core.transports.mcp.logging")
    def test_run_custom_port(self, mock_logging):
        from spine.core.transports.mcp import run_spine_mcp

        mcp = MagicMock()
        mcp.name = "test"
        mcp.settings = MagicMock()

        with patch.object(sys, "argv", ["test", "--transport", "streamable-http", "--port", "9999"]):
            run_spine_mcp(mcp)

        mcp.run.assert_called_once_with(transport="streamable-http")
        assert mcp.settings.port == 9999

    @patch("spine.core.transports.mcp.logging")
    def test_run_with_log_name(self, mock_logging):
        from spine.core.transports.mcp import run_spine_mcp

        mcp = MagicMock()
        mcp.name = "test"

        with patch.object(sys, "argv", ["test"]):
            run_spine_mcp(mcp, log_name="custom-logger")

        mock_logging.getLogger.assert_any_call("custom-logger")

    @patch("spine.core.transports.mcp.logging")
    def test_run_ignores_unknown_args(self, mock_logging):
        from spine.core.transports.mcp import run_spine_mcp

        mcp = MagicMock()
        mcp.name = "test"

        with patch.object(sys, "argv", ["test", "--unknown", "value"]):
            run_spine_mcp(mcp)

        mcp.run.assert_called_once_with(transport="stdio")
