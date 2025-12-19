"""Tests for PipelineRunner — synchronous pipeline execution.

Covers:
- run() happy path
- run() with PipelineNotFoundError
- run() with BadParamsError (spec validation + custom)
- run() with unexpected exception → FAILED result
- run_all() stops on first failure
- get_runner() singleton factory
"""

from datetime import datetime, timedelta

import pytest

from spine.framework.exceptions import BadParamsError, PipelineNotFoundError
from spine.framework.pipelines import Pipeline, PipelineResult, PipelineStatus
from spine.framework.registry import clear_registry, register_pipeline
from spine.framework.runner import PipelineRunner, get_runner


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean_registry():
    """Clear the pipeline registry before and after each test."""
    clear_registry()
    yield
    clear_registry()


class SuccessPipeline(Pipeline):
    """A pipeline that always succeeds."""

    name = "success"

    def run(self) -> PipelineResult:
        return PipelineResult(
            status=PipelineStatus.COMPLETED,
            started_at=datetime.now(),
            completed_at=datetime.now() + timedelta(seconds=1),
            metrics={"rows": 42},
        )


class FailPipeline(Pipeline):
    """A pipeline that always fails."""

    name = "fail"

    def run(self) -> PipelineResult:
        raise RuntimeError("something broke")


class BadValidatePipeline(Pipeline):
    """A pipeline with custom param validation that rejects everything."""

    name = "bad_validate"

    def validate_params(self) -> None:
        raise ValueError("params are bad")

    def run(self) -> PipelineResult:  # pragma: no cover
        return PipelineResult(status=PipelineStatus.COMPLETED, started_at=datetime.now())


# ---------------------------------------------------------------------------
# Tests: run()
# ---------------------------------------------------------------------------


class TestPipelineRunnerRun:
    def test_run_success(self):
        register_pipeline("success")(SuccessPipeline)
        runner = PipelineRunner()
        result = runner.run("success")
        assert result.status == PipelineStatus.COMPLETED
        assert result.metrics == {"rows": 42}

    def test_run_not_found(self):
        runner = PipelineRunner()
        with pytest.raises(PipelineNotFoundError):
            runner.run("nonexistent")

    def test_run_exception_returns_failed(self):
        register_pipeline("fail")(FailPipeline)
        runner = PipelineRunner()
        result = runner.run("fail")
        assert result.status == PipelineStatus.FAILED
        assert "something broke" in result.error

    def test_run_custom_validate_raises_bad_params(self):
        register_pipeline("bad_validate")(BadValidatePipeline)
        runner = PipelineRunner()
        with pytest.raises(BadParamsError):
            runner.run("bad_validate")


# ---------------------------------------------------------------------------
# Tests: run_all()
# ---------------------------------------------------------------------------


class TestPipelineRunnerRunAll:
    def test_run_all_success(self):
        register_pipeline("s1")(SuccessPipeline)
        register_pipeline("s2")(SuccessPipeline)
        runner = PipelineRunner()
        results = runner.run_all(["s1", "s2"])
        assert len(results) == 2
        assert all(r.status == PipelineStatus.COMPLETED for r in results)

    def test_run_all_stops_on_failure(self):
        register_pipeline("s1")(SuccessPipeline)
        register_pipeline("fail")(FailPipeline)
        register_pipeline("s3")(SuccessPipeline)
        runner = PipelineRunner()
        results = runner.run_all(["s1", "fail", "s3"])
        assert len(results) == 2  # stopped after "fail", s3 not run
        assert results[0].status == PipelineStatus.COMPLETED
        assert results[1].status == PipelineStatus.FAILED


# ---------------------------------------------------------------------------
# Tests: get_runner()
# ---------------------------------------------------------------------------


class TestGetRunner:
    def test_returns_pipeline_runner(self):
        runner = get_runner()
        assert isinstance(runner, PipelineRunner)

    def test_singleton(self):
        r1 = get_runner()
        r2 = get_runner()
        assert r1 is r2
