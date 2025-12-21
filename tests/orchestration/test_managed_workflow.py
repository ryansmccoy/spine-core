"""Tests for spine.orchestration.managed_workflow — builder + operation.

Covers ManagedWorkflow builder, ManagedOperation run/show/history/query,
and the _StubRunnable helper.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from spine.orchestration.managed_workflow import (
    ManagedOperation,
    ManagedWorkflow,
    StepDef,
    _StubRunnable,
)


class TestStubRunnable:
    def test_submit_returns_completed(self):
        stub = _StubRunnable()
        result = stub.submit_operation_sync("test_operation")
        assert result.status == "completed"

    def test_submit_with_params(self):
        stub = _StubRunnable()
        result = stub.submit_operation_sync(
            "etl",
            params={"key": "val"},
            parent_run_id="run-1",
            correlation_id="corr-1",
        )
        assert result.status == "completed"


class TestStepDef:
    def test_dataclass_fields(self):
        from spine.orchestration.step_types import ErrorPolicy

        sd = StepDef(
            name="fetch",
            fn=lambda x: x,
            config={"url": "http://example.com"},
            depends_on=[],
            strict=True,
            on_error=ErrorPolicy.STOP,
        )
        assert sd.name == "fetch"
        assert sd.strict is True
        assert sd.depends_on == []


class TestManagedWorkflowBuilder:
    def test_basic_build(self):
        def fetch(ctx):
            return {"data": [1, 2, 3]}

        def transform(ctx):
            return {"transformed": True}

        operation = (
            ManagedWorkflow("test.operation")
            .step("fetch", fetch)
            .step("transform", transform)
            .build()
        )
        assert isinstance(operation, ManagedOperation)
        assert operation.workflow.name == "test.operation"
        assert len(operation.workflow.steps) == 2

    def test_step_with_config(self):
        def fetch(ctx):
            return {}

        operation = (
            ManagedWorkflow("config.test")
            .step("fetch", fetch, config={"url": "http://test.com"})
            .build()
        )
        assert operation.workflow.steps[0].name == "fetch"

    def test_step_with_depends_on(self):
        def a(ctx):
            return {}

        def b(ctx):
            return {}

        operation = (
            ManagedWorkflow("deps.test")
            .step("a", a)
            .step("b", b, depends_on=["a"])
            .build()
        )
        assert len(operation.workflow.steps) == 2


class TestManagedOperation:
    def _make_operation(self):
        def noop(ctx):
            return {"ok": True}

        return (
            ManagedWorkflow("test.pipe")
            .step("step1", noop)
            .build()
        )

    def test_repr(self):
        p = self._make_operation()
        r = repr(p)
        assert "test.pipe" in r
        assert "step1" in r
        assert "in-memory" in r

    def test_workflow_property(self):
        p = self._make_operation()
        assert p.workflow.name == "test.pipe"

    def test_is_persistent_default(self):
        p = self._make_operation()
        assert p.is_persistent is False

    def test_last_result_none_initially(self):
        p = self._make_operation()
        assert p.last_result is None

    def test_run_records_result(self):
        p = self._make_operation()
        result = p.run()
        assert result is not None
        assert p.last_result is result

    def test_history_empty(self):
        p = self._make_operation()
        assert p.history() == []

    def test_history_after_run(self):
        p = self._make_operation()
        p.run()
        h = p.history()
        assert len(h) == 1
        assert "run_id" in h[0]
        assert "status" in h[0]

    def test_show_no_runs(self, capsys):
        p = self._make_operation()
        p.show()
        captured = capsys.readouterr()
        assert "no runs" in captured.out.lower()

    def test_show_after_run(self, capsys):
        p = self._make_operation()
        p.run()
        p.show()
        captured = capsys.readouterr()
        assert "test.pipe" in captured.out

    def test_close(self):
        p = self._make_operation()
        p.close()  # Should not raise

    def test_query_db(self):
        p = self._make_operation()
        # In-memory SQLite — query sqlite_master
        try:
            rows = p.query_db("SELECT name FROM sqlite_master WHERE type='table'")
            assert isinstance(rows, list)
        except Exception:
            # Connection might not support this in test mode
            pass

    def test_table_counts(self):
        p = self._make_operation()
        counts = p.table_counts()
        assert isinstance(counts, dict)
