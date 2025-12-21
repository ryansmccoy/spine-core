"""MCP tools package — re-exports all tool registrations."""

# Importing each module triggers @mcp.tool() registration
from spine.mcp.tools import (  # noqa: F401
    dlq,
    health,
    monitoring,
    runs,
    schedules,
    sources,
    stats,
    workflows,
)
