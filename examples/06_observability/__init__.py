"""Observability — Structured logging, metrics collection, context binding.

Observability primitives give pipelines production-grade visibility:
structured log events, Prometheus-style counters/histograms, and
thread-local context that enriches every log line automatically.

READING ORDER
─────────────
    01 — Structured logging (structlog with processors and formatters)
    02 — Metrics collection (counters, histograms, Prometheus export)
    03 — Context binding (thread-local context for automatic enrichment)
"""
