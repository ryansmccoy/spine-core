"""Tests for ``spine.execution.dispatcher`` — EventDispatcher submission, queries, cancel/retry."""

from __future__ import annotations

import pytest

from spine.execution.dispatcher import EventDispatcher
from spine.execution.runs import RunStatus
from spine.execution.spec import WorkSpec


# ---------------------------------------------------------------------------
# Minimal Executor Stubs
# ---------------------------------------------------------------------------


class _OkExecutor:
    """Executor that always succeeds, returning a fixed external ref."""

    name = "ok"

    async def submit(self, spec: WorkSpec) -> str:
        return f"ref-{spec.name}"

    async def cancel(self, external_ref: str) -> bool:
        return True

    async def get_status(self, external_ref: str) -> str | None:
        return "completed"


class _FailExecutor:
    """Executor that always raises on submit."""

    name = "fail"

    async def submit(self, spec: WorkSpec) -> str:
        raise RuntimeError("executor down")

    async def cancel(self, external_ref: str) -> bool:
        return False

    async def get_status(self, external_ref: str) -> str | None:
        return None


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def dispatcher():
    return EventDispatcher(executor=_OkExecutor())


@pytest.fixture()
def fail_dispatcher():
    return EventDispatcher(executor=_FailExecutor())


# ---------------------------------------------------------------------------
# Submit
# ---------------------------------------------------------------------------


class TestSubmit:
    @pytest.mark.asyncio
    async def test_submit_returns_run_id(self, dispatcher):
        run_id = await dispatcher.submit(WorkSpec(kind="task", name="ping"))
        assert isinstance(run_id, str) and len(run_id) > 0

    @pytest.mark.asyncio
    async def test_submit_task_convenience(self, dispatcher):
        run_id = await dispatcher.submit_task("send_email", {"to": "a@b.com"})
        run = await dispatcher.get_run(run_id)
        assert run is not None
        assert run.spec.kind == "task"
        assert run.spec.name == "send_email"

    @pytest.mark.asyncio
    async def test_submit_operation_convenience(self, dispatcher):
        run_id = await dispatcher.submit_operation("ingest", {"date": "2026-01-01"})
        run = await dispatcher.get_run(run_id)
        assert run.spec.kind == "operation"

    @pytest.mark.asyncio
    async def test_submit_workflow_convenience(self, dispatcher):
        run_id = await dispatcher.submit_workflow("daily")
        run = await dispatcher.get_run(run_id)
        assert run.spec.kind == "workflow"

    @pytest.mark.asyncio
    async def test_submit_step_convenience(self, dispatcher):
        parent = await dispatcher.submit_workflow("parent_wf")
        step_id = await dispatcher.submit_step("validate", parent_run_id=parent)
        step = await dispatcher.get_run(step_id)
        assert step.spec.kind == "step"
        assert step.spec.parent_run_id == parent

    @pytest.mark.asyncio
    async def test_idempotent_submit(self, dispatcher):
        """Submitting with same idempotency key returns same run_id."""
        id1 = await dispatcher.submit(
            WorkSpec(kind="task", name="t", idempotency_key="uniq-1"),
        )
        id2 = await dispatcher.submit(
            WorkSpec(kind="task", name="t", idempotency_key="uniq-1"),
        )
        assert id1 == id2


# ---------------------------------------------------------------------------
# Failure handling
# ---------------------------------------------------------------------------


class TestSubmitFailure:
    @pytest.mark.asyncio
    async def test_executor_failure_marks_run_failed(self, fail_dispatcher):
        run_id = await fail_dispatcher.submit_task("boom")
        run = await fail_dispatcher.get_run(run_id)
        assert run.status == RunStatus.FAILED
        assert "executor down" in run.error


# ---------------------------------------------------------------------------
# Query
# ---------------------------------------------------------------------------


class TestQuery:
    @pytest.mark.asyncio
    async def test_get_run_not_found(self, dispatcher):
        result = await dispatcher.get_run("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_list_runs_empty(self, dispatcher):
        runs = await dispatcher.list_runs()
        assert runs == []

    @pytest.mark.asyncio
    async def test_list_runs_filter_by_kind(self, dispatcher):
        await dispatcher.submit_task("t1")
        await dispatcher.submit_operation("p1")
        tasks = await dispatcher.list_runs(kind="task")
        assert all(r.kind == "task" for r in tasks)
        assert len(tasks) == 1

    @pytest.mark.asyncio
    async def test_list_runs_filter_by_name(self, dispatcher):
        await dispatcher.submit_task("alpha")
        await dispatcher.submit_task("beta")
        found = await dispatcher.list_runs(name="alpha")
        assert len(found) == 1
        assert found[0].name == "alpha"

    @pytest.mark.asyncio
    async def test_get_events(self, dispatcher):
        run_id = await dispatcher.submit_task("e1")
        events = await dispatcher.get_events(run_id)
        assert len(events) >= 1  # at least CREATED event

    @pytest.mark.asyncio
    async def test_get_children(self, dispatcher):
        parent_id = await dispatcher.submit_workflow("wf")
        await dispatcher.submit_step("step1", parent_run_id=parent_id)
        children = await dispatcher.get_children(parent_id)
        assert len(children) == 1


# ---------------------------------------------------------------------------
# Control — cancel / retry
# ---------------------------------------------------------------------------


class TestControl:
    @pytest.mark.asyncio
    async def test_cancel_nonexistent_returns_false(self, dispatcher):
        assert await dispatcher.cancel("nope") is False

    @pytest.mark.asyncio
    async def test_retry_not_found_raises(self, dispatcher):
        with pytest.raises(ValueError, match="not found"):
            await dispatcher.retry("nope")

    @pytest.mark.asyncio
    async def test_retry_creates_new_run(self, fail_dispatcher):
        """Retry a failed run → new run created."""
        orig_id = await fail_dispatcher.submit_task("retriable")
        orig = await fail_dispatcher.get_run(orig_id)
        assert orig.status == RunStatus.FAILED

        new_id = await fail_dispatcher.retry(orig_id)
        assert new_id != orig_id
        new_run = await fail_dispatcher.get_run(new_id)
        assert new_run is not None
        assert new_run.retry_of_run_id == orig_id
        assert new_run.attempt == orig.attempt + 1
