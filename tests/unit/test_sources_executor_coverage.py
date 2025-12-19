"""Tests for sources/protocol.py, executors/local.py, and more low-coverage modules."""
from __future__ import annotations

import asyncio

import pytest

from spine.core.errors import SourceError
from spine.core.result import Err, Ok
from spine.execution.executors.local import LocalExecutor
from spine.execution.spec import WorkSpec
from spine.framework.sources.protocol import (
    BaseSource,
    SourceMetadata,
    SourceRegistry,
    SourceResult,
    SourceType,
)


# =============================================================================
# SourceMetadata
# =============================================================================


class TestSourceMetadata:
    def test_to_dict_minimal(self):
        m = SourceMetadata(source_name="test", source_type=SourceType.FILE)
        d = m.to_dict()
        assert d["source_name"] == "test"
        assert d["source_type"] == "file"
        assert "fetched_at" in d
        assert "content_changed" in d

    def test_to_dict_full(self):
        m = SourceMetadata(
            source_name="test",
            source_type=SourceType.HTTP,
            duration_ms=500,
            content_hash="abc",
            etag="etag1",
            last_modified="2026-01-01",
            bytes_fetched=1024,
            row_count=100,
            url="https://example.com",
            path="/data/file.csv",
            query="SELECT 1",
            params={"date": "2026-01-01"},
        )
        d = m.to_dict()
        assert d["duration_ms"] == 500
        assert d["content_hash"] == "abc"
        assert d["url"] == "https://example.com"
        assert d["params"] == {"date": "2026-01-01"}


# =============================================================================
# SourceResult
# =============================================================================


class TestSourceResult:
    def test_ok(self):
        m = SourceMetadata(source_name="t", source_type=SourceType.FILE)
        r = SourceResult.ok(data=[{"a": 1}], metadata=m)
        assert r.success
        assert r.data == [{"a": 1}]
        assert r.metadata.row_count == 1

    def test_ok_raw(self):
        m = SourceMetadata(source_name="t", source_type=SourceType.HTTP)
        r = SourceResult.ok_raw(raw_data=b"hello", metadata=m)
        assert r.success
        assert r.raw_data == b"hello"
        assert r.metadata.bytes_fetched == 5

    def test_fail(self):
        err = SourceError("bad fetch")
        r = SourceResult.fail(error=err)
        assert not r.success
        assert r.error is err

    def test_to_result_ok(self):
        m = SourceMetadata(source_name="t", source_type=SourceType.FILE)
        r = SourceResult.ok(data=[{"a": 1}], metadata=m)
        result = r.to_result()
        assert isinstance(result, Ok)
        assert result.value == [{"a": 1}]

    def test_to_result_err(self):
        err = SourceError("bad")
        r = SourceResult.fail(error=err)
        result = r.to_result()
        assert isinstance(result, Err)

    def test_to_result_no_data_no_error(self):
        r = SourceResult(success=True)  # No data, no error
        result = r.to_result()
        assert isinstance(result, Err)

    def test_len(self):
        m = SourceMetadata(source_name="t", source_type=SourceType.FILE)
        r = SourceResult.ok(data=[{"a": 1}, {"a": 2}], metadata=m)
        assert len(r) == 2

    def test_len_no_data(self):
        r = SourceResult(success=True)
        assert len(r) == 0


# =============================================================================
# BaseSource
# =============================================================================


class TestBaseSource:
    def test_properties(self):
        class DummySource(BaseSource):
            def fetch(self, params=None):
                m = self._create_metadata(params)
                return SourceResult.ok(data=[], metadata=m)

        src = DummySource("test_src", SourceType.FILE, domain="test_domain", config={"k": "v"})
        assert src.name == "test_src"
        assert src.source_type == SourceType.FILE
        assert src.domain == "test_domain"

    def test_create_metadata(self):
        class DummySource(BaseSource):
            def fetch(self, params=None):
                return SourceResult.ok(data=[], metadata=self._create_metadata(params))

        src = DummySource("test", SourceType.FILE)
        result = src.fetch(params={"date": "2026-01-01"})
        assert result.metadata.source_name == "test"
        assert result.metadata.params == {"date": "2026-01-01"}

    def test_wrap_error_plain(self):
        class DummySource(BaseSource):
            def fetch(self, params=None):
                return SourceResult.fail(error=self._wrap_error(ValueError("bad")))

        src = DummySource("test", SourceType.FILE)
        result = src.fetch()
        assert isinstance(result.error, SourceError)

    def test_wrap_error_already_source_error(self):
        class DummySource(BaseSource):
            def fetch(self, params=None):
                original = SourceError("original")
                return SourceResult.fail(error=self._wrap_error(original))

        src = DummySource("test", SourceType.FILE)
        result = src.fetch()
        assert result.error.message == "original"


