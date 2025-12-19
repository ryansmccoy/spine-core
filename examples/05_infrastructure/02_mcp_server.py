"""MCP Server — AI-native Orchestration Interface.

Demonstrates the Model Context Protocol (MCP) server that exposes
spine-core workflow orchestration and monitoring capabilities as
AI-callable tools.

The MCP server provides 13+ tools for:
- Run management (list, get, submit, cancel)
- Workflow orchestration (list, get, run)
- Schedule management (list, create)
- Quality monitoring (results, anomalies, alerts)
- Health checks

Usage:
    # stdio mode (for Claude Desktop, Cline, etc.)
    spine-core-mcp

    # HTTP mode (for custom AI agents)
    spine-core-mcp --transport http --port 8100

Requires:
    pip install spine-core[mcp]
"""

from __future__ import annotations


def demo_server_creation():
    """Create and inspect the MCP server."""
    import asyncio

    from spine.mcp.server import create_server

    server = create_server()

    print("=== MCP Server Info ===")
    print(f"Name: {server.name}")
    print(f"\nInstructions:\n{server.instructions}")

    # List available tools
    tools = asyncio.run(server.list_tools())
    print(f"\n=== Available Tools ({len(tools)}) ===")
    
    categories = {
        "Run Management": ["list_runs", "get_run", "submit_run", "cancel_run"],
        "Workflows": ["list_workflows", "get_workflow", "run_workflow"],
        "Schedules": ["list_schedules", "create_schedule"],
        "Quality": ["list_quality_results"],
        "Monitoring": ["list_anomalies", "list_alerts"],
        "System": ["health_check"],
    }

    for category, tool_names in categories.items():
        print(f"\n{category}:")
        for name in tool_names:
            tool = next((t for t in tools if t.name == name), None)
            if tool:
                print(f"  ✓ {name}")
                # Show first line of description
                desc = tool.description.split("\n")[0] if tool.description else ""
                print(f"    {desc}")
            else:
                print(f"  ✗ {name} (not found)")


def demo_tool_schemas():
    """Show schemas for key tools."""
    import asyncio

    from spine.mcp.server import mcp

    tools = asyncio.run(mcp.list_tools())

    print("\n=== Tool Schemas (Sample) ===")

    # Show schema for list_runs
    list_runs_tool = next(t for t in tools if t.name == "list_runs")
    print("\nlist_runs:")
    print(f"  Description: {list_runs_tool.description.split('.')[0]}")
    if list_runs_tool.inputSchema:
        props = list_runs_tool.inputSchema.get("properties", {})
        print("  Parameters:")
        for param, schema in props.items():
            param_type = schema.get("type", "any")
            print(f"    - {param} ({param_type}): {schema.get('description', '')}")

    # Show schema for run_workflow
    run_wf_tool = next(t for t in tools if t.name == "run_workflow")
    print("\nrun_workflow:")
    print(f"  Description: {run_wf_tool.description.split('.')[0]}")
    if run_wf_tool.inputSchema:
        props = run_wf_tool.inputSchema.get("properties", {})
        print("  Parameters:")
        for param, schema in props.items():
            param_type = schema.get("type", "any")
            print(f"    - {param} ({param_type}): {schema.get('description', '')}")


def demo_integration_examples():
    """Show how to integrate with AI agents."""
    print("\n=== Integration Examples ===")

    print("""
1. Claude Desktop (stdio):
   Add to claude_desktop_config.json:
   {
     "mcpServers": {
       "spine-core": {
         "command": "spine-core-mcp"
       }
     }
   }

2. Custom AI Agent (HTTP):
   import httpx
   
   async def call_spine_tool(tool_name: str, params: dict):
       async with httpx.AsyncClient() as client:
           resp = await client.post(
               "http://localhost:8100/mcp/call",
               json={"tool": tool_name, "params": params}
           )
           return resp.json()
   
   # List active runs
   runs = await call_spine_tool("list_runs", {"status": "RUNNING"})
   
   # Execute workflow
   result = await call_spine_tool(
       "run_workflow",
       {"name": "etl_pipeline", "params": {"tier": "TIER_1"}}
   )

3. Cline / Continue / Other MCP Clients:
   Configure the MCP server URI in your tool's settings.
   Tools will auto-discover and become available in the UI.
""")


def demo_security_notes():
    """Important security considerations."""
    print("\n=== Security Notes ===")
    print("""
⚠️  Production Deployment:

1. Authentication:
   - MCP servers do NOT provide auth by default
   - Use a reverse proxy (nginx, Caddy) with API keys
   - Or wrap in your own auth middleware

2. Network Security:
   - HTTP mode binds to 0.0.0.0 — restrict with firewall
   - stdio mode is safe for local development only

3. Permissions:
   - MCP tools can execute workflows and modify schedules
   - Audit tool usage via spine-core's execution logs
   - Consider role-based tool filtering for production

4. Rate Limiting:
   - Add rate limiting at the proxy level
   - Monitor /health endpoint for abuse patterns
""")


def demo_monitoring():
    """Show monitoring capabilities."""
    print("\n=== Monitoring MCP Server ===")
    print("""
The MCP server exposes spine-core's monitoring capabilities:

1. Health Check:
   tool: health_check
   →  Returns: database status, table count, latency

2. Run Status:
   tool: list_runs
   filter: {"status": "FAILED"}
   →  Recent failures

3. Quality Metrics:
   tool: list_quality_results
   filter: {"workflow": "etl_pipeline"}
   →  Test pass/fail rates

4. Anomaly Detection:
   tool: list_anomalies
   filter: {"severity": "CRITICAL"}
   →  Data quality issues

5. Alerts:
   tool: list_alerts
   filter: {"severity": "ERROR"}
   →  System notifications
""")


if __name__ == "__main__":
    try:
        demo_server_creation()
        demo_tool_schemas()
        demo_integration_examples()
        demo_monitoring()
        demo_security_notes()

        print("\n✓ MCP server ready!")
        print("  Run: spine-core-mcp")
        print("  Or: spine-core-mcp --transport http --port 8100")

    except ImportError as e:
        print(f"❌ MCP SDK not installed: {e}")
        print("   Install with: pip install spine-core[mcp]")
