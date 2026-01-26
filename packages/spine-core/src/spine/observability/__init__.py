"""Observability package for spine-core.

Provides standardized logging, metrics, and tracing for:
- Elastic/ELK Stack ingestion
- OpenTelemetry integration
- DataDog/New Relic/Grafana compatibility
- Prometheus metrics exposure

Key components:
- logging: Structured JSON logging
- metrics: Prometheus-style metrics
- tracing: Distributed tracing support
"""

from .logging import (
    get_logger,
    configure_logging,
    LogLevel,
    StructuredLogger,
    JsonFormatter,
    add_context,
    clear_context,
    get_context,
)

from .metrics import (
    MetricsRegistry,
    Counter,
    Gauge,
    Histogram,
    get_metrics_registry,
    counter,
    gauge,
    histogram,
    execution_metrics,
)

__all__ = [
    # Logging
    "get_logger",
    "configure_logging",
    "LogLevel",
    "StructuredLogger",
    "JsonFormatter",
    "add_context",
    "clear_context",
    "get_context",
    
    # Metrics
    "MetricsRegistry",
    "Counter",
    "Gauge",
    "Histogram",
    "get_metrics_registry",
    "counter",
    "gauge",
    "histogram",
    "execution_metrics",
]
