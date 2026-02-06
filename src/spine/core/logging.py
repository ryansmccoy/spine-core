"""
Spine-Core Logging - Standardized structured logging for all spines.

This module provides a standardized logging configuration using structlog
that can be imported by any spine (capture-spine, market-spine, feedspine, etc.)

Manifesto:
    Observability is critical for financial data pipelines. This module
    provides structured logging that:
    
    - **Standardizes:** Same log format across all spines
    - **Structures:** JSON output for log aggregation (ELK, etc.)
    - **Correlates:** execution_id, batch_id propagation
    - **Flexes:** Console output for development, JSON for production
    
    Every spine should use spine.core.logging for consistency.

Architecture:
    ::
    
        ┌─────────────────────────────────────────────────────────────┐
        │                    Logging Architecture                      │
        └─────────────────────────────────────────────────────────────┘
        
        Configuration Flow:
        ┌────────────────────────────────────────────────────────────┐
        │ configure_logging(level="INFO", json_format=True,          │
        │                   service="capture-spine")                 │
        │                                                             │
        │     ↓                                                       │
        │ structlog configured with processor chain:                  │
        │   1. add_timestamp                                          │
        │   2. add_log_level                                          │
        │   3. add_service_metadata                                   │
        │   4. elasticsearch_compatible                               │
        │   5. JSONRenderer (or ConsoleRenderer for dev)              │
        └────────────────────────────────────────────────────────────┘
        
        Usage Flow:
        ┌────────────────────────────────────────────────────────────┐
        │ logger = get_logger(__name__)                              │
        │ logger.info("event_happened", key="value", count=42)       │
        │                                                             │
        │ Output (JSON format):                                       │
        │ {                                                           │
        │   "@timestamp": "2025-12-26T10:00:00Z",                    │
        │   "log.level": "info",                                     │
        │   "service.name": "capture-spine",                         │
        │   "event": "event_happened",                               │
        │   "key": "value",                                          │
        │   "count": 42                                              │
        │ }                                                           │
        └────────────────────────────────────────────────────────────┘

Features:
    - Structured JSON output for Elasticsearch ingestion
    - Context propagation (workflow, run_id, request_id)
    - Service-level metadata
    - Elasticsearch-compatible field names (@timestamp, log.level)
    - Colored console output for development
    - Fallback to stdlib logging if structlog unavailable

Examples:
    Production (JSON for log aggregation):
    
    >>> from spine.core.logging import configure_logging, get_logger
    >>> configure_logging(level="INFO", json_format=True, service="capture-spine")
    >>> logger = get_logger(__name__)
    >>> logger.info("event_happened", key="value", count=42)
    
    Development (auto-detect: colored console if tty):
    
    >>> configure_logging(level="DEBUG", service="capture-spine")
    >>> logger = get_logger(__name__)
    >>> logger.debug("debugging", data={"foo": "bar"})

Performance:
    - configure_logging(): One-time setup, O(1)
    - get_logger(): Returns cached logger, O(1)
    - Log calls: Minimal overhead with structlog

Guardrails:
    - Graceful fallback to stdlib logging if structlog unavailable
    - Auto-detects JSON vs console based on TTY
    - Service name stored globally (set once at startup)
    - ECS-compatible field names for Elasticsearch

Context:
    - Domain: Observability, logging, monitoring
    - Used By: All Spine services and pipelines
    - Integrates With: Elasticsearch, Kibana, log aggregation
    - Dependencies: structlog (optional, fallback to stdlib)

Tags:
    logging, structlog, observability, elasticsearch, ecs,
    json-logging, spine-core, monitoring

Doc-Types:
    - API Reference
    - Observability Guide
    - Configuration Documentation
"""

from __future__ import annotations

import logging
import sys
from typing import Any

try:
    import structlog
    from structlog.types import EventDict, Processor, WrappedLogger
    STRUCTLOG_AVAILABLE = True
except ImportError:
    STRUCTLOG_AVAILABLE = False
    structlog = None  # type: ignore


# Store service name for metadata
_SERVICE_NAME = "spine"


