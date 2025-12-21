"""Prometheus-style metrics for observability.

Provides metrics that can be exposed via:
- Prometheus /metrics endpoint
- OpenTelemetry export
- StatsD/DataDog
- Custom exporters

Metric types:
- Counter: Monotonically increasing value
- Gauge: Value that can go up or down
- Histogram: Distribution of values

Example:
    >>> from spine.observability.metrics import counter, gauge, histogram
    >>>
    >>> # Increment a counter
    >>> counter("executions_total", labels={"operation": "sec.filings"}).inc()
    >>>
    >>> # Set a gauge
    >>> gauge("queue_depth").set(42)
    >>>
    >>> # Record to histogram
    >>> histogram("execution_duration_seconds").observe(1.5)
"""

import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


def utcnow() -> datetime:
    """Return timezone-aware UTC datetime."""
    return datetime.now(UTC)


@dataclass(frozen=True)
class Labels:
    """Immutable label set for metrics."""

    _labels: tuple[tuple[str, str], ...]

    @classmethod
    def from_dict(cls, d: dict[str, str] | None) -> "Labels":
        """Create from dictionary."""
        if not d:
            return cls(())
        return cls(tuple(sorted(d.items())))

    def to_dict(self) -> dict[str, str]:
        """Convert to dictionary."""
        return dict(self._labels)

    def __hash__(self) -> int:
        return hash(self._labels)


class Metric(ABC):
    """Base class for metrics."""

    def __init__(self, name: str, description: str = ""):
        self.name = name
        self.description = description
        self._lock = threading.Lock()

    @abstractmethod
    def collect(self) -> list[dict[str, Any]]:
        """Collect metric values for export."""
        ...


class Counter(Metric):
    """A monotonically increasing counter.

    Use for:
    - Request counts
    - Error counts
    - Completed tasks
    """

    def __init__(self, name: str, description: str = "", labels: list[str] | None = None):
        super().__init__(name, description)
        self._label_names = labels or []
        self._values: dict[Labels, float] = {}

    def labels(self, **kwargs: str) -> "CounterChild":
        """Get counter with specific labels."""
        return CounterChild(self, Labels.from_dict(kwargs))

    def inc(self, value: float = 1.0) -> None:
        """Increment counter (no labels)."""
        self.labels().inc(value)

    def _inc(self, labels: Labels, value: float) -> None:
        """Internal increment."""
        with self._lock:
            self._values[labels] = self._values.get(labels, 0.0) + value

    def _get(self, labels: Labels) -> float:
        """Get current value."""
        with self._lock:
            return self._values.get(labels, 0.0)

    def collect(self) -> list[dict[str, Any]]:
        """Collect all counter values."""
        with self._lock:
            return [
                {
                    "name": self.name,
                    "type": "counter",
                    "labels": labels.to_dict(),
                    "value": value,
                }
                for labels, value in self._values.items()
            ]


class CounterChild:
    """Counter with fixed labels."""

    def __init__(self, counter: Counter, labels: Labels):
        self._counter = counter
        self._labels = labels

    def inc(self, value: float = 1.0) -> None:
        """Increment the counter."""
        if value < 0:
            raise ValueError("Counter can only increase")
        self._counter._inc(self._labels, value)

    @property
    def value(self) -> float:
        """Get current value."""
        return self._counter._get(self._labels)


class Gauge(Metric):
    """A value that can go up or down.

    Use for:
    - Queue depth
    - Active connections
    - Temperature
    """

    def __init__(self, name: str, description: str = "", labels: list[str] | None = None):
        super().__init__(name, description)
        self._label_names = labels or []
        self._values: dict[Labels, float] = {}

    def labels(self, **kwargs: str) -> "GaugeChild":
        """Get gauge with specific labels."""
        return GaugeChild(self, Labels.from_dict(kwargs))

    def set(self, value: float) -> None:
        """Set gauge value (no labels)."""
        self.labels().set(value)

    def inc(self, value: float = 1.0) -> None:
        """Increment gauge (no labels)."""
        self.labels().inc(value)

    def dec(self, value: float = 1.0) -> None:
        """Decrement gauge (no labels)."""
        self.labels().dec(value)

    def _set(self, labels: Labels, value: float) -> None:
        """Internal set."""
        with self._lock:
            self._values[labels] = value

    def _get(self, labels: Labels) -> float:
        """Get current value."""
        with self._lock:
            return self._values.get(labels, 0.0)

    def collect(self) -> list[dict[str, Any]]:
        """Collect all gauge values."""
        with self._lock:
            return [
                {
                    "name": self.name,
                    "type": "gauge",
                    "labels": labels.to_dict(),
                    "value": value,
                }
                for labels, value in self._values.items()
            ]


