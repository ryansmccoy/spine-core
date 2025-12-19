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
    JsonFormatter,
    LogLevel,
    StructuredLogger,
    add_context,
    clear_context,
    configure_logging,
    get_context,
    get_logger,
)
from .metrics import (
    Counter,
    Gauge,
    Histogram,
    MetricsRegistry,
    counter,
    execution_metrics,
    gauge,
    get_metrics_registry,
    histogram,
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
