"""MCP transport scaffold for AI-callable spine services.

Provides ``create_spine_mcp()`` -- a factory that creates a ready-to-run
Model Context Protocol server for any spine service.  Each spine registers
its domain-specific tools; the transport layer handles stdio/HTTP framing,
error mapping, and lifecycle.

Modules
-------
mcp     create_spine_mcp() + run_spine_mcp() factory functions
"""
