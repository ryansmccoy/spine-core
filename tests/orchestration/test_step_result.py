"""Tests for StepResult, QualityMetrics, and ErrorCategory.

Covers factories (.ok, .fail, .skip, .from_value), serialization,
quality metrics computation, error categories, and the with_next_step
method used by choice branching.
"""

import pytest

from spine.orchestration.step_result import (
    ErrorCategory,
    QualityMetrics,
    StepResult,
)


# ---------------------------------------------------------------------------
# ErrorCategory enum
# ---------------------------------------------------------------------------


class TestErrorCategory:
    """ErrorCategory enum values and string coercion."""

    def test_all_categories_exist(self):
        assert ErrorCategory.INTERNAL.value == "INTERNAL"
        assert ErrorCategory.DATA_QUALITY.value == "DATA_QUALITY"
        assert ErrorCategory.TRANSIENT.value == "TRANSIENT"
        assert ErrorCategory.TIMEOUT.value == "TIMEOUT"
        assert ErrorCategory.DEPENDENCY.value == "DEPENDENCY"
        assert ErrorCategory.CONFIGURATION.value == "CONFIGURATION"

    def test_category_is_str_enum(self):
        assert isinstance(ErrorCategory.INTERNAL, str)
        assert ErrorCategory.INTERNAL == "INTERNAL"


# ---------------------------------------------------------------------------
# QualityMetrics
# ---------------------------------------------------------------------------


class TestQualityMetrics:
    """QualityMetrics computation and serialization."""

    def test_default_metrics(self):
        m = QualityMetrics()
        assert m.record_count == 0
        assert m.valid_count == 0
        assert m.passed is True

    def test_auto_invalid_count(self):
        m = QualityMetrics(record_count=100, valid_count=95)
        assert m.invalid_count == 5

    def test_valid_rate(self):
        m = QualityMetrics(record_count=200, valid_count=190)
        assert m.valid_rate == pytest.approx(0.95)

    def test_valid_rate_zero_records(self):
        m = QualityMetrics(record_count=0)
        assert m.valid_rate == 0.0

    def test_null_rate(self):
        m = QualityMetrics(record_count=100, null_count=10)
        assert m.null_rate == pytest.approx(0.10)

    def test_null_rate_zero_records(self):
        m = QualityMetrics(record_count=0)
        assert m.null_rate == 0.0

    def test_custom_metrics(self):
        m = QualityMetrics(custom_metrics={"latency_ms": 42})
        assert m.custom_metrics["latency_ms"] == 42

    def test_failure_reasons(self):
        m = QualityMetrics(failure_reasons=["missing CIK", "bad CUSIP"])
        assert len(m.failure_reasons) == 2

    def test_to_dict(self):
        m = QualityMetrics(record_count=100, valid_count=95, passed=True)
        d = m.to_dict()
        assert d["record_count"] == 100
        assert d["valid_count"] == 95
        assert d["invalid_count"] == 5
        assert d["passed"] is True
        assert "valid_rate" in d
        assert "null_rate" in d
        assert "custom_metrics" in d


# ---------------------------------------------------------------------------
# StepResult factories
# ---------------------------------------------------------------------------


class TestStepResultOk:
    """StepResult.ok() factory."""

    def test_ok_minimal(self):
        r = StepResult.ok()
        assert r.success is True
        assert r.output == {}
        assert r.error is None

    def test_ok_with_output(self):
        r = StepResult.ok(output={"count": 42})
        assert r.output["count"] == 42

    def test_ok_with_context_updates(self):
        r = StepResult.ok(context_updates={"stage": "done"})
        assert r.context_updates["stage"] == "done"

    def test_ok_with_quality(self):
        q = QualityMetrics(record_count=10, valid_count=10)
        r = StepResult.ok(quality=q)
        assert r.quality is not None
        assert r.quality.valid_rate == 1.0

    def test_ok_with_events(self):
        r = StepResult.ok(events=[{"event": "fetched", "rows": 500}])
        assert len(r.events) == 1


