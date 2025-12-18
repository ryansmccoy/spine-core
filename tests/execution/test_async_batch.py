"""Tests for AsyncBatchExecutor — asyncio-based parallel work fan-out."""

from __future__ import annotations

import asyncio
import pytest

from spine.execution.async_batch import (
    AsyncBatchExecutor,
    AsyncBatchItem,
    AsyncBatchResult,
)


# ── Helpers ──────────────────────────────────────────────────────────────


async def _echo(params: dict) -> dict:
    """Handler that echoes params."""
    return params


async def _slow(params: dict) -> dict:
    """Handler that sleeps briefly."""
    await asyncio.sleep(params.get("delay", 0.01))
    return {"done": True}


async def _failing(params: dict) -> dict:
    """Handler that always raises."""
    raise ValueError(f"boom: {params.get('msg', 'fail')}")


# ── AsyncBatchItem ───────────────────────────────────────────────────────


class TestAsyncBatchItem:
    """Tests for the AsyncBatchItem dataclass."""

    def test_defaults(self):
        item = AsyncBatchItem(name="x", handler=_echo)
        assert item.name == "x"
        assert item.status == "pending"
        assert item.result is None
        assert item.error is None
        assert item.started_at is None
        assert item.completed_at is None

    def test_duration_none_when_incomplete(self):
        item = AsyncBatchItem(name="x", handler=_echo)
        assert item.duration_seconds is None

    def test_duration_computed(self):
        from datetime import UTC, datetime, timedelta

        t0 = datetime.now(UTC)
        t1 = t0 + timedelta(seconds=2.5)
        item = AsyncBatchItem(
            name="x", handler=_echo, started_at=t0, completed_at=t1,
        )
        assert item.duration_seconds == pytest.approx(2.5)


# ── AsyncBatchResult ─────────────────────────────────────────────────────


class TestAsyncBatchResult:
    """Tests for AsyncBatchResult aggregate metrics."""

    def _make_result(self, statuses: list[str]) -> AsyncBatchResult:
        from datetime import UTC, datetime

        items = [
            AsyncBatchItem(name=f"i{i}", handler=_echo, status=s)
            for i, s in enumerate(statuses)
        ]
        now = datetime.now(UTC)
        return AsyncBatchResult(
            batch_id="b1", items=items, started_at=now, completed_at=now,
        )

    def test_counts(self):
        r = self._make_result(["completed", "completed", "failed", "pending"])
        assert r.succeeded == 2
        assert r.failed == 1
        assert r.total == 4

    def test_to_dict_keys(self):
        r = self._make_result(["completed"])
        d = r.to_dict()
        assert "batch_id" in d
        assert "total" in d
        assert "succeeded" in d
        assert "items" in d
        assert isinstance(d["items"], list)


# ── AsyncBatchExecutor ───────────────────────────────────────────────────


class TestAsyncBatchExecutor:
    """Tests for the executor itself."""

    def test_add_returns_self(self):
        batch = AsyncBatchExecutor(max_concurrency=5)
        ret = batch.add("a", _echo, {"k": "v"})
        assert ret is batch

    def test_item_count(self):
        batch = AsyncBatchExecutor()
        assert batch.item_count == 0
        batch.add("a", _echo)
        batch.add("b", _echo)
        assert batch.item_count == 2

    def test_batch_id_is_uuid(self):
        import uuid

        batch = AsyncBatchExecutor()
        uuid.UUID(batch.batch_id)  # should not raise

    @pytest.mark.asyncio
    async def test_run_all_success(self):
        batch = AsyncBatchExecutor(max_concurrency=5)
        batch.add("a", _echo, {"x": 1})
        batch.add("b", _echo, {"x": 2})
        result = await batch.run_all()
        assert result.succeeded == 2
        assert result.failed == 0
        assert result.total == 2

    @pytest.mark.asyncio
    async def test_run_all_with_failure(self):
        batch = AsyncBatchExecutor()
        batch.add("ok", _echo, {"x": 1})
        batch.add("bad", _failing, {"msg": "test"})
        result = await batch.run_all()
        assert result.succeeded == 1
        assert result.failed == 1

    @pytest.mark.asyncio
    async def test_concurrency_bounded(self):
        """Verify semaphore bounds concurrency."""
        active = 0
        max_active = 0
        lock = asyncio.Lock()

        async def _track(params):
            nonlocal active, max_active
            async with lock:
                active += 1
                max_active = max(max_active, active)
            await asyncio.sleep(0.02)
            async with lock:
                active -= 1
            return {"ok": True}

        batch = AsyncBatchExecutor(max_concurrency=2)
        for i in range(6):
            batch.add(f"t{i}", _track)
        await batch.run_all()
        assert max_active <= 2

    @pytest.mark.asyncio
    async def test_result_contains_timestamps(self):
        batch = AsyncBatchExecutor()
        batch.add("x", _echo, {"v": 1})
        result = await batch.run_all()
        assert result.started_at is not None
        assert result.completed_at is not None
        assert result.duration_seconds >= 0

    @pytest.mark.asyncio
    async def test_item_result_is_dict(self):
        """Handler returning a non-dict gets wrapped."""

        async def _return_str(params):
            return "hello"

        batch = AsyncBatchExecutor()
        batch.add("x", _return_str)
        result = await batch.run_all()
        item = result.items[0]
        assert isinstance(item.result, dict)
        assert item.result["result"] == "hello"

    @pytest.mark.asyncio
    async def test_failed_item_has_error(self):
        batch = AsyncBatchExecutor()
        batch.add("bad", _failing, {"msg": "oops"})
        result = await batch.run_all()
        item = result.items[0]
        assert item.status == "failed"
        assert "oops" in item.error
