"""Tests for EventDispatcher — the central submission/query API.

Covers:
- submit (canonical), convenience wrappers (submit_task, submit_operation, etc.)
- Idempotency de-duplication
- Query: get_run, list_runs, get_events, get_children
- Control: cancel, retry, lifecycle marks
- clear()
- Executor error handling
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from spine.execution.dispatcher import EventDispatcher
from spine.execution.runs import RunStatus
from spine.execution.spec import WorkSpec


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_executor(**overrides):
    """Create a mock async executor."""
    ex = AsyncMock()
    ex.name = "mock"
    ex.submit = AsyncMock(return_value="ext-ref-001")
    ex.cancel = AsyncMock(return_value=True)
    ex.get_status = AsyncMock(return_value="queued")
    ex.get_result = AsyncMock(return_value=None)
    for k, v in overrides.items():
        setattr(ex, k, v)
    return ex


def _make_spec(**overrides) -> WorkSpec:
    defaults = dict(kind="task", name="handler_a", params={"x": 1})
    defaults.update(overrides)
    return WorkSpec(**defaults)


# ---------------------------------------------------------------------------
# Tests: init
# ---------------------------------------------------------------------------


class TestEventDispatcherInit:
    def test_default_init(self):
        d = EventDispatcher(executor=_make_executor())
        assert d.ledger is None
        assert d.registry is None
        assert d.concurrency is None
        assert d._memory_runs == {}

    def test_init_with_all_kwargs(self):
        ledger = MagicMock()
        registry = MagicMock()
        conc = MagicMock()
        d = EventDispatcher(
            executor=_make_executor(), ledger=ledger, registry=registry, concurrency=conc
        )
        assert d.ledger is ledger
        assert d.registry is registry
        assert d.concurrency is conc


# ---------------------------------------------------------------------------
# Tests: submit
# ---------------------------------------------------------------------------


class TestSubmit:
    @pytest.mark.asyncio
    async def test_submit_returns_run_id(self):
        d = EventDispatcher(executor=_make_executor())
        run_id = await d.submit(_make_spec())
        assert isinstance(run_id, str) and len(run_id) == 36  # uuid

    @pytest.mark.asyncio
    async def test_submit_creates_run_record(self):
        d = EventDispatcher(executor=_make_executor())
        run_id = await d.submit(_make_spec(name="my_task"))
        run = await d.get_run(run_id)
        assert run is not None
        assert run.spec.name == "my_task"

    @pytest.mark.asyncio
    async def test_submit_calls_executor(self):
        ex = _make_executor()
        d = EventDispatcher(executor=ex)
        await d.submit(_make_spec())
        ex.submit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_idempotency_dedup(self):
        d = EventDispatcher(executor=_make_executor())
        spec = _make_spec(idempotency_key="idem-1")
        r1 = await d.submit(spec)
        r2 = await d.submit(spec)
        assert r1 == r2  # same run_id returned

    @pytest.mark.asyncio
    async def test_submit_records_events(self):
        d = EventDispatcher(executor=_make_executor())
        run_id = await d.submit(_make_spec())
        events = await d.get_events(run_id)
        types = [e.event_type for e in events]
        assert "created" in types or "queued" in types


class TestSubmitFailure:
    @pytest.mark.asyncio
    async def test_executor_error_marks_failed(self):
        ex = _make_executor()
        ex.submit = AsyncMock(side_effect=RuntimeError("boom"))
        d = EventDispatcher(executor=ex)
        run_id = await d.submit(_make_spec())
        run = await d.get_run(run_id)
        assert run.status == RunStatus.FAILED
        assert "boom" in run.error


# ---------------------------------------------------------------------------
# Tests: convenience wrappers
# ---------------------------------------------------------------------------


class TestConvenienceWrappers:
    @pytest.mark.asyncio
    async def test_submit_task(self):
        d = EventDispatcher(executor=_make_executor())
        run_id = await d.submit_task("email", {"to": "a@b"})
        run = await d.get_run(run_id)
        assert run.spec.kind == "task"
        assert run.spec.name == "email"

    @pytest.mark.asyncio
    async def test_submit_operation(self):
        d = EventDispatcher(executor=_make_executor())
        run_id = await d.submit_operation("ingest")
        run = await d.get_run(run_id)
        assert run.spec.kind == "operation"

    @pytest.mark.asyncio
    async def test_submit_workflow(self):
        d = EventDispatcher(executor=_make_executor())
        run_id = await d.submit_workflow("daily")
        run = await d.get_run(run_id)
        assert run.spec.kind == "workflow"

    @pytest.mark.asyncio
    async def test_submit_step(self):
        d = EventDispatcher(executor=_make_executor())
        run_id = await d.submit_step("validate", parent_run_id="parent-1")
        run = await d.get_run(run_id)
        assert run.spec.kind == "step"
        assert run.spec.parent_run_id == "parent-1"


# ---------------------------------------------------------------------------
# Tests: query
# ---------------------------------------------------------------------------


class TestQuery:
    @pytest.mark.asyncio
    async def test_get_run_missing(self):
        d = EventDispatcher(executor=_make_executor())
        assert await d.get_run("no-such") is None

    @pytest.mark.asyncio
    async def test_list_runs_empty(self):
        d = EventDispatcher(executor=_make_executor())
        assert await d.list_runs() == []

    @pytest.mark.asyncio
    async def test_list_runs_filter_kind(self):
        d = EventDispatcher(executor=_make_executor())
        await d.submit_task("a")
        await d.submit_operation("b")
        tasks = await d.list_runs(kind="task")
        assert len(tasks) == 1
        assert tasks[0].kind == "task"

    @pytest.mark.asyncio
    async def test_list_runs_filter_name(self):
        d = EventDispatcher(executor=_make_executor())
        await d.submit_task("alpha")
        await d.submit_task("beta")
        result = await d.list_runs(name="beta")
        assert len(result) == 1
        assert result[0].name == "beta"

    @pytest.mark.asyncio
    async def test_list_runs_limit_offset(self):
        d = EventDispatcher(executor=_make_executor())
        for i in range(5):
            await d.submit_task(f"t{i}")
        page = await d.list_runs(limit=2, offset=2)
        assert len(page) == 2

    @pytest.mark.asyncio
    async def test_get_events(self):
        d = EventDispatcher(executor=_make_executor())
        run_id = await d.submit_task("x")
        events = await d.get_events(run_id)
        assert len(events) > 0

    @pytest.mark.asyncio
    async def test_get_children(self):
        d = EventDispatcher(executor=_make_executor())
        p = await d.submit_workflow("parent_wf")
        c = await d.submit_step("child_step", parent_run_id=p)
        children = await d.get_children(p)
        assert any(ch.name == "child_step" for ch in children)


# ---------------------------------------------------------------------------
# Tests: control
# ---------------------------------------------------------------------------


class TestControl:
    @pytest.mark.asyncio
    async def test_cancel_success(self):
        ex = _make_executor()
        d = EventDispatcher(executor=ex)
        run_id = await d.submit_task("x")
        ok = await d.cancel(run_id)
        assert ok is True
        ex.cancel.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_cancel_nonexistent_run(self):
        d = EventDispatcher(executor=_make_executor())
        ok = await d.cancel("no-such")
        assert ok is False

    @pytest.mark.asyncio
    async def test_retry_creates_new_run(self):
        d = EventDispatcher(executor=_make_executor())
        run_id = await d.submit_task("x")
        new_id = await d.retry(run_id)
        assert new_id != run_id
        new_run = await d.get_run(new_id)
        assert new_run is not None

    @pytest.mark.asyncio
    async def test_retry_nonexistent_raises(self):
        d = EventDispatcher(executor=_make_executor())
        with pytest.raises(ValueError, match="not found"):
            await d.retry("no-such")


# ---------------------------------------------------------------------------
# Tests: lifecycle
# ---------------------------------------------------------------------------


class TestLifecycle:
    @pytest.mark.asyncio
    async def test_mark_started(self):
        d = EventDispatcher(executor=_make_executor())
        run_id = await d.submit_task("x")
        await d.mark_started(run_id)
        run = await d.get_run(run_id)
        assert run.status == RunStatus.RUNNING

    @pytest.mark.asyncio
    async def test_mark_completed(self):
        d = EventDispatcher(executor=_make_executor())
        run_id = await d.submit_task("x")
        await d.mark_started(run_id)
        await d.mark_completed(run_id, result={"ok": True})
        run = await d.get_run(run_id)
        assert run.status == RunStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_mark_failed(self):
        d = EventDispatcher(executor=_make_executor())
        run_id = await d.submit_task("x")
        await d.mark_failed(run_id, "bad stuff", "ValueError")
        run = await d.get_run(run_id)
        assert run.status == RunStatus.FAILED
        assert run.error == "bad stuff"

    @pytest.mark.asyncio
    async def test_record_progress(self):
        d = EventDispatcher(executor=_make_executor())
        run_id = await d.submit_task("x")
        await d.record_progress(run_id, 0.5, "halfway")
        events = await d.get_events(run_id)
        progress_events = [e for e in events if e.event_type == "progress"]
        assert len(progress_events) == 1


# ---------------------------------------------------------------------------
# Tests: clear
# ---------------------------------------------------------------------------


class TestClear:
    @pytest.mark.asyncio
    async def test_clear_resets_state(self):
        d = EventDispatcher(executor=_make_executor())
        await d.submit_task("x")
        d.clear()
        assert await d.list_runs() == []


# ---------------------------------------------------------------------------
# Tests: backward-compat alias
# ---------------------------------------------------------------------------