class TestStepResultFail:
    """StepResult.fail() factory."""

    def test_fail_basic(self):
        r = StepResult.fail("oops")
        assert r.success is False
        assert r.error == "oops"
        assert r.error_category == "INTERNAL"  # default

    def test_fail_with_string_category(self):
        r = StepResult.fail("bad data", category="DATA_QUALITY")
        assert r.error_category == "DATA_QUALITY"

    def test_fail_with_enum_category(self):
        r = StepResult.fail("timeout", category=ErrorCategory.TIMEOUT)
        assert r.error_category == "TIMEOUT"  # normalised to str

    def test_fail_with_quality(self):
        q = QualityMetrics(record_count=100, valid_count=50, passed=False)
        r = StepResult.fail("low quality", quality=q)
        assert r.quality is not None
        assert r.quality.passed is False

    def test_fail_auto_error_message(self):
        """If error is None, a default message is set."""
        r = StepResult(success=False)
        assert r.error is not None
        assert "without error message" in r.error


class TestStepResultSkip:
    """StepResult.skip() factory."""

    def test_skip_basic(self):
        r = StepResult.skip("already processed")
        assert r.success is True
        assert r.output["skipped"] is True
        assert r.output["skip_reason"] == "already processed"

    def test_skip_with_output(self):
        r = StepResult.skip("cached", output={"cached": True})
        assert r.output["cached"] is True


class TestStepResultFromValue:
    """StepResult.from_value() coercion."""

    def test_from_step_result(self):
        original = StepResult.ok(output={"a": 1})
        r = StepResult.from_value(original)
        assert r is original

    def test_from_none(self):
        r = StepResult.from_value(None)
        assert r.success is True
        assert r.output == {}

    def test_from_dict(self):
        r = StepResult.from_value({"count": 42})
        assert r.success is True
        assert r.output["count"] == 42

    def test_from_true(self):
        r = StepResult.from_value(True)
        assert r.success is True

    def test_from_false(self):
        r = StepResult.from_value(False)
        assert r.success is False

    def test_from_string(self):
        r = StepResult.from_value("hello")
        assert r.success is True
        assert r.output["message"] == "hello"

    def test_from_int(self):
        r = StepResult.from_value(42)
        assert r.success is True
        assert r.output["value"] == 42

    def test_from_float(self):
        r = StepResult.from_value(3.14)
        assert r.success is True
        assert r.output["value"] == pytest.approx(3.14)

    def test_from_other(self):
        r = StepResult.from_value([1, 2, 3])
        assert r.success is True
        assert r.output["result"] == [1, 2, 3]


# ---------------------------------------------------------------------------
# with_next_step
# ---------------------------------------------------------------------------


class TestWithNextStep:
    """StepResult.with_next_step() for choice branching."""

    def test_sets_next_step(self):
        r = StepResult.ok(output={"branch": "then"})
        r2 = r.with_next_step("process_step")
        assert r2.next_step == "process_step"
        assert r2.success is True
        assert r2.output == {"branch": "then"}

    def test_original_unchanged(self):
        r = StepResult.ok()
        r2 = r.with_next_step("other")
        assert r.next_step is None
        assert r2.next_step == "other"

    def test_with_none(self):
        r = StepResult.ok()
        r2 = r.with_next_step(None)
        assert r2.next_step is None


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


class TestStepResultSerialization:
    """StepResult.to_dict() serialization."""

    def test_ok_to_dict(self):
        r = StepResult.ok(output={"count": 10})
        d = r.to_dict()
        assert d["success"] is True
        assert d["output"]["count"] == 10
        assert "error" not in d

    def test_fail_to_dict(self):
        r = StepResult.fail("oops", category="TRANSIENT")
        d = r.to_dict()
        assert d["success"] is False
        assert d["error"] == "oops"
        assert d["error_category"] == "TRANSIENT"

    def test_quality_in_to_dict(self):
        q = QualityMetrics(record_count=100, valid_count=95)
        r = StepResult.ok(quality=q)
        d = r.to_dict()
        assert d["quality"]["record_count"] == 100

    def test_next_step_in_to_dict(self):
        r = StepResult.ok().with_next_step("target")
        d = r.to_dict()
        assert d["next_step"] == "target"

    def test_repr(self):
        r = StepResult.ok(output={"a": 1, "b": 2})
        s = repr(r)
        assert "OK" in s
        assert "a" in s

        r2 = StepResult.fail("err", category="TIMEOUT")
        s2 = repr(r2)
        assert "FAIL" in s2
        assert "TIMEOUT" in s2
