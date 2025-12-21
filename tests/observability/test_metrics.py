"""Tests for Prometheus-style metrics."""

import pytest
import time
from unittest.mock import MagicMock, patch

from spine.observability.metrics import (
    Labels,
    Counter,
    CounterChild,
    Gauge,
    GaugeChild,
    Histogram,
    HistogramChild,
    Timer,
    MetricsRegistry,
    get_metrics_registry,
    counter,
    gauge,
    histogram,
    ExecutionMetrics,
)


class TestLabels:
    """Tests for Labels class."""

    def test_create_from_dict(self):
        """Test creating labels from dict."""
        labels = Labels.from_dict({"env": "prod", "region": "us-east"})
        
        d = labels.to_dict()
        assert d["env"] == "prod"
        assert d["region"] == "us-east"

    def test_create_from_empty_dict(self):
        """Test creating labels from empty dict."""
        labels = Labels.from_dict({})
        assert labels.to_dict() == {}

    def test_create_from_none(self):
        """Test creating labels from None."""
        labels = Labels.from_dict(None)
        assert labels.to_dict() == {}

    def test_labels_are_hashable(self):
        """Test labels can be used as dict keys."""
        labels1 = Labels.from_dict({"a": "1", "b": "2"})
        labels2 = Labels.from_dict({"a": "1", "b": "2"})
        
        # Same labels should have same hash
        assert hash(labels1) == hash(labels2)
        
        # Can use as dict key
        d = {labels1: "value"}
        assert d[labels2] == "value"


class TestCounter:
    """Tests for Counter metric."""

    def test_create_counter(self):
        """Test creating a counter."""
        c = Counter("requests_total", "Total requests")
        assert c.name == "requests_total"
        assert c.description == "Total requests"

    def test_increment_counter(self):
        """Test incrementing counter."""
        c = Counter("requests_total")
        
        c.inc()
        c.inc()
        c.inc(5)
        
        assert c.labels().value == 7

    def test_increment_with_labels(self):
        """Test incrementing counter with labels."""
        c = Counter("requests_total", labels=["method", "status"])
        
        c.labels(method="GET", status="200").inc()
        c.labels(method="GET", status="200").inc()
        c.labels(method="POST", status="201").inc()
        
        assert c.labels(method="GET", status="200").value == 2
        assert c.labels(method="POST", status="201").value == 1

    def test_counter_cannot_decrease(self):
        """Test counter cannot be decreased."""
        c = Counter("requests_total")
        
        with pytest.raises(ValueError):
            c.inc(-1)

    def test_counter_collect(self):
        """Test counter collection."""
        c = Counter("requests_total")
        
        c.labels(method="GET").inc(10)
        c.labels(method="POST").inc(5)
        
        data = c.collect()
        
        assert len(data) == 2
        assert all(d["type"] == "counter" for d in data)


class TestGauge:
    """Tests for Gauge metric."""

    def test_create_gauge(self):
        """Test creating a gauge."""
        g = Gauge("temperature", "Current temperature")
        assert g.name == "temperature"

    def test_set_gauge(self):
        """Test setting gauge value."""
        g = Gauge("temperature")
        
        g.set(25.5)
        
        assert g.labels().value == 25.5

    def test_gauge_inc_dec(self):
        """Test incrementing/decrementing gauge."""
        g = Gauge("queue_depth")
        
        g.set(10)
        g.inc(5)
        g.dec(3)
        
        assert g.labels().value == 12

    def test_gauge_with_labels(self):
        """Test gauge with labels."""
        g = Gauge("queue_depth", labels=["queue_name"])
        
        g.labels(queue_name="high").set(100)
        g.labels(queue_name="low").set(10)
        
        assert g.labels(queue_name="high").value == 100
        assert g.labels(queue_name="low").value == 10

    def test_gauge_set_to_current_time(self):
        """Test setting gauge to current time."""
        g = Gauge("last_update_timestamp")
        
        before = time.time()
        g.labels().set_to_current_time()
        after = time.time()
        
        value = g.labels().value
        assert before <= value <= after


