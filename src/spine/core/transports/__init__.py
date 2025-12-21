"""MCP transport scaffold for AI-callable spine services.

Manifesto:
    Every spine service needs to be callable by AI agents via the Model
    Context Protocol.  Without a shared scaffold, each service re-implements
    the same stdio/HTTP framing, error mapping, and lifecycle boilerplate.

Provides ``create_spine_mcp()`` -- a factory that creates a ready-to-run
Model Context Protocol server for any spine service.  Each spine registers
its domain-specific tools; the transport layer handles stdio/HTTP framing,
error mapping, and lifecycle.

Modules
-------
mcp     create_spine_mcp() + run_spine_mcp() factory functions

Tags:
    spine-core, mcp, transport, ai-callable, protocol, factory

Doc-Types:
    package-overview
"""