class GaugeChild:
    """Gauge with fixed labels."""

    def __init__(self, gauge: Gauge, labels: Labels):
        self._gauge = gauge
        self._labels = labels

    def set(self, value: float) -> None:
        """Set the gauge value."""
        self._gauge._set(self._labels, value)

    def inc(self, value: float = 1.0) -> None:
        """Increment the gauge."""
        with self._gauge._lock:
            current = self._gauge._values.get(self._labels, 0.0)
            self._gauge._values[self._labels] = current + value

    def dec(self, value: float = 1.0) -> None:
        """Decrement the gauge."""
        self.inc(-value)

    @property
    def value(self) -> float:
        """Get current value."""
        return self._gauge._get(self._labels)

    def set_to_current_time(self) -> None:
        """Set gauge to current Unix timestamp."""
        self.set(time.time())


class Histogram(Metric):
    """A distribution of values.

    Use for:
    - Request latency
    - Response sizes
    - Execution duration
    """

    DEFAULT_BUCKETS = (
        0.005,
        0.01,
        0.025,
        0.05,
        0.075,
        0.1,
        0.25,
        0.5,
        0.75,
        1.0,
        2.5,
        5.0,
        7.5,
        10.0,
        float("inf"),
    )

    def __init__(
        self,
        name: str,
        description: str = "",
        labels: list[str] | None = None,
        buckets: tuple[float, ...] | None = None,
    ):
        super().__init__(name, description)
        self._label_names = labels or []
        self._buckets = buckets or self.DEFAULT_BUCKETS
        self._data: dict[Labels, dict[str, Any]] = {}

    def labels(self, **kwargs: str) -> "HistogramChild":
        """Get histogram with specific labels."""
        return HistogramChild(self, Labels.from_dict(kwargs))

    def observe(self, value: float) -> None:
        """Record an observation (no labels)."""
        self.labels().observe(value)

    def _observe(self, labels: Labels, value: float) -> None:
        """Internal observe."""
        with self._lock:
            if labels not in self._data:
                self._data[labels] = {
                    "buckets": dict.fromkeys(self._buckets, 0),
                    "sum": 0.0,
                    "count": 0,
                }

            data = self._data[labels]
            data["sum"] += value
            data["count"] += 1

            for bucket in self._buckets:
                if value <= bucket:
                    data["buckets"][bucket] += 1

    def _get(self, labels: Labels) -> dict[str, Any]:
        """Get histogram data."""
        with self._lock:
            return self._data.get(
                labels,
                {
                    "buckets": dict.fromkeys(self._buckets, 0),
                    "sum": 0.0,
                    "count": 0,
                },
            )

    def collect(self) -> list[dict[str, Any]]:
        """Collect all histogram values."""
        with self._lock:
            results = []
            for labels, data in self._data.items():
                results.append(
                    {
                        "name": self.name,
                        "type": "histogram",
                        "labels": labels.to_dict(),
                        "buckets": dict(data["buckets"]),
                        "sum": data["sum"],
                        "count": data["count"],
                    }
                )
            return results


class HistogramChild:
    """Histogram with fixed labels."""

    def __init__(self, histogram: Histogram, labels: Labels):
        self._histogram = histogram
        self._labels = labels

    def observe(self, value: float) -> None:
        """Record an observation."""
        self._histogram._observe(self._labels, value)

    def time(self) -> "Timer":
        """Context manager to time a block and record duration."""
        return Timer(self)

    @property
    def data(self) -> dict[str, Any]:
        """Get histogram data."""
        return self._histogram._get(self._labels)


class Timer:
    """Context manager for timing operations."""

    def __init__(self, histogram_child: HistogramChild):
        self._histogram_child = histogram_child
        self._start: float | None = None

    def __enter__(self) -> "Timer":
        self._start = time.perf_counter()
        return self

    def __exit__(self, *args: Any) -> None:
        duration = time.perf_counter() - self._start
        self._histogram_child.observe(duration)


