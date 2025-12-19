"""Tests for Idea #6 — Workflow Templates & Recipes.

Covers:
- etl_pipeline template (with/without validation)
- fan_out_fan_in template (with/without merge)
- conditional_branch template
- retry_wrapper template (with/without fallback)
- scheduled_batch template
- Template registry (register, get, list)
- Custom template registration
"""

from __future__ import annotations

import pytest

from spine.orchestration import Step, StepResult, StepType, Workflow
from spine.orchestration.step_types import ErrorPolicy, RetryPolicy
from spine.orchestration.templates import (
    conditional_branch,
    etl_pipeline,
    fan_out_fan_in,
    get_template,
    list_templates,
    register_template,
    retry_wrapper,
    scheduled_batch,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _validate_fn(ctx, config):
    return StepResult.ok(output={"valid": True})


def _merge_fn(ctx, config):
    return StepResult.ok(output={"merged": True})


def _condition_fn(ctx):
    return True


def _notify_fn(ctx, config):
    return StepResult.ok(output={"notified": True})


# ---------------------------------------------------------------------------
# ETL Pipeline template
# ---------------------------------------------------------------------------

class TestETLPipeline:
    def test_basic_etl(self):
        wf = etl_pipeline(
            name="test.etl",
            extract_pipeline="extract.pipe",
            transform_pipeline="transform.pipe",
            load_pipeline="load.pipe",
        )

        assert isinstance(wf, Workflow)
        assert wf.name == "test.etl"
        assert len(wf.steps) == 3
        assert wf.steps[0].name == "extract"
        assert wf.steps[1].name == "transform"
        assert wf.steps[2].name == "load"
        assert all(s.step_type == StepType.PIPELINE for s in wf.steps)

    def test_etl_with_validation(self):
        wf = etl_pipeline(
            name="test.etl.validated",
            extract_pipeline="ep",
            transform_pipeline="tp",
            load_pipeline="lp",
            validate_handler=_validate_fn,
        )

        assert len(wf.steps) == 4
        assert wf.steps[1].name == "validate"
        assert wf.steps[1].step_type == StepType.LAMBDA

    def test_etl_dependencies(self):
        wf = etl_pipeline(
            name="dep.test",
            extract_pipeline="ep",
            transform_pipeline="tp",
            load_pipeline="lp",
        )

        assert wf.steps[1].depends_on == ("extract",)
        assert wf.steps[2].depends_on == ("transform",)

    def test_etl_with_validation_dependencies(self):
        wf = etl_pipeline(
            name="dep.test",
            extract_pipeline="ep",
            transform_pipeline="tp",
            load_pipeline="lp",
            validate_handler=_validate_fn,
        )

        assert wf.steps[1].depends_on == ("extract",)  # validate
        assert wf.steps[2].depends_on == ("validate",)  # transform

    def test_etl_metadata(self):
        wf = etl_pipeline(
            name="meta.etl",
            extract_pipeline="ep",
            transform_pipeline="tp",
            load_pipeline="lp",
            domain="finance",
            description="Daily finance ETL",
            tags=["daily", "finance"],
        )

        assert wf.domain == "finance"
        assert wf.description == "Daily finance ETL"
        assert wf.tags == ["daily", "finance"]


# ---------------------------------------------------------------------------
# Fan-out/fan-in template
# ---------------------------------------------------------------------------

class TestFanOutFanIn:
    def test_basic_fan_out(self):
        wf = fan_out_fan_in(
            name="test.fanout",
            items_path="$.records",
            iterator_pipeline="record.process",
        )

        assert len(wf.steps) == 1
        assert wf.steps[0].name == "scatter"
        assert wf.steps[0].step_type == StepType.MAP
        assert wf.steps[0].items_path == "$.records"

    def test_fan_out_with_merge(self):
        wf = fan_out_fan_in(
            name="test.fanout.merge",
            items_path="$.items",
            iterator_pipeline="process",
            merge_handler=_merge_fn,
        )

        assert len(wf.steps) == 2
        assert wf.steps[1].name == "merge"
        assert wf.steps[1].step_type == StepType.LAMBDA

    def test_fan_out_concurrency(self):
        wf = fan_out_fan_in(
            name="concurrent",
            items_path="$.data",
            iterator_pipeline="p",
            max_concurrency=16,
        )

        assert wf.steps[0].max_concurrency == 16


# ---------------------------------------------------------------------------
# Conditional branch template
# ---------------------------------------------------------------------------

class TestConditionalBranch:
    def test_basic_branch(self):
        wf = conditional_branch(
            name="test.branch",
            condition=_condition_fn,
            true_pipeline="path.a",
            false_pipeline="path.b",
        )

        assert len(wf.steps) == 3
        choice_step = [s for s in wf.steps if s.step_type == StepType.CHOICE][0]
        assert choice_step.name == "route"
        assert choice_step.then_step == "on_true"
        assert choice_step.else_step == "on_false"

    def test_branch_has_both_pipelines(self):
        wf = conditional_branch(
            name="test.branch",
            condition=_condition_fn,
            true_pipeline="yes",
            false_pipeline="no",
        )

        pipeline_steps = [s for s in wf.steps if s.step_type == StepType.PIPELINE]
        assert len(pipeline_steps) == 2
        names = {s.pipeline_name for s in pipeline_steps}
        assert names == {"yes", "no"}


# ---------------------------------------------------------------------------
# Retry wrapper template
# ---------------------------------------------------------------------------

class TestRetryWrapper:
    def test_basic_retry(self):
        wf = retry_wrapper(
            name="test.retry",
            target_pipeline="risky.pipeline",
            max_retries=5,
        )

        assert len(wf.steps) == 1
        step = wf.steps[0]
        assert step.pipeline_name == "risky.pipeline"
        assert step.on_error == ErrorPolicy.CONTINUE
        assert step.retry_policy is not None
        assert step.retry_policy.max_attempts == 5

    def test_retry_with_fallback(self):
        wf = retry_wrapper(
            name="test.retry.fb",
            target_pipeline="risky",
            fallback_pipeline="safe.fallback",
        )

        assert len(wf.steps) == 2
        assert wf.steps[1].name == "fallback"
        assert wf.steps[1].pipeline_name == "safe.fallback"

    def test_retry_backoff(self):
        wf = retry_wrapper(
            name="test.retry",
            target_pipeline="p",
        )

        rp = wf.steps[0].retry_policy
        assert rp.initial_delay_seconds == 1
        assert rp.backoff_multiplier == 2.0


# ---------------------------------------------------------------------------
# Scheduled batch template
# ---------------------------------------------------------------------------

class TestScheduledBatch:
    def test_basic_batch(self):
        wf = scheduled_batch(
            name="test.batch",
            wait_seconds=60,
            execute_pipeline="batch.run",
        )

        assert len(wf.steps) == 2
        assert wf.steps[0].step_type == StepType.WAIT
        assert wf.steps[0].duration_seconds == 60
        assert wf.steps[1].step_type == StepType.PIPELINE

    def test_batch_with_validate_and_notify(self):
        wf = scheduled_batch(
            name="full.batch",
            wait_seconds=30,
            execute_pipeline="batch.run",
            validate_handler=_validate_fn,
            notify_handler=_notify_fn,
        )

        assert len(wf.steps) == 4
        types = [s.step_type for s in wf.steps]
        assert types == [StepType.WAIT, StepType.PIPELINE, StepType.LAMBDA, StepType.LAMBDA]

    def test_batch_dependencies(self):
        wf = scheduled_batch(
            name="dep.batch",
            wait_seconds=10,
            execute_pipeline="p",
            validate_handler=_validate_fn,
            notify_handler=_notify_fn,
        )

        assert wf.steps[1].depends_on == ("delay",)  # execute after wait
        assert wf.steps[2].depends_on == ("execute",)  # validate after execute
        assert wf.steps[3].depends_on == ("validate",)  # notify after validate


# ---------------------------------------------------------------------------
# Template registry
# ---------------------------------------------------------------------------

class TestTemplateRegistry:
    def test_list_templates(self):
        names = list_templates()
        assert "etl_pipeline" in names
        assert "fan_out_fan_in" in names
        assert "conditional_branch" in names
        assert "retry_wrapper" in names
        assert "scheduled_batch" in names

    def test_get_template(self):
        factory = get_template("etl_pipeline")
        assert factory is etl_pipeline

    def test_get_unknown_template_raises(self):
        with pytest.raises(KeyError, match="Unknown template"):
            get_template("nonexistent_template")

    def test_register_custom_template(self):
        def custom_factory(**kwargs):
            return Workflow(name=kwargs.get("name", "custom"), steps=[])

        register_template("custom_test", custom_factory)
        assert "custom_test" in list_templates()
        assert get_template("custom_test") is custom_factory

    def test_builtin_count(self):
        names = list_templates()
        assert len(names) >= 5  # At least the 5 built-ins
