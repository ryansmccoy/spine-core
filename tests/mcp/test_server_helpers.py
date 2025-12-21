"""Tests for MCP server helper functions.

Tests the internal utility functions rather than the full MCP transport.
"""

from __future__ import annotations

from spine.mcp.server import _get_version, create_server


class TestMcpServerHelpers:
    """MCP server utility tests."""

    def test_get_version_returns_string(self):
        version = _get_version()
        assert isinstance(version, str)
        assert version != ""

    def test_create_server_returns_mcp_instance(self):
        server = create_server()
        assert server is not None
        # Server should have the tools registered
        assert hasattr(server, "tool")


class TestMcpAppContext:
    """AppContext dataclass tests."""

    def test_default_app_context(self):
        from spine.mcp.server import AppContext

        ctx = AppContext()
        assert ctx.conn is None
        assert ctx.initialized is False

    def test_app_context_with_values(self):
        from spine.mcp.server import AppContext

        ctx = AppContext(conn="mock", initialized=True)
        assert ctx.conn == "mock"
        assert ctx.initialized is True
