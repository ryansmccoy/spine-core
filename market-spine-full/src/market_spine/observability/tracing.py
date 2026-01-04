"""OpenTelemetry tracing configuration."""

from contextlib import contextmanager
from typing import Iterator

from market_spine.core.settings import get_settings

_tracer = None


def configure_tracing() -> None:
    """Configure OpenTelemetry tracing."""
    global _tracer
    settings = get_settings()

    if not settings.tracing_enabled:
        return

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource

        # Create resource
        resource = Resource.create(
            {
                "service.name": "market-spine",
                "service.version": "1.0.0",
            }
        )

        # Create tracer provider
        provider = TracerProvider(resource=resource)

        # Add OTLP exporter
        exporter = OTLPSpanExporter(endpoint=settings.otlp_endpoint)
        provider.add_span_processor(BatchSpanProcessor(exporter))

        # Set global tracer provider
        trace.set_tracer_provider(provider)
        _tracer = trace.get_tracer("market-spine")

    except ImportError:
        pass  # OpenTelemetry not installed


def get_tracer():
    """Get the tracer instance."""
    global _tracer
    if _tracer is None:
        try:
            from opentelemetry import trace

            _tracer = trace.get_tracer("market-spine")
        except ImportError:
            return None
    return _tracer


@contextmanager
def trace_span(name: str, attributes: dict | None = None) -> Iterator[None]:
    """Create a trace span context."""
    tracer = get_tracer()
    if tracer is None:
        yield
        return

    with tracer.start_as_current_span(name, attributes=attributes):
        yield


def instrument_fastapi(app):
    """Instrument FastAPI with OpenTelemetry."""
    settings = get_settings()
    if not settings.tracing_enabled:
        return

    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(app)
    except ImportError:
        pass


def instrument_celery():
    """Instrument Celery with OpenTelemetry."""
    settings = get_settings()
    if not settings.tracing_enabled:
        return

    try:
        from opentelemetry.instrumentation.celery import CeleryInstrumentor

        CeleryInstrumentor().instrument()
    except ImportError:
        pass


def instrument_psycopg():
    """Instrument psycopg with OpenTelemetry."""
    settings = get_settings()
    if not settings.tracing_enabled:
        return

    try:
        from opentelemetry.instrumentation.psycopg import PsycopgInstrumentor

        PsycopgInstrumentor().instrument()
    except ImportError:
        pass
