"""spine-core MCP Server Implementation.

Exposes spine-core workflow orchestration, run management, scheduling,
quality monitoring, and alerting capabilities as MCP tools.

This module is a backward-compatible re-export hub.  The actual
implementation lives in `spine.mcp._app` (shared state) and
`spine.mcp.tools.*` (tool functions).

Tags: mcp, server, ai-tools, orchestration, protocol
Doc-Types: API_REFERENCE, TECHNICAL_DESIGN
"""

from __future__ import annotations

# Re-export shared state for backward compat
from spine.mcp._app import (  # noqa: F401
    AppContext,
    _get_context,
    _get_version,
    lifespan,
    mcp,
)

# Import tools to trigger @mcp.tool() registration
from spine.mcp.tools.runs import (  # noqa: F401
    cancel_run,
    get_run,
    get_run_events,
    get_run_logs,
    get_run_steps,
    list_runs,
    retry_run,
    submit_run,
)
from spine.mcp.tools.workflows import (  # noqa: F401
    get_workflow,
    list_workflows,
    run_workflow,
)
from spine.mcp.tools.schedules import (  # noqa: F401
    create_schedule,
    delete_schedule,
    get_schedule,
    list_schedules,
    update_schedule,
)
from spine.mcp.tools.monitoring import (  # noqa: F401
    acknowledge_alert,
    create_alert_channel,
    list_alert_channels,
    list_alerts,
    list_anomalies,
    list_quality_results,
)
from spine.mcp.tools.health import get_capabilities, health_check  # noqa: F401
from spine.mcp.tools.sources import (  # noqa: F401
    get_source,
    list_sources,
    register_source,
)
from spine.mcp.tools.dlq import (  # noqa: F401
    list_dead_letters,
    replay_dead_letter,
)
from spine.mcp.tools.stats import get_run_stats  # noqa: F401

from spine.core.transports.mcp import run_spine_mcp


def create_server():
    """Create and return the MCP server instance."""
    return mcp


def run():
    """Run the MCP server (entry point for console script)."""
    run_spine_mcp(mcp, default_port=8100, log_name="spine-core-mcp")


if __name__ == "__main__":
    run()