# =============================================================================
# SourceRegistry
# =============================================================================


class TestSourceRegistry:
    def test_register_and_get(self):
        class DummySource(BaseSource):
            def fetch(self, params=None):
                return SourceResult.ok(data=[], metadata=self._create_metadata())

        reg = SourceRegistry()
        src = DummySource("my_source", SourceType.FILE)
        reg.register(src)
        assert reg.get("my_source") is src

    def test_get_missing_raises(self):
        reg = SourceRegistry()
        with pytest.raises(SourceError, match="Source not found"):
            reg.get("missing")

    def test_list_sources(self):
        class DummySource(BaseSource):
            def fetch(self, params=None):
                return SourceResult.ok(data=[], metadata=self._create_metadata())

        reg = SourceRegistry()
        reg.register(DummySource("b", SourceType.FILE))
        reg.register(DummySource("a", SourceType.HTTP))
        assert reg.list_sources() == ["a", "b"]

    def test_list_by_type(self):
        class DummySource(BaseSource):
            def fetch(self, params=None):
                return SourceResult.ok(data=[], metadata=self._create_metadata())

        reg = SourceRegistry()
        reg.register(DummySource("f1", SourceType.FILE))
        reg.register(DummySource("h1", SourceType.HTTP))
        assert reg.list_by_type(SourceType.FILE) == ["f1"]

    def test_register_factory(self):
        class DummySource(BaseSource):
            def fetch(self, params=None):
                return SourceResult.ok(data=[], metadata=self._create_metadata())

        reg = SourceRegistry()
        reg.register_factory("lazy_src", DummySource, {"source_type": SourceType.FILE})
        assert "lazy_src" in reg.list_sources()
        src = reg.get("lazy_src")
        assert src.name == "lazy_src"


# =============================================================================
# LocalExecutor
# =============================================================================


class TestLocalExecutor:
    """Test local executor (async)."""

    def test_register_and_submit(self):
        executor = LocalExecutor(max_workers=2)
        executor.register_handler("task", "echo", lambda params: params)

        async def run():
            spec = WorkSpec(kind="task", name="echo", params={"data": "test"})
            ref = await executor.submit(spec)
            import time
            time.sleep(0.1)
            status = await executor.get_status(ref)
            result = await executor.get_result(ref)
            return ref, status, result

        ref, status, result = asyncio.run(run())
        assert ref.startswith("local-")
        assert status == "completed"
        assert result == {"data": "test"}
        executor.shutdown()

    def test_submit_unknown_handler_raises(self):
        executor = LocalExecutor()

        async def run():
            spec = WorkSpec(kind="task", name="missing", params={})
            return await executor.submit(spec)

        with pytest.raises(ValueError, match="No handler"):
            asyncio.run(run())
        executor.shutdown()

    def test_get_status_unknown_ref(self):
        executor = LocalExecutor()

        async def run():
            return await executor.get_status("unknown")

        assert asyncio.run(run()) is None
        executor.shutdown()

    def test_get_result_unknown_ref(self):
        executor = LocalExecutor()

        async def run():
            return await executor.get_result("unknown")

        assert asyncio.run(run()) is None
        executor.shutdown()

    def test_cancel(self):
        executor = LocalExecutor()

        async def run():
            return await executor.cancel("nonexistent")

        assert asyncio.run(run()) is False
        executor.shutdown()

    def test_context_manager(self):
        with LocalExecutor() as executor:
            executor.register_handler("task", "noop", lambda p: None)

    def test_failed_handler(self):
        def bad_handler(params):
            raise RuntimeError("handler error")

        executor = LocalExecutor()
        executor.register_handler("task", "bad", bad_handler)

        async def run():
            spec = WorkSpec(kind="task", name="bad", params={})
            ref = await executor.submit(spec)
            import time
            time.sleep(0.1)
            status = await executor.get_status(ref)
            result = await executor.get_result(ref)
            return status, result

        status, result = asyncio.run(run())
        assert status == "failed"
        assert result is None
        executor.shutdown()
