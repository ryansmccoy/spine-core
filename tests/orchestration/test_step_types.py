"""Tests for Step, StepType, ErrorPolicy, RetryPolicy, and callable-ref utilities.

Covers all Step factory methods, serialization, tier helpers, and the
_callable_ref / resolve_callable_ref utilities used by YAML serialization.
"""

from __future__ import annotations

import pytest

from spine.orchestration.step_result import StepResult
from spine.orchestration.step_types import (
    ErrorPolicy,
    RetryPolicy,
    Step,
    StepType,
    _callable_ref,
    resolve_callable_ref,
)
from spine.orchestration.workflow_context import WorkflowContext


# ---------------------------------------------------------------------------
# StepType enum
# ---------------------------------------------------------------------------


class TestStepType:
    def test_values(self):
        assert StepType.LAMBDA.value == "lambda"
        assert StepType.OPERATION.value == "operation"
        assert StepType.CHOICE.value == "choice"
        assert StepType.WAIT.value == "wait"
        assert StepType.MAP.value == "map"

    def test_is_str_enum(self):
        assert isinstance(StepType.LAMBDA, str)


# ---------------------------------------------------------------------------
# ErrorPolicy / RetryPolicy
# ---------------------------------------------------------------------------


class TestErrorPolicy:
    def test_values(self):
        assert ErrorPolicy.STOP.value == "stop"
        assert ErrorPolicy.CONTINUE.value == "continue"
        assert ErrorPolicy.RETRY.value == "retry"

    def test_is_str_enum(self):
        assert isinstance(ErrorPolicy.STOP, str)


class TestRetryPolicy:
    def test_defaults(self):
        rp = RetryPolicy()
        assert rp.max_attempts == 3
        assert rp.initial_delay_seconds == 1.0
        assert rp.backoff_multiplier == 2.0
        assert rp.max_delay_seconds == 60.0
        assert "TRANSIENT" in rp.retryable_categories
        assert "TIMEOUT" in rp.retryable_categories

    def test_custom(self):
        rp = RetryPolicy(max_attempts=5, initial_delay_seconds=0.5)
        assert rp.max_attempts == 5
        assert rp.initial_delay_seconds == 0.5

    def test_frozen(self):
        rp = RetryPolicy()
        with pytest.raises(AttributeError):
            rp.max_attempts = 10  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Step factory: lambda_
# ---------------------------------------------------------------------------


def _dummy_handler(ctx: WorkflowContext, config: dict) -> StepResult:
    return StepResult.ok(output={"handled": True})


class TestStepLambda:
    def test_basic(self):
        s = Step.lambda_("step1", _dummy_handler)
        assert s.name == "step1"
        assert s.step_type == StepType.LAMBDA
        assert s.handler is _dummy_handler
        assert s.on_error == ErrorPolicy.STOP

    def test_with_config(self):
        s = Step.lambda_("s", _dummy_handler, config={"k": "v"})
        assert s.config["k"] == "v"

    def test_with_error_policy(self):
        s = Step.lambda_("s", _dummy_handler, on_error=ErrorPolicy.CONTINUE)
        assert s.on_error == ErrorPolicy.CONTINUE

    def test_with_depends_on_list(self):
        s = Step.lambda_("s", _dummy_handler, depends_on=["a", "b"])
        assert s.depends_on == ("a", "b")

    def test_with_depends_on_tuple(self):
        s = Step.lambda_("s", _dummy_handler, depends_on=("a",))
        assert s.depends_on == ("a",)


# ---------------------------------------------------------------------------
# Step factory: operation
# ---------------------------------------------------------------------------


class TestStepOperation:
    def test_basic(self):
        s = Step.operation("ingest", "my.operation")
        assert s.step_type == StepType.OPERATION
        assert s.operation_name == "my.operation"

    def test_with_params(self):
        s = Step.operation("ingest", "p", params={"batch": 100})
        assert s.config["batch"] == 100

    def test_with_depends_on(self):
        s = Step.operation("load", "p", depends_on=["extract"])
        assert "extract" in s.depends_on


# ---------------------------------------------------------------------------
# Step factory: choice
# ---------------------------------------------------------------------------


class TestStepChoice:
    def test_basic(self):
        cond = lambda ctx: True
        s = Step.choice("branch", cond, then_step="a", else_step="b")
        assert s.step_type == StepType.CHOICE
        assert s.then_step == "a"
        assert s.else_step == "b"
        assert s.condition is cond

    def test_no_else(self):
        s = Step.choice("branch", lambda ctx: True, then_step="go")
        assert s.else_step is None


# ---------------------------------------------------------------------------
# Step factory: wait
# ---------------------------------------------------------------------------


class TestStepWait:
    def test_basic(self):
        s = Step.wait("pause", duration_seconds=30)
        assert s.step_type == StepType.WAIT
        assert s.duration_seconds == 30

    def test_with_next(self):
        s = Step.wait("pause", duration_seconds=5, next_step="resume")
        assert s.then_step == "resume"


# ---------------------------------------------------------------------------
# Step factory: map
# ---------------------------------------------------------------------------