class TestHistogram:
    """Tests for Histogram metric."""

    def test_create_histogram(self):
        """Test creating a histogram."""
        h = Histogram("request_duration_seconds", "Request duration")
        assert h.name == "request_duration_seconds"

    def test_observe_values(self):
        """Test observing values."""
        h = Histogram("request_duration_seconds")
        
        h.observe(0.1)
        h.observe(0.5)
        h.observe(1.0)
        
        data = h.labels().data
        assert data["count"] == 3
        assert data["sum"] == pytest.approx(1.6)

    def test_histogram_buckets(self):
        """Test histogram buckets."""
        h = Histogram(
            "request_duration_seconds",
            buckets=(0.1, 0.5, 1.0, float("inf")),
        )
        
        h.observe(0.05)  # Goes in 0.1 bucket
        h.observe(0.3)   # Goes in 0.5 bucket
        h.observe(0.8)   # Goes in 1.0 bucket
        h.observe(2.0)   # Goes in inf bucket
        
        data = h.labels().data
        # Buckets are cumulative
        assert data["buckets"][0.1] == 1
        assert data["buckets"][0.5] == 2
        assert data["buckets"][1.0] == 3
        assert data["buckets"][float("inf")] == 4

    def test_histogram_with_labels(self):
        """Test histogram with labels."""
        h = Histogram("request_duration_seconds", labels=["method"])
        
        h.labels(method="GET").observe(0.1)
        h.labels(method="GET").observe(0.2)
        h.labels(method="POST").observe(0.5)
        
        get_data = h.labels(method="GET").data
        post_data = h.labels(method="POST").data
        
        assert get_data["count"] == 2
        assert post_data["count"] == 1

    def test_histogram_timer_context_manager(self):
        """Test histogram timer context manager."""
        h = Histogram("request_duration_seconds")
        
        with h.labels().time():
            time.sleep(0.05)
        
        data = h.labels().data
        assert data["count"] == 1
        assert data["sum"] >= 0.04  # Allow some slack


class TestMetricsRegistry:
    """Tests for MetricsRegistry."""

    def test_register_counter(self):
        """Test registering a counter."""
        registry = MetricsRegistry()
        
        c = registry.counter("requests_total", "Total requests")
        
        assert c.name == "requests_total"

    def test_get_same_counter(self):
        """Test getting same counter returns same instance."""
        registry = MetricsRegistry()
        
        c1 = registry.counter("requests_total")
        c2 = registry.counter("requests_total")
        
        assert c1 is c2

    def test_register_all_types(self):
        """Test registering all metric types."""
        registry = MetricsRegistry()
        
        c = registry.counter("counter_metric")
        g = registry.gauge("gauge_metric")
        h = registry.histogram("histogram_metric")
        
        assert isinstance(c, Counter)
        assert isinstance(g, Gauge)
        assert isinstance(h, Histogram)

    def test_collect_all_metrics(self):
        """Test collecting all metrics."""
        registry = MetricsRegistry()
        
        registry.counter("requests_total").inc(10)
        registry.gauge("temperature").set(25.0)
        registry.histogram("latency").observe(0.1)
        
        data = registry.collect()
        
        assert len(data) >= 3

    def test_export_prometheus_format(self):
        """Test exporting in Prometheus format."""
        registry = MetricsRegistry()
        
        registry.counter("http_requests_total").labels(method="GET").inc(100)
        registry.gauge("temperature").set(25.5)
        
        output = registry.export_prometheus()
        
        # Should have metric lines
        assert "http_requests_total" in output
        assert "temperature" in output
        assert "100" in output
        assert "25.5" in output


class TestGlobalFunctions:
    """Tests for global convenience functions."""

    def test_global_counter(self):
        """Test global counter function."""
        c = counter("global_counter_test")
        c.inc()
        
        # Should be in global registry
        c2 = counter("global_counter_test")
        assert c is c2

    def test_global_gauge(self):
        """Test global gauge function."""
        g = gauge("global_gauge_test")
        g.set(42)
        
        g2 = gauge("global_gauge_test")
        assert g2.labels().value == 42

    def test_global_histogram(self):
        """Test global histogram function."""
        h = histogram("global_histogram_test")
        h.observe(1.0)
        
        h2 = histogram("global_histogram_test")
        assert h2.labels().data["count"] == 1


class TestExecutionMetrics:
    """Tests for ExecutionMetrics pre-defined metrics."""

    def test_record_submission(self):
        """Test recording submission."""
        # Use fresh registry
        registry = MetricsRegistry()
        metrics = ExecutionMetrics(registry)
        
        metrics.record_submission("sec.filings")
        metrics.record_submission("sec.filings")
        metrics.record_submission("market.prices")
        
        assert metrics.submitted.labels(operation="sec.filings").value == 2
        assert metrics.submitted.labels(operation="market.prices").value == 1

    def test_record_completion(self):
        """Test recording completion."""
        registry = MetricsRegistry()
        metrics = ExecutionMetrics(registry)
        
        metrics.record_submission("test.operation")
        metrics.record_completion("test.operation", "completed", 1.5)
        
        assert metrics.completed.labels(operation="test.operation", status="completed").value == 1
        assert metrics.duration.labels(operation="test.operation").data["count"] == 1

    def test_active_executions_tracking(self):
        """Test active executions tracking."""
        registry = MetricsRegistry()
        metrics = ExecutionMetrics(registry)
        
        metrics.record_submission("test.operation")
        metrics.record_submission("test.operation")
        # Active should be 2
        
        metrics.record_completion("test.operation", "completed", 1.0)
        # Active should be 1

    def test_dlq_depth_gauge(self):
        """Test DLQ depth gauge."""
        registry = MetricsRegistry()
        metrics = ExecutionMetrics(registry)
        
        metrics.dlq_depth.labels(operation="test").set(10)
        
        assert metrics.dlq_depth.labels(operation="test").value == 10
