"""Shared MCP application state — server instance, context, helpers.

Tags: mcp, server, internal
Doc-Types: TECHNICAL_DESIGN
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from spine.core.transports.mcp import create_spine_mcp

logger = logging.getLogger("spine.mcp")


@dataclass
class AppContext:
    """Application context for MCP server."""

    conn: Any = None  # Database connection
    initialized: bool = False


@asynccontextmanager
async def lifespan():
    """MCP server lifespan manager."""
    ctx = AppContext()

    try:
        from spine.core.database import get_connection

        ctx.conn = get_connection()
        ctx.initialized = True
        logger.info("spine-core MCP server initialized")
    except Exception as e:
        logger.warning("Database connection unavailable: %s", e)
        ctx.conn = None
        ctx.initialized = False

    yield ctx

    if ctx.conn:
        try:
            ctx.conn.close()
        except Exception:
            pass


# Create MCP server instance
mcp = create_spine_mcp(
    name="spine-core",
    instructions="""
spine-core orchestration and monitoring server.

Capabilities:
- Execute and monitor workflow runs
- Manage schedules
- Query quality metrics
- List alerts and anomalies
- Health checks

Use these tools to orchestrate data operations, track execution status,
and monitor data quality across your spine-based workflows.
""",
    lifespan=lifespan,
)


def _get_context() -> AppContext:
    """Get current MCP context."""
    try:
        from spine.core.database import get_connection

        conn = get_connection()
        return AppContext(conn=conn, initialized=True)
    except Exception:
        return AppContext(conn=None, initialized=False)


def _get_version() -> str:
    """Get spine-core version."""
    try:
        from spine import __version__

        return __version__
    except Exception:
        return "unknown"