class TestStepMap:
    def test_basic(self):
        from spine.orchestration.workflow import Workflow
        wf = Workflow(name="iter", steps=[])
        s = Step.map("fan", items_path="data.items", iterator_workflow=wf)
        assert s.step_type == StepType.MAP
        assert s.items_path == "data.items"
        assert s.max_concurrency == 4
        assert s.config["item_param"] == "item"

    def test_custom_concurrency(self):
        s = Step.map("fan", items_path="items", iterator_workflow=None, max_concurrency=8)
        assert s.max_concurrency == 8


# ---------------------------------------------------------------------------
# Step factory: from_function
# ---------------------------------------------------------------------------


class TestStepFromFunction:
    def test_plain_function(self):
        def add(a: int, b: int) -> dict:
            return {"sum": a + b}

        s = Step.from_function("add", add, config={"a": 1, "b": 2})
        assert s.step_type == StepType.LAMBDA
        assert s.handler is not None
        assert s.handler is not add  # wrapped

    def test_handler_works(self):
        def multiply(x: int, y: int) -> dict:
            return {"product": x * y}

        s = Step.from_function("mul", multiply)
        ctx = WorkflowContext.create("test", params={"x": 3, "y": 7})
        result = s.handler(ctx, s.config)
        assert result.success is True
        assert result.output["product"] == 21


# ---------------------------------------------------------------------------
# Tier helpers
# ---------------------------------------------------------------------------


class TestTierHelpers:
    def test_lambda_is_basic(self):
        s = Step.lambda_("s", _dummy_handler)
        assert s.is_basic_tier() is True
        assert s.is_intermediate_tier() is False
        assert s.is_advanced_tier() is False

    def test_operation_is_basic(self):
        s = Step.operation("s", "p")
        assert s.is_basic_tier() is True

    def test_choice_is_intermediate(self):
        s = Step.choice("s", lambda c: True, then_step="t")
        assert s.is_intermediate_tier() is True
        assert s.is_basic_tier() is False

    def test_wait_is_advanced(self):
        s = Step.wait("s", duration_seconds=1)
        assert s.is_advanced_tier() is True

    def test_map_is_advanced(self):
        s = Step.map("s", items_path="items", iterator_workflow=None)
        assert s.is_advanced_tier() is True


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


class TestStepSerialization:
    def test_lambda_to_dict(self):
        s = Step.lambda_("lstep", _dummy_handler)
        d = s.to_dict()
        assert d["name"] == "lstep"
        assert d["type"] == "lambda"
        assert "handler_ref" in d  # _dummy_handler is a named function

    def test_operation_to_dict(self):
        d = Step.operation("p", "my.operation").to_dict()
        assert d["operation"] == "my.operation"

    def test_choice_to_dict(self):
        d = Step.choice("c", lambda ctx: True, then_step="a", else_step="b").to_dict()
        assert d["then_step"] == "a"
        assert d["else_step"] == "b"

    def test_wait_to_dict(self):
        d = Step.wait("w", duration_seconds=10).to_dict()
        assert d["duration_seconds"] == 10

    def test_map_to_dict(self):
        d = Step.map("m", items_path="items", iterator_workflow=None).to_dict()
        assert d["items_path"] == "items"
        assert d["max_concurrency"] == 4

    def test_error_policy_in_dict(self):
        d = Step.lambda_("s", _dummy_handler, on_error=ErrorPolicy.CONTINUE).to_dict()
        assert d["on_error"] == "continue"

    def test_depends_on_in_dict(self):
        d = Step.lambda_("s", _dummy_handler, depends_on=["a"]).to_dict()
        assert d["depends_on"] == ["a"]

    def test_config_not_in_dict_when_empty(self):
        d = Step.lambda_("s", _dummy_handler).to_dict()
        assert "config" not in d


# ---------------------------------------------------------------------------
# _callable_ref and resolve_callable_ref
# ---------------------------------------------------------------------------


class TestCallableRef:
    def test_named_function(self):
        ref = _callable_ref(_dummy_handler)
        assert ref is not None
        assert ":" in ref
        assert "_dummy_handler" in ref

    def test_lambda_returns_none(self):
        ref = _callable_ref(lambda x: x)
        assert ref is None

    def test_none_returns_none(self):
        assert _callable_ref(None) is None

    def test_resolve_roundtrip(self):
        ref = _callable_ref(_dummy_handler)
        assert ref is not None
        fn = resolve_callable_ref(ref)
        assert fn is _dummy_handler

    def test_resolve_bad_ref(self):
        with pytest.raises(ValueError, match="missing ':'"):
            resolve_callable_ref("nocolon")

    def test_resolve_missing_module(self):
        with pytest.raises(ImportError):
            resolve_callable_ref("no.such.module:func")

    def test_resolve_missing_attr(self):
        with pytest.raises(AttributeError):
            resolve_callable_ref("os:no_such_attr_xyz")


# ---------------------------------------------------------------------------
# Repr
# ---------------------------------------------------------------------------


class TestStepRepr:
    def test_lambda_repr(self):
        s = Step.lambda_("s", _dummy_handler)
        assert "lambda_" in repr(s)
        assert "'s'" in repr(s)

    def test_operation_repr(self):
        s = Step.operation("s", "my.pipe")
        assert "operation" in repr(s)
        assert "my.pipe" in repr(s)

    def test_choice_repr(self):
        s = Step.choice("s", lambda c: True, then_step="t")
        assert "choice" in repr(s)

    def test_wait_repr(self):
        s = Step.wait("s", duration_seconds=5)
        assert "Step(" in repr(s)
