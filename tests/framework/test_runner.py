"""Tests for OperationRunner — synchronous operation execution.

Covers:
- run() happy path
- run() with OperationNotFoundError
- run() with BadParamsError (spec validation + custom)
- run() with unexpected exception → FAILED result
- run_all() stops on first failure
- get_runner() singleton factory
"""

from datetime import datetime, timedelta

import pytest

from spine.framework.exceptions import BadParamsError, OperationNotFoundError
from spine.framework.operations import Operation, OperationResult, OperationStatus
from spine.framework.registry import clear_registry, register_operation
from spine.framework.runner import OperationRunner, get_runner


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean_registry():
    """Clear the operation registry before and after each test."""
    clear_registry()
    yield
    clear_registry()


class SuccessOperation(Operation):
    """A operation that always succeeds."""

    name = "success"

    def run(self) -> OperationResult:
        return OperationResult(
            status=OperationStatus.COMPLETED,
            started_at=datetime.now(),
            completed_at=datetime.now() + timedelta(seconds=1),
            metrics={"rows": 42},
        )


class FailOperation(Operation):
    """A operation that always fails."""

    name = "fail"

    def run(self) -> OperationResult:
        raise RuntimeError("something broke")


class BadValidateOperation(Operation):
    """A operation with custom param validation that rejects everything."""

    name = "bad_validate"

    def validate_params(self) -> None:
        raise ValueError("params are bad")

    def run(self) -> OperationResult:  # pragma: no cover
        return OperationResult(status=OperationStatus.COMPLETED, started_at=datetime.now())


# ---------------------------------------------------------------------------
# Tests: run()
# ---------------------------------------------------------------------------


class TestOperationRunnerRun:
    def test_run_success(self):
        register_operation("success")(SuccessOperation)
        runner = OperationRunner()
        result = runner.run("success")
        assert result.status == OperationStatus.COMPLETED
        assert result.metrics == {"rows": 42}

    def test_run_not_found(self):
        runner = OperationRunner()
        with pytest.raises(OperationNotFoundError):
            runner.run("nonexistent")

    def test_run_exception_returns_failed(self):
        register_operation("fail")(FailOperation)
        runner = OperationRunner()
        result = runner.run("fail")
        assert result.status == OperationStatus.FAILED
        assert "something broke" in result.error

    def test_run_custom_validate_raises_bad_params(self):
        register_operation("bad_validate")(BadValidateOperation)
        runner = OperationRunner()
        with pytest.raises(BadParamsError):
            runner.run("bad_validate")


# ---------------------------------------------------------------------------
# Tests: run_all()
# ---------------------------------------------------------------------------


class TestOperationRunnerRunAll:
    def test_run_all_success(self):
        register_operation("s1")(SuccessOperation)
        register_operation("s2")(SuccessOperation)
        runner = OperationRunner()
        results = runner.run_all(["s1", "s2"])
        assert len(results) == 2
        assert all(r.status == OperationStatus.COMPLETED for r in results)

    def test_run_all_stops_on_failure(self):
        register_operation("s1")(SuccessOperation)
        register_operation("fail")(FailOperation)
        register_operation("s3")(SuccessOperation)
        runner = OperationRunner()
        results = runner.run_all(["s1", "fail", "s3"])
        assert len(results) == 2  # stopped after "fail", s3 not run
        assert results[0].status == OperationStatus.COMPLETED
        assert results[1].status == OperationStatus.FAILED


# ---------------------------------------------------------------------------
# Tests: get_runner()
# ---------------------------------------------------------------------------


class TestGetRunner:
    def test_returns_operation_runner(self):
        runner = get_runner()
        assert isinstance(runner, OperationRunner)

    def test_singleton(self):
        r1 = get_runner()
        r2 = get_runner()
        assert r1 is r2
