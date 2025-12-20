"""Tests for MCP server tools."""

import pytest

pytest.importorskip("mcp")


def test_server_initialization():
    """Test MCP server can be initialized."""
    from spine.mcp.server import create_server

    server = create_server()
    assert server is not None
    assert server.name == "spine-core"


def test_health_check_tool():
    """Test health check tool is registered."""
    import asyncio

    from spine.mcp.server import mcp

    # Check tool is registered
    tools = asyncio.run(mcp.list_tools())
    tool_names = [t.name for t in tools]

    assert "health_check" in tool_names


def test_run_management_tools():
    """Test run management tools are registered."""
    import asyncio

    from spine.mcp.server import mcp

    tools = asyncio.run(mcp.list_tools())
    tool_names = [t.name for t in tools]

    assert "list_runs" in tool_names
    assert "get_run" in tool_names
    assert "submit_run" in tool_names
    assert "cancel_run" in tool_names


def test_workflow_management_tools():
    """Test workflow tools are registered."""
    import asyncio

    from spine.mcp.server import mcp

    tools = asyncio.run(mcp.list_tools())
    tool_names = [t.name for t in tools]

    assert "list_workflows" in tool_names
    assert "get_workflow" in tool_names
    assert "run_workflow" in tool_names


def test_schedule_management_tools():
    """Test schedule tools are registered."""
    import asyncio

    from spine.mcp.server import mcp

    tools = asyncio.run(mcp.list_tools())
    tool_names = [t.name for t in tools]

    assert "list_schedules" in tool_names
    assert "create_schedule" in tool_names


def test_monitoring_tools():
    """Test monitoring tools are registered."""
    import asyncio

    from spine.mcp.server import mcp

    tools = asyncio.run(mcp.list_tools())
    tool_names = [t.name for t in tools]

    assert "list_quality_results" in tool_names
    assert "list_anomalies" in tool_names
    assert "list_alerts" in tool_names


def test_tool_count():
    """Test expected number of tools."""
    import asyncio

    from spine.mcp.server import mcp

    tools = asyncio.run(mcp.list_tools())
    
    # Should have 15 tools:
    # - 4 run management (list, get, submit, cancel)
    # - 3 workflow (list, get, run)
    # - 2 schedule (list, create)
    # - 3 monitoring (quality, anomalies, alerts)
    # - 1 health
    # Total: 13 minimum
    assert len(tools) >= 13
