"""Tests for spine.orchestration.composition — composition operators."""

from __future__ import annotations

import pytest

from spine.orchestration.composition import (
    chain,
    conditional,
    merge_workflows,
    parallel,
    retry,
)
from spine.orchestration.step_result import StepResult
from spine.orchestration.step_types import ErrorPolicy, Step, StepType
from spine.orchestration.workflow import ExecutionMode, FailurePolicy, Workflow


def _ok_handler(ctx, config):
    return StepResult.ok(output={"done": True})


def _always_true(ctx):
    return True


def _always_false(ctx):
    return False


# ── chain() ──────────────────────────────────────────────────────────


class TestChain:
    """Tests for the chain() composition operator."""

    def test_chain_creates_sequential_workflow(self):
        wf = chain(
            "test.chain",
            Step.lambda_("a", _ok_handler),
            Step.lambda_("b", _ok_handler),
        )
        assert isinstance(wf, Workflow)
        assert wf.name == "test.chain"
        assert len(wf.steps) == 2
        assert wf.execution_policy.mode == ExecutionMode.SEQUENTIAL

    def test_chain_single_step(self):
        wf = chain("test.one", Step.lambda_("only", _ok_handler))
        assert len(wf.steps) == 1

    def test_chain_preserves_step_order(self):
        wf = chain(
            "test.order",
            Step.lambda_("first", _ok_handler),
            Step.lambda_("second", _ok_handler),
            Step.lambda_("third", _ok_handler),
        )
        names = [s.name for s in wf.steps]
        assert names == ["first", "second", "third"]

    def test_chain_with_domain_and_tags(self):
        wf = chain(
            "test.tagged",
            Step.lambda_("a", _ok_handler),
            domain="finra.otc",
            tags=["production"],
        )
        assert wf.domain == "finra.otc"
        assert wf.tags == ["production"]

    def test_chain_with_defaults(self):
        wf = chain(
            "test.defaults",
            Step.lambda_("a", _ok_handler),
            defaults={"tier": "NMS_TIER_1"},
        )
        assert wf.defaults == {"tier": "NMS_TIER_1"}

    def test_chain_no_steps_raises(self):
        with pytest.raises(ValueError, match="at least one step"):
            chain("empty")


# ── parallel() ───────────────────────────────────────────────────────


class TestParallel:
    """Tests for the parallel() composition operator."""

    def test_parallel_creates_dag_workflow(self):
        wf = parallel(
            "test.parallel",
            Step.operation("a", "pipe.a"),
            Step.operation("b", "pipe.b"),
        )
        assert wf.execution_policy.mode == ExecutionMode.PARALLEL
        assert len(wf.steps) == 2

    def test_parallel_with_merge_fn(self):
        wf = parallel(
            "test.merge",
            Step.operation("a", "pipe.a"),
            Step.operation("b", "pipe.b"),
            merge_fn=_ok_handler,
        )
        # 2 parallel + 1 merge = 3 steps
        assert len(wf.steps) == 3
        merge_step = wf.steps[-1]
        assert merge_step.name == "__merge__"
        assert set(merge_step.depends_on) == {"a", "b"}

    def test_parallel_max_concurrency(self):
        wf = parallel(
            "test.conc",
            Step.operation("a", "pipe.a"),
            Step.operation("b", "pipe.b"),
            max_concurrency=8,
        )
        assert wf.execution_policy.max_concurrency == 8

    def test_parallel_on_failure(self):
        wf = parallel(
            "test.fail",
            Step.operation("a", "pipe.a"),
            Step.operation("b", "pipe.b"),
            on_failure=FailurePolicy.CONTINUE,
        )
        assert wf.execution_policy.on_failure == FailurePolicy.CONTINUE

    def test_parallel_too_few_steps_raises(self):
        with pytest.raises(ValueError, match="at least two steps"):
            parallel("test.one", Step.operation("a", "pipe.a"))


# ── conditional() ────────────────────────────────────────────────────


class TestConditional:
    """Tests for the conditional() composition operator."""

    def test_conditional_creates_choice_workflow(self):
        wf = conditional(
            "test.cond",
            condition=_always_true,
            then_steps=[Step.operation("do_it", "pipe.do")],
        )
        # 1 choice + 1 then step
        assert len(wf.steps) == 2
        assert wf.steps[0].step_type == StepType.CHOICE

    def test_conditional_with_else(self):
        wf = conditional(
            "test.if_else",
            condition=_always_false,
            then_steps=[Step.operation("yes", "pipe.yes")],
            else_steps=[Step.operation("no", "pipe.no")],
        )
        # 1 choice + 1 then + 1 else
        assert len(wf.steps) == 3
        choice = wf.steps[0]
        assert choice.then_step == "yes"
        assert choice.else_step == "no"

    def test_conditional_no_then_raises(self):
        with pytest.raises(ValueError, match="at least one then_step"):
            conditional("empty", condition=_always_true, then_steps=[])

    def test_conditional_choice_step_name(self):
        wf = conditional(
            "test.named",
            condition=_always_true,
            then_steps=[Step.operation("proceed", "pipe.proceed")],
        )
        assert wf.steps[0].name == "__condition__"