def _add_service_metadata(
    logger: "WrappedLogger", method_name: str, event_dict: "EventDict"
) -> "EventDict":
    """Add service-level metadata to all logs."""
    event_dict.setdefault("service.name", _SERVICE_NAME)
    return event_dict


def _elasticsearch_compatible(
    logger: "WrappedLogger", method_name: str, event_dict: "EventDict"
) -> "EventDict":
    """Make field names Elasticsearch/ECS compatible."""
    # Ensure @timestamp for Elasticsearch
    if "timestamp" in event_dict:
        event_dict["@timestamp"] = event_dict.pop("timestamp")
    
    # Use ECS log.level naming
    if "level" in event_dict:
        event_dict["log.level"] = event_dict.pop("level")
    
    return event_dict


def configure_logging(
    level: str = "INFO",
    json_format: bool | None = None,
    service: str = "spine",
    add_timestamp: bool = True,
) -> None:
    """Configure structured logging for the application.
    
    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR)
        json_format: True for JSON, False for console, None for auto (JSON if not tty)
        service: Service name to include in logs
        add_timestamp: Include ISO timestamp in logs
    
    Example:
        # Production (JSON for log aggregation)
        configure_logging(level="INFO", json_format=True, service="capture-spine")
        
        # Development (auto-detect: colored console if tty)
        configure_logging(level="DEBUG", service="capture-spine")
    """
    global _SERVICE_NAME
    _SERVICE_NAME = service
    
    if not STRUCTLOG_AVAILABLE:
        # Fallback to standard logging
        logging.basicConfig(
            format=f"%(asctime)s - {service} - %(levelname)s - %(name)s - %(message)s",
            stream=sys.stdout,
            level=getattr(logging, level.upper()),
        )
        return
    
    # Auto-detect format if not specified
    if json_format is None:
        json_format = not sys.stdout.isatty()
    
    # Build processor chain
    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.StackInfoRenderer(),
        structlog.dev.set_exc_info,
        _add_service_metadata,
    ]
    
    if add_timestamp:
        shared_processors.insert(0, structlog.processors.TimeStamper(fmt="iso"))
    
    if json_format:
        shared_processors.append(_elasticsearch_compatible)
        renderer: Processor = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True)
    
    processors = shared_processors + [renderer]
    
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper())
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
    
    # Configure standard library logging too
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, level.upper()),
    )


def get_logger(name: str | None = None) -> Any:
    """Get a structured logger.
    
    Args:
        name: Logger name (usually __name__)
        
    Returns:
        structlog BoundLogger if available, else standard Logger
    """
    if STRUCTLOG_AVAILABLE:
        return structlog.get_logger(name)
    return logging.getLogger(name)


def bind_context(**kwargs: Any) -> None:
    """Bind context to include in all subsequent logs.
    
    Example:
        bind_context(workflow="copilot.ingest", run_id="abc123")
        logger.info("step_started")  # Includes workflow and run_id
    """
    if STRUCTLOG_AVAILABLE:
        structlog.contextvars.bind_contextvars(**kwargs)


def unbind_context(*keys: str) -> None:
    """Remove specific keys from logging context."""
    if STRUCTLOG_AVAILABLE:
        structlog.contextvars.unbind_contextvars(*keys)


def clear_context() -> None:
    """Clear all bound context."""
    if STRUCTLOG_AVAILABLE:
        structlog.contextvars.clear_contextvars()


class LogContext:
    """Context manager for scoped logging context.
    
    Example:
        with LogContext(workflow="my_workflow", run_id="abc123"):
            logger.info("step_started")
            logger.info("step_completed")
        # Context cleared here
    """
    
    def __init__(self, **kwargs: Any):
        self._context = kwargs
    
    def __enter__(self) -> "LogContext":
        bind_context(**self._context)
        return self
    
    def __exit__(self, *args) -> None:
        unbind_context(*self._context.keys())
    
    async def __aenter__(self) -> "LogContext":
        bind_context(**self._context)
        return self
    
    async def __aexit__(self, *args) -> None:
        unbind_context(*self._context.keys())


__all__ = [
    "configure_logging",
    "get_logger",
    "bind_context",
    "unbind_context",
    "clear_context",
    "LogContext",
    "STRUCTLOG_AVAILABLE",
]