class MetricsRegistry:
    """Registry of all metrics for collection and export."""

    def __init__(self):
        self._metrics: dict[str, Metric] = {}
        self._lock = threading.Lock()

    def register(self, metric: Metric) -> Metric:
        """Register a metric."""
        with self._lock:
            if metric.name in self._metrics:
                return self._metrics[metric.name]
            self._metrics[metric.name] = metric
            return metric

    def counter(
        self,
        name: str,
        description: str = "",
        labels: list[str] | None = None,
    ) -> Counter:
        """Get or create a counter."""
        with self._lock:
            if name not in self._metrics:
                self._metrics[name] = Counter(name, description, labels)
            return self._metrics[name]

    def gauge(
        self,
        name: str,
        description: str = "",
        labels: list[str] | None = None,
    ) -> Gauge:
        """Get or create a gauge."""
        with self._lock:
            if name not in self._metrics:
                self._metrics[name] = Gauge(name, description, labels)
            return self._metrics[name]

    def histogram(
        self,
        name: str,
        description: str = "",
        labels: list[str] | None = None,
        buckets: tuple[float, ...] | None = None,
    ) -> Histogram:
        """Get or create a histogram."""
        with self._lock:
            if name not in self._metrics:
                self._metrics[name] = Histogram(name, description, labels, buckets)
            return self._metrics[name]

    def collect(self) -> list[dict[str, Any]]:
        """Collect all metrics."""
        with self._lock:
            results = []
            for metric in self._metrics.values():
                results.extend(metric.collect())
            return results

    def export_prometheus(self) -> str:
        """Export metrics in Prometheus text format."""
        lines = []

        for data in self.collect():
            name = data["name"]
            metric_type = data["type"]
            labels = data.get("labels", {})

            # Format labels
            if labels:
                label_str = ",".join(f'{k}="{v}"' for k, v in labels.items())
                label_str = "{" + label_str + "}"
            else:
                label_str = ""

            if metric_type in ("counter", "gauge"):
                lines.append(f"{name}{label_str} {data['value']}")

            elif metric_type == "histogram":
                # Bucket lines
                for bucket, count in data["buckets"].items():
                    bucket_labels = f'{label_str[:-1]},le="{bucket}"}}' if label_str else f'{{le="{bucket}"}}'
                    lines.append(f"{name}_bucket{bucket_labels} {count}")

                # Sum and count
                lines.append(f"{name}_sum{label_str} {data['sum']}")
                lines.append(f"{name}_count{label_str} {data['count']}")

        return "\n".join(lines)


# Global registry
_default_registry = MetricsRegistry()


def get_metrics_registry() -> MetricsRegistry:
    """Get the default metrics registry."""
    return _default_registry


def counter(
    name: str,
    description: str = "",
    labels: list[str] | None = None,
) -> Counter:
    """Get or create a counter from the default registry."""
    return _default_registry.counter(name, description, labels)


def gauge(
    name: str,
    description: str = "",
    labels: list[str] | None = None,
) -> Gauge:
    """Get or create a gauge from the default registry."""
    return _default_registry.gauge(name, description, labels)


def histogram(
    name: str,
    description: str = "",
    labels: list[str] | None = None,
    buckets: tuple[float, ...] | None = None,
) -> Histogram:
    """Get or create a histogram from the default registry."""
    return _default_registry.histogram(name, description, labels, buckets)


# Pre-defined execution metrics
class ExecutionMetrics:
    """Pre-defined metrics for execution tracking."""

    def __init__(self, registry: MetricsRegistry | None = None):
        reg = registry or _default_registry

        self.submitted = reg.counter(
            "spine_executions_submitted_total",
            "Total executions submitted",
            ["operation"],
        )

        self.completed = reg.counter(
            "spine_executions_completed_total",
            "Total executions completed",
            ["operation", "status"],
        )

        self.duration = reg.histogram(
            "spine_execution_duration_seconds",
            "Execution duration in seconds",
            ["operation"],
            buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0, float("inf")),
        )

        self.dlq_depth = reg.gauge(
            "spine_dlq_depth",
            "Number of items in dead letter queue",
            ["operation"],
        )

        self.active_executions = reg.gauge(
            "spine_active_executions",
            "Number of currently running executions",
            ["operation"],
        )

        self.locks_held = reg.gauge(
            "spine_locks_held",
            "Number of currently held locks",
        )

    def record_submission(self, operation: str) -> None:
        """Record an execution submission."""
        self.submitted.labels(operation=operation).inc()
        self.active_executions.labels(operation=operation).inc()

    def record_completion(self, operation: str, status: str, duration: float) -> None:
        """Record an execution completion."""
        self.completed.labels(operation=operation, status=status).inc()
        self.duration.labels(operation=operation).observe(duration)
        self.active_executions.labels(operation=operation).dec()


# Global execution metrics instance
execution_metrics = ExecutionMetrics()