# ── retry() ──────────────────────────────────────────────────────────


class TestRetry:
    """Tests for the retry() composition operator."""

    def test_retry_creates_multiple_attempt_steps(self):
        step = Step.operation("fetch", "data.fetch")
        wf = retry("test.retry", step, max_attempts=3)
        assert len(wf.steps) == 3
        assert wf.steps[0].name == "fetch_attempt_1"
        assert wf.steps[1].name == "fetch_attempt_2"
        assert wf.steps[2].name == "fetch_attempt_3"

    def test_retry_error_policy_continue_except_last(self):
        step = Step.operation("fetch", "data.fetch")
        wf = retry("test.retry", step, max_attempts=3)
        assert wf.steps[0].on_error == ErrorPolicy.CONTINUE
        assert wf.steps[1].on_error == ErrorPolicy.CONTINUE
        assert wf.steps[2].on_error == ErrorPolicy.STOP

    def test_retry_single_attempt(self):
        step = Step.lambda_("compute", _ok_handler)
        wf = retry("test.once", step, max_attempts=1)
        assert len(wf.steps) == 1
        assert wf.steps[0].name == "compute"  # no suffix for single

    def test_retry_preserves_step_type(self):
        step = Step.operation("fetch", "data.fetch")
        wf = retry("test.retry", step, max_attempts=2)
        for s in wf.steps:
            assert s.step_type == StepType.OPERATION
            assert s.operation_name == "data.fetch"

    def test_retry_adds_attempt_to_config(self):
        step = Step.operation("fetch", "data.fetch")
        wf = retry("test.retry", step, max_attempts=2)
        assert wf.steps[0].config["__attempt__"] == 1
        assert wf.steps[1].config["__attempt__"] == 2

    def test_retry_zero_attempts_raises(self):
        step = Step.lambda_("a", _ok_handler)
        with pytest.raises(ValueError, match="max_attempts must be >= 1"):
            retry("bad", step, max_attempts=0)


# ── merge_workflows() ───────────────────────────────────────────────


class TestMergeWorkflows:
    """Tests for the merge_workflows() operator."""

    def test_merge_combines_steps(self):
        wf1 = Workflow(name="wf1", steps=[Step.lambda_("a", _ok_handler)])
        wf2 = Workflow(name="wf2", steps=[Step.lambda_("b", _ok_handler)])
        merged = merge_workflows("combined", wf1, wf2)
        assert len(merged.steps) == 2
        assert [s.name for s in merged.steps] == ["a", "b"]

    def test_merge_prefixes_on_collision(self):
        wf1 = Workflow(name="wf1", steps=[Step.lambda_("common", _ok_handler)])
        wf2 = Workflow(name="wf2", steps=[Step.lambda_("common", _ok_handler)])
        merged = merge_workflows("combined", wf1, wf2)
        assert len(merged.steps) == 2
        names = [s.name for s in merged.steps]
        assert "common" in names
        assert "wf2.common" in names

    def test_merge_combines_defaults(self):
        wf1 = Workflow(name="wf1", steps=[Step.lambda_("a", _ok_handler)], defaults={"x": 1})
        wf2 = Workflow(name="wf2", steps=[Step.lambda_("b", _ok_handler)], defaults={"y": 2})
        merged = merge_workflows("combined", wf1, wf2)
        assert merged.defaults["x"] == 1
        assert merged.defaults["y"] == 2

    def test_merge_too_few_raises(self):
        wf1 = Workflow(name="wf1", steps=[Step.lambda_("a", _ok_handler)])
        with pytest.raises(ValueError, match="at least two workflows"):
            merge_workflows("bad", wf1)

    def test_merge_tags(self):
        wf1 = Workflow(name="wf1", steps=[Step.lambda_("a", _ok_handler)])
        wf2 = Workflow(name="wf2", steps=[Step.lambda_("b", _ok_handler)])
        merged = merge_workflows("combined", wf1, wf2, tags=["merged", "test"])
        assert merged.tags == ["merged", "test"]
