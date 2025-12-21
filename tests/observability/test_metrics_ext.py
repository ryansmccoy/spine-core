"""Tests for observability metrics — Counter, Gauge, Histogram, Registry.

Pure in-memory metric classes with zero external dependencies.
"""

from __future__ import annotations

import time
from threading import Thread
from unittest.mock import patch

import pytest

from spine.observability.metrics import (
    Counter,
    ExecutionMetrics,
    Gauge,
    Histogram,
    Labels,
    MetricsRegistry,
    Timer,
    counter,
    gauge,
    get_metrics_registry,
    histogram,
)


# ── Labels ───────────────────────────────────────────────────


class TestLabels:
    def test_from_dict(self):
        lbl = Labels.from_dict({"env": "prod", "region": "us"})
        d = lbl.to_dict()
        assert d["env"] == "prod"
        assert d["region"] == "us"

    def test_to_dict_roundtrip(self):
        original = {"env": "prod", "region": "us"}
        lbl = Labels.from_dict(original)
        assert lbl.to_dict() == original

    def test_hashable(self):
        a = Labels.from_dict({"env": "prod"})
        b = Labels.from_dict({"env": "prod"})
        assert hash(a) == hash(b)
        assert {a, b} == {a}

    def test_empty_labels(self):
        lbl = Labels.from_dict({})
        assert lbl.to_dict() == {}


# ── Counter ──────────────────────────────────────────────────


class TestCounter:
    def test_inc_default(self):
        c = Counter("test_counter", "A counter")
        c.inc()
        collected = c.collect()
        assert any(s.get("value", 0) > 0 for s in collected)

    def test_inc_with_amount(self):
        c = Counter("test_inc_amount", "Counter with amount")
        c.inc(5)
        data = c.collect()
        assert any(s.get("value") == 5 for s in data)

    def test_inc_negative_raises(self):
        c = Counter("test_neg", "Negative test")
        child = c.labels(env="test")
        with pytest.raises(ValueError):
            child.inc(-1)

    def test_labels_returns_child(self):
        c = Counter("test_labeled", "Labeled")
        child = c.labels(env="prod")
        child.inc(3)
        assert child.value == 3

    def test_collect_multiple_labels(self):
        c = Counter("multi_label", "Multi label")
        c.labels(env="prod").inc(10)
        c.labels(env="staging").inc(5)
        data = c.collect()
        assert len(data) >= 2


# ── Gauge ────────────────────────────────────────────────────


class TestGauge:
    def test_set(self):
        g = Gauge("test_gauge", "A gauge")
        g.set(42)
        data = g.collect()
        assert any(s.get("value") == 42 for s in data)

    def test_inc_dec(self):
        g = Gauge("test_inc_dec", "Inc/Dec")
        child = g.labels(env="test")
        child.set(10)
        child.inc(5)
        child.dec(3)
        assert child.value == 12

    def test_set_to_current_time(self):
        g = Gauge("test_time", "Time gauge")
        child = g.labels(env="test")
        child.set_to_current_time()
        assert child.value > 1_000_000_000  # Unix timestamp

    def test_collect_returns_metrics(self):
        g = Gauge("test_collect_gauge", "Collect")
        g.set(99)
        data = g.collect()
        assert isinstance(data, list)


# ── Histogram ────────────────────────────────────────────────


class TestHistogram:
    def test_observe(self):
        h = Histogram("test_hist", "A histogram")
        h.observe(0.5)
        h.observe(1.5)
        data = h.collect()
        assert len(data) > 0

    def test_observe_with_labels(self):
        h = Histogram("test_hist_labels", "Labeled histogram")
        child = h.labels(env="test")
        child.observe(0.1)
        child.observe(0.2)
        assert child.data is not None

    def test_custom_buckets(self):
        h = Histogram("custom_bucket", "Custom", buckets=[1, 5, 10])
        h.observe(3)
        data = h.collect()
        assert len(data) > 0


# ── Timer ────────────────────────────────────────────────────


class TestTimer:
    def test_context_manager(self):
        h = Histogram("timer_hist", "Timer test")
        child = h.labels(env="test")
        with child.time():
            time.sleep(0.01)
        assert child.data is not None


# ── MetricsRegistry ──────────────────────────────────────────


class TestMetricsRegistry:
    def test_register_counter(self):
        reg = MetricsRegistry()
        c = reg.counter("reg_counter", "A counter")
        assert isinstance(c, Counter)

    def test_register_gauge(self):
        reg = MetricsRegistry()
        g = reg.gauge("reg_gauge", "A gauge")
        assert isinstance(g, Gauge)

    def test_register_histogram(self):
        reg = MetricsRegistry()
        h = reg.histogram("reg_hist", "A histogram")
        assert isinstance(h, Histogram)

    def test_duplicate_register_returns_existing(self):
        reg = MetricsRegistry()
        c1 = reg.counter("dup_counter", "First")
        c2 = reg.counter("dup_counter", "Second")
        assert c1 is c2

    def test_collect_all(self):
        reg = MetricsRegistry()
        c = reg.counter("collect_counter", "Counter")
        c.inc(5)
        g = reg.gauge("collect_gauge", "Gauge")
        g.set(10)
        data = reg.collect()
        assert len(data) >= 2

    def test_export_prometheus(self):
        reg = MetricsRegistry()
        c = reg.counter("prom_counter", "Prometheus test")
        c.inc(7)
        output = reg.export_prometheus()
        assert isinstance(output, str)
        assert "prom_counter" in output


# ── Module-level shortcuts ───────────────────────────────────


class TestModuleShortcuts:
    def test_get_metrics_registry(self):
        reg = get_metrics_registry()
        assert isinstance(reg, MetricsRegistry)

    def test_counter_shortcut(self):
        c = counter("shortcut_counter", "Shortcut")
        assert isinstance(c, Counter)

    def test_gauge_shortcut(self):
        g = gauge("shortcut_gauge", "Shortcut")
        assert isinstance(g, Gauge)

    def test_histogram_shortcut(self):
        h = histogram("shortcut_hist", "Shortcut")
        assert isinstance(h, Histogram)


# ── ExecutionMetrics ─────────────────────────────────────────


class TestExecutionMetrics:
    def test_record_submission(self):
        em = ExecutionMetrics()
        em.record_submission("test-wf")  # Should not raise

    def test_record_completion_success(self):
        em = ExecutionMetrics()
        em.record_completion("test-wf", "COMPLETED", 1500.0)

    def test_record_completion_failure(self):
        em = ExecutionMetrics()
        em.record_completion("test-op", "FAILED", 500.0)
