"""spine-core MCP Server.

Model Context Protocol (MCP) server exposing spine-core capabilities
as AI-callable tools for workflow orchestration, run management,
scheduling, quality monitoring, and alerting.

Usage::

    # stdio mode (default)
    spine-core-mcp

    # HTTP mode
    spine-core-mcp --transport http --port 8100

Requires::

    pip install spine-core[mcp]

"""

from spine.mcp.server import create_server, mcp, run

__all__ = [
    "create_server",
    "mcp",
    "run",
]
