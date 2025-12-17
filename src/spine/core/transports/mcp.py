"""Shared MCP server scaffold for any Spine service.

Eliminates the repeated boilerplate across genai-spine, search-spine,
and knowledge-spine MCP servers.  Each spine only needs to:

1. Define a lifespan that yields its ``AppContext``
2. Register tools/resources/prompts on the returned ``FastMCP`` instance
3. Call ``run()`` from its console script entry point

Usage::

    from spine.core.transports.mcp import create_spine_mcp, run_spine_mcp

    mcp = create_spine_mcp(
        name="knowledge-spine",
        instructions="Auto-evolving knowledge graph ...",
        lifespan=app_lifespan,
    )

    # register tools
    @mcp.tool(title="Find Nodes")
    async def find_nodes(...): ...

    # entry point for console script
    def run():
        run_spine_mcp(mcp, default_port=8106)

Requires the ``mcp`` optional extra::

    pip install spine-core[mcp]
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

try:
    from mcp.server.fastmcp import Context, FastMCP  # noqa: F401
    from mcp.server.session import ServerSession  # noqa: F401
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "spine.core.transports.mcp requires the mcp SDK. Install it with: pip install spine-core[mcp]"
    ) from exc


logger = logging.getLogger("spine.core.mcp")


def create_spine_mcp(
    name: str,
    instructions: str,
    lifespan: Callable[..., Any],
) -> FastMCP:
    """Create a FastMCP server instance with standard Spine conventions.

    Parameters
    ----------
    name : str
        MCP server name (e.g. "knowledge-spine").
    instructions : str
        Natural language description of the server's capabilities.
    lifespan : async context manager
        Lifespan factory that yields an AppContext dataclass.

    Returns
    -------
    FastMCP
        Configured server instance — register tools/resources/prompts on it.
    """
    return FastMCP(
        name,
        instructions=instructions,
        lifespan=lifespan,
    )


def run_spine_mcp(
    mcp: FastMCP,
    *,
    default_port: int = 8000,
    log_name: str | None = None,
) -> None:
    """Standard entry point for a Spine MCP console script.

    Parses ``--transport`` and ``--port`` from ``sys.argv`` and starts
    the server in either stdio or streamable-http mode.

    Parameters
    ----------
    mcp : FastMCP
        The configured server instance.
    default_port : int
        Port to use for HTTP transport if not specified via ``--port``.
    log_name : str | None
        Logger name for startup messages.  Defaults to the MCP server name.
    """
    import sys

    name = log_name or mcp.name
    _logger = logging.getLogger(name)

    transport = "stdio"
    port = default_port
    args = sys.argv[1:]

    i = 0
    while i < len(args):
        if args[i] in ("--transport", "-t") and i + 1 < len(args):
            transport = args[i + 1]
            i += 2
        elif args[i] in ("--port", "-p") and i + 1 < len(args):
            port = int(args[i + 1])
            i += 2
        else:
            i += 1

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    if transport in ("http", "streamable-http"):
        mcp.settings.host = "0.0.0.0"
        mcp.settings.port = port
        _logger.info("Starting %s MCP (streamable-http) on port %d", name, port)
        mcp.run(transport="streamable-http")
    else:
        _logger.info("Starting %s MCP (stdio)", name)
        mcp.run(transport="stdio")
