"""Tests for step_result.py and step_types.py to boost coverage."""
from __future__ import annotations

import pytest

from spine.orchestration.step_result import ErrorCategory, QualityMetrics, StepResult
from spine.orchestration.step_types import ErrorPolicy, RetryPolicy, Step, StepType


# =============================================================================
# StepResult
# =============================================================================


class TestStepResultFactories:
    """Test StepResult factory methods."""

    def test_ok_defaults(self):
        r = StepResult.ok()
        assert r.success
        assert r.output == {}
        assert r.context_updates == {}
        assert r.error is None
        assert r.quality is None
        assert r.events == []

    def test_ok_with_all_fields(self):
        qm = QualityMetrics(record_count=100, valid_count=95, passed=True)
        r = StepResult.ok(
            output={"count": 100},
            context_updates={"last": "step"},
            quality=qm,
            events=[{"event": "done"}],
        )
        assert r.output == {"count": 100}
        assert r.context_updates == {"last": "step"}
        assert r.quality is qm
        assert len(r.events) == 1

    def test_fail_defaults(self):
        r = StepResult.fail("something broke")
        assert not r.success
        assert r.error == "something broke"
        assert r.error_category == "INTERNAL"

    def test_fail_with_category_enum(self):
        r = StepResult.fail("timeout", category=ErrorCategory.TIMEOUT)
        assert r.error_category == "TIMEOUT"

    def test_fail_with_category_string(self):
        r = StepResult.fail("bad", category="CUSTOM")
        assert r.error_category == "CUSTOM"

    def test_fail_with_output_and_quality(self):
        qm = QualityMetrics(record_count=50, valid_count=10, passed=False)
        r = StepResult.fail(
            "quality check failed",
            category=ErrorCategory.DATA_QUALITY,
            output={"partial": True},
            quality=qm,
            events=[{"event": "fail"}],
        )
        assert r.output == {"partial": True}
        assert r.quality.passed is False
        assert len(r.events) == 1

    def test_skip(self):
        r = StepResult.skip("already done")
        assert r.success
        assert r.output["skipped"] is True
        assert r.output["skip_reason"] == "already done"

    def test_skip_with_output(self):
        r = StepResult.skip("cached", output={"cached": True})
        assert r.output == {"cached": True}


class TestStepResultPostInit:
    """Test __post_init__ behavior."""

    def test_failure_without_error_gets_default(self):
        r = StepResult(success=False)
        assert r.error == "Step failed without error message"

    def test_error_category_enum_normalized(self):
        r = StepResult(success=False, error="e", error_category=ErrorCategory.TRANSIENT)
        assert r.error_category == "TRANSIENT"  # Normalized to string


class TestStepResultSerialization:
    """Test to_dict."""

    def test_to_dict_success(self):
        r = StepResult.ok(output={"k": "v"}, context_updates={"u": 1})
        d = r.to_dict()
        assert d["success"] is True
        assert d["output"] == {"k": "v"}
        assert d["context_updates"] == {"u": 1}
        assert "error" not in d

    def test_to_dict_failure(self):
        r = StepResult.fail("oops", category="DATA_QUALITY")
        d = r.to_dict()
        assert d["success"] is False
        assert d["error"] == "oops"
        assert d["error_category"] == "DATA_QUALITY"

    def test_to_dict_with_quality(self):
        qm = QualityMetrics(record_count=100, valid_count=90)
        r = StepResult.ok(quality=qm)
        d = r.to_dict()
        assert "quality" in d
        assert d["quality"]["record_count"] == 100

    def test_to_dict_with_events(self):
        r = StepResult.ok(events=[{"type": "log"}])
        d = r.to_dict()
        assert d["events"] == [{"type": "log"}]

    def test_to_dict_with_next_step(self):
        r = StepResult(success=True, next_step="jump_here")
        d = r.to_dict()
        assert d["next_step"] == "jump_here"


class TestStepResultRepr:
    """Test __repr__."""

    def test_repr_ok(self):
        r = StepResult.ok(output={"a": 1, "b": 2})
        text = repr(r)
        assert "OK" in text
        assert "output_keys=" in text

    def test_repr_fail(self):
        r = StepResult.fail("e", category="TIMEOUT")
        text = repr(r)
        assert "FAIL" in text


# =============================================================================
# QualityMetrics
# =============================================================================


class TestQualityMetrics:
    """Test QualityMetrics."""

    def test_auto_calculate_invalid(self):
        qm = QualityMetrics(record_count=100, valid_count=90)
        assert qm.invalid_count == 10

    def test_valid_rate(self):
        qm = QualityMetrics(record_count=200, valid_count=150)
        assert qm.valid_rate == 0.75

    def test_valid_rate_zero_records(self):
        qm = QualityMetrics(record_count=0, valid_count=0)
        assert qm.valid_rate == 0.0

    def test_null_rate(self):
        qm = QualityMetrics(record_count=100, valid_count=100, null_count=5)
        assert qm.null_rate == 0.05

    def test_null_rate_zero_records(self):
        qm = QualityMetrics(record_count=0, null_count=0)
        assert qm.null_rate == 0.0

    def test_to_dict(self):
        qm = QualityMetrics(
            record_count=100,
            valid_count=95,
            null_count=2,
            passed=True,
            custom_metrics={"extra": 42},
            failure_reasons=["reason1"],
        )
        d = qm.to_dict()
        assert d["record_count"] == 100
        assert d["valid_rate"] == 0.95
        assert d["null_rate"] == 0.02
        assert d["custom_metrics"] == {"extra": 42}
        assert d["failure_reasons"] == ["reason1"]


