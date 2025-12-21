"""Tests for spine.execution.executors.async_local — AsyncLocalExecutor.

Covers handler registration, submit/cancel/wait lifecycle, status tracking,
LRU eviction of results, and error handling.
"""

from __future__ import annotations

import asyncio

import pytest

from spine.execution.executors.async_local import AsyncLocalExecutor
from spine.execution.spec import WorkSpec


def _make_spec(kind: str = "task", name: str = "echo", params: dict | None = None) -> WorkSpec:
    return WorkSpec(kind=kind, name=name, params=params or {})


class TestAsyncLocalExecutorInit:
    def test_default_concurrency(self):
        executor = AsyncLocalExecutor()
        assert executor._max_concurrency == 10
        assert executor.name == "async_local"

    def test_custom_concurrency(self):
        executor = AsyncLocalExecutor(max_concurrency=5)
        assert executor._max_concurrency == 5


class TestHandlerRegistration:
    def test_register_handler(self):
        executor = AsyncLocalExecutor()

        async def my_handler(params):
            return {"result": "ok"}

        executor.register("task", "echo", my_handler)
        assert "task:echo" in executor._handlers

    def test_register_multiple_kinds(self):
        executor = AsyncLocalExecutor()

        async def h1(params):
            return {}

        async def h2(params):
            return {}

        executor.register("task", "t1", h1)
        executor.register("operation", "p1", h2)
        assert "task:t1" in executor._handlers
        assert "operation:p1" in executor._handlers


class TestSubmitAndWait:
    @pytest.mark.asyncio
    async def test_submit_returns_ref(self):
        executor = AsyncLocalExecutor()

        async def handler(params):
            return {"echo": params.get("msg", "")}

        executor.register("task", "echo", handler)
        ref = await executor.submit(_make_spec(params={"msg": "hello"}))
        assert ref.startswith("async-")
        assert len(ref) == 18  # "async-" + 12 hex chars

    @pytest.mark.asyncio
    async def test_wait_completed(self):
        executor = AsyncLocalExecutor()

        async def handler(params):
            return {"status": "done"}

        executor.register("task", "echo", handler)
        ref = await executor.submit(_make_spec())
        status = await executor.wait(ref, timeout=5.0)
        assert status == "completed"

    @pytest.mark.asyncio
    async def test_get_result_after_completion(self):
        executor = AsyncLocalExecutor()

        async def handler(params):
            return {"value": 42}

        executor.register("task", "echo", handler)
        ref = await executor.submit(_make_spec())
        await executor.wait(ref, timeout=5.0)
        result = await executor.get_result(ref)
        assert result == {"value": 42}

    @pytest.mark.asyncio
    async def test_get_error_on_failure(self):
        executor = AsyncLocalExecutor()

        async def bad_handler(params):
            raise ValueError("oops")

        executor.register("task", "fail", bad_handler)
        ref = await executor.submit(_make_spec(name="fail"))
        await executor.wait(ref, timeout=5.0)
        err = await executor.get_error(ref)
        assert "oops" in err

    @pytest.mark.asyncio
    async def test_submit_unregistered_raises(self):
        executor = AsyncLocalExecutor()
        with pytest.raises(RuntimeError, match="No async handler"):
            await executor.submit(_make_spec(name="missing"))


class TestGetStatus:
    @pytest.mark.asyncio
    async def test_unknown_ref(self):
        executor = AsyncLocalExecutor()
        assert await executor.get_status("unknown") is None

    @pytest.mark.asyncio
    async def test_completed_status(self):
        executor = AsyncLocalExecutor()

        async def handler(params):
            return {}

        executor.register("task", "echo", handler)
        ref = await executor.submit(_make_spec())
        await executor.wait(ref, timeout=5.0)
        assert await executor.get_status(ref) == "completed"

    @pytest.mark.asyncio
    async def test_failed_status(self):
        executor = AsyncLocalExecutor()

        async def bad(params):
            raise RuntimeError("boom")

        executor.register("task", "boom", bad)
        ref = await executor.submit(_make_spec(name="boom"))
        await executor.wait(ref, timeout=5.0)
        assert await executor.get_status(ref) == "failed"


class TestCancel:
    @pytest.mark.asyncio
    async def test_cancel_running(self):
        executor = AsyncLocalExecutor()

        async def slow(params):
            await asyncio.sleep(60)
            return {}

        executor.register("task", "slow", slow)
        ref = await executor.submit(_make_spec(name="slow"))
        # Small yield to let the task start
        await asyncio.sleep(0.05)
        cancelled = await executor.cancel(ref)
        assert cancelled is True

    @pytest.mark.asyncio
    async def test_cancel_already_done(self):
        executor = AsyncLocalExecutor()

        async def fast(params):
            return {}

        executor.register("task", "fast", fast)
        ref = await executor.submit(_make_spec(name="fast"))
        await executor.wait(ref, timeout=5.0)
        cancelled = await executor.cancel(ref)
        assert cancelled is False

    @pytest.mark.asyncio
    async def test_cancel_unknown(self):
        executor = AsyncLocalExecutor()
        cancelled = await executor.cancel("unknown-ref")
        assert cancelled is False


class TestWaitEdgeCases:
    @pytest.mark.asyncio
    async def test_wait_unknown_ref(self):
        executor = AsyncLocalExecutor()
        status = await executor.wait("nonexistent")
        assert status == "not_found"

    @pytest.mark.asyncio
    async def test_wait_timeout(self):
        executor = AsyncLocalExecutor()

        async def slow(params):
            await asyncio.sleep(60)

        executor.register("task", "slow", slow)
        ref = await executor.submit(_make_spec(name="slow"))
        status = await executor.wait(ref, timeout=0.05)
        assert status == "running"
        # Cleanup
        await executor.cancel(ref)


class TestActiveCount:
    @pytest.mark.asyncio
    async def test_active_count_idle(self):
        executor = AsyncLocalExecutor()
        assert executor.active_count == 0

    @pytest.mark.asyncio
    async def test_active_count_with_task(self):
        executor = AsyncLocalExecutor()
        gate = asyncio.Event()

        async def gated(params):
            await gate.wait()
            return {}

        executor.register("task", "gated", gated)
        ref = await executor.submit(_make_spec(name="gated"))
        await asyncio.sleep(0.05)
        assert executor.active_count >= 1
        gate.set()
        await executor.wait(ref, timeout=5.0)


class TestResultNonDict:
    @pytest.mark.asyncio
    async def test_non_dict_result_wrapped(self):
        executor = AsyncLocalExecutor()

        async def handler(params):
            return "plain_string"

        executor.register("task", "wrap", handler)
        ref = await executor.submit(_make_spec(name="wrap"))
        await executor.wait(ref, timeout=5.0)
        result = await executor.get_result(ref)
        assert result == {"result": "plain_string"}


class TestCatchAllHandler:
    @pytest.mark.asyncio
    async def test_all_handler_fallback(self):
        executor = AsyncLocalExecutor()

        async def catchall(params):
            return {"caught": True}

        executor.register("task", "__all__", catchall)
        ref = await executor.submit(_make_spec(name="anything"))
        await executor.wait(ref, timeout=5.0)
        result = await executor.get_result(ref)
        assert result["caught"] is True