# =============================================================================
# Step Types
# =============================================================================


class TestStepFactories:
    """Test Step factory methods."""

    def test_lambda_step(self):
        handler = lambda ctx, cfg: StepResult.ok()
        s = Step.lambda_("test", handler=handler, config={"k": "v"})
        assert s.step_type == StepType.LAMBDA
        assert s.handler is handler
        assert s.config == {"k": "v"}
        assert s.on_error == ErrorPolicy.STOP

    def test_operation_step(self):
        s = Step.operation("test", "my.operation", params={"x": 1})
        assert s.step_type == StepType.OPERATION
        assert s.operation_name == "my.operation"
        assert s.config == {"x": 1}

    def test_choice_step(self):
        cond = lambda ctx: True
        s = Step.choice("test", condition=cond, then_step="a", else_step="b")
        assert s.step_type == StepType.CHOICE
        assert s.condition is cond
        assert s.then_step == "a"
        assert s.else_step == "b"

    def test_wait_step(self):
        s = Step.wait("test", duration_seconds=30, next_step="next")
        assert s.step_type == StepType.WAIT
        assert s.duration_seconds == 30
        assert s.then_step == "next"

    def test_map_step(self):
        s = Step.map("test", items_path="items", iterator_workflow="wf", max_concurrency=8)
        assert s.step_type == StepType.MAP
        assert s.items_path == "items"
        assert s.iterator_workflow == "wf"
        assert s.max_concurrency == 8
        assert s.config == {"item_param": "item"}


class TestStepTierChecks:
    """Test tier classification helpers."""

    def test_lambda_is_basic(self):
        s = Step.lambda_("t", handler=lambda c, cfg: None)
        assert s.is_basic_tier()
        assert not s.is_intermediate_tier()
        assert not s.is_advanced_tier()

    def test_operation_is_basic(self):
        s = Step.operation("t", "p")
        assert s.is_basic_tier()

    def test_choice_is_intermediate(self):
        s = Step.choice("t", condition=lambda ctx: True, then_step="x")
        assert s.is_intermediate_tier()
        assert not s.is_basic_tier()

    def test_wait_is_advanced(self):
        s = Step.wait("t", duration_seconds=1)
        assert s.is_advanced_tier()
        assert not s.is_basic_tier()

    def test_map_is_advanced(self):
        s = Step.map("t", items_path="i", iterator_workflow="w")
        assert s.is_advanced_tier()


class TestStepSerialization:
    """Test Step to_dict."""

    def test_operation_to_dict(self):
        s = Step.operation("s", "p", params={"k": 1})
        d = s.to_dict()
        assert d["name"] == "s"
        assert d["type"] == "operation"
        assert d["operation"] == "p"
        assert d["config"] == {"k": 1}

    def test_lambda_to_dict(self):
        s = Step.lambda_("s", handler=lambda c, cfg: None)
        d = s.to_dict()
        assert d["type"] == "lambda"

    def test_choice_to_dict(self):
        s = Step.choice("s", condition=lambda ctx: True, then_step="a", else_step="b")
        d = s.to_dict()
        assert d["type"] == "choice"
        assert d["then_step"] == "a"
        assert d["else_step"] == "b"

    def test_wait_to_dict(self):
        s = Step.wait("s", duration_seconds=60)
        d = s.to_dict()
        assert d["type"] == "wait"
        assert d["duration_seconds"] == 60

    def test_map_to_dict(self):
        s = Step.map("s", items_path="items", iterator_workflow="w", max_concurrency=2)
        d = s.to_dict()
        assert d["type"] == "map"
        assert d["items_path"] == "items"
        assert d["max_concurrency"] == 2

    def test_on_error_excluded_when_default(self):
        s = Step.operation("s", "p")
        d = s.to_dict()
        assert "on_error" not in d

    def test_on_error_included_when_continue(self):
        s = Step.operation("s", "p", on_error=ErrorPolicy.CONTINUE)
        d = s.to_dict()
        assert d["on_error"] == "continue"


class TestStepRepr:
    """Test __repr__."""

    def test_operation_repr(self):
        s = Step.operation("ingest", "my.ingest")
        assert "operation" in repr(s).lower()

    def test_lambda_repr(self):
        s = Step.lambda_("val", handler=lambda c, cfg: None)
        assert "lambda" in repr(s).lower()


class TestRetryPolicy:
    """Test RetryPolicy defaults."""

    def test_defaults(self):
        rp = RetryPolicy()
        assert rp.max_attempts == 3
        assert rp.initial_delay_seconds == 1.0
        assert rp.backoff_multiplier == 2.0
        assert rp.max_delay_seconds == 60.0
        assert "TRANSIENT" in rp.retryable_categories


class TestErrorPolicy:
    """Test ErrorPolicy enum."""

    def test_values(self):
        assert ErrorPolicy.STOP.value == "stop"
        assert ErrorPolicy.CONTINUE.value == "continue"
        assert ErrorPolicy.RETRY.value == "retry"
