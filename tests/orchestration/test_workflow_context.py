"""Tests for WorkflowContext — immutability, factories, serialization.

Covers create/from_dict factories, with_output/with_params/with_metadata
immutability, property accessors, dry_run handling, and round-trip
serialization via to_dict / from_dict.
"""

from __future__ import annotations

import pytest

from spine.orchestration.workflow_context import WorkflowContext


# ---------------------------------------------------------------------------
# Factory: create
# ---------------------------------------------------------------------------


class TestWorkflowContextCreate:
    def test_minimal(self):
        ctx = WorkflowContext.create("my.workflow")
        assert ctx.workflow_name == "my.workflow"
        assert ctx.params == {}
        assert ctx.outputs == {}
        assert ctx.run_id  # non-empty UUID

    def test_with_params(self):
        ctx = WorkflowContext.create("wf", params={"tier": "NMS"})
        assert ctx.params["tier"] == "NMS"

    def test_with_partition(self):
        ctx = WorkflowContext.create("wf", partition={"date": "2025-01-01"})
        assert ctx.partition["date"] == "2025-01-01"

    def test_with_batch_id(self):
        ctx = WorkflowContext.create("wf", batch_id="batch-42")
        assert ctx.batch_id == "batch-42"

    def test_with_run_id(self):
        ctx = WorkflowContext.create("wf", run_id="custom-id")
        assert ctx.run_id == "custom-id"

    def test_dry_run(self):
        ctx = WorkflowContext.create("wf", dry_run=True)
        assert ctx.is_dry_run is True
        assert ctx.metadata["dry_run"] is True

    def test_not_dry_run(self):
        ctx = WorkflowContext.create("wf")
        assert ctx.is_dry_run is False


# ---------------------------------------------------------------------------
# Accessors
# ---------------------------------------------------------------------------


class TestAccessors:
    def test_get_param(self):
        ctx = WorkflowContext.create("wf", params={"k": "v"})
        assert ctx.get_param("k") == "v"
        assert ctx.get_param("missing") is None
        assert ctx.get_param("missing", 42) == 42

    def test_get_output_full(self):
        ctx = WorkflowContext(outputs={"step1": {"count": 10}})
        assert ctx.get_output("step1") == {"count": 10}

    def test_get_output_key(self):
        ctx = WorkflowContext(outputs={"step1": {"count": 10, "ok": True}})
        assert ctx.get_output("step1", "count") == 10
        assert ctx.get_output("step1", "missing", -1) == -1

    def test_get_output_missing_step(self):
        ctx = WorkflowContext()
        assert ctx.get_output("nope") is None
        assert ctx.get_output("nope", default=99) == 99

    def test_has_output(self):
        ctx = WorkflowContext(outputs={"step1": {}})
        assert ctx.has_output("step1") is True
        assert ctx.has_output("step2") is False

    def test_execution_id(self):
        ctx = WorkflowContext.create("wf")
        assert ctx.execution_id  # non-empty


# ---------------------------------------------------------------------------
# Immutable mutation
# ---------------------------------------------------------------------------


class TestImmutability:
    def test_with_output_returns_new(self):
        ctx = WorkflowContext.create("wf")
        ctx2 = ctx.with_output("step1", {"rows": 100})
        assert ctx2 is not ctx
        assert ctx2.outputs["step1"]["rows"] == 100
        assert "step1" not in ctx.outputs  # original unchanged

    def test_with_params_returns_new(self):
        ctx = WorkflowContext.create("wf", params={"a": 1})
        ctx2 = ctx.with_params({"b": 2})
        assert ctx2 is not ctx
        assert ctx2.params["b"] == 2
        assert ctx2.params["a"] == 1  # existing preserved
        assert "b" not in ctx.params  # original unchanged

    def test_with_params_overwrites(self):
        ctx = WorkflowContext.create("wf", params={"a": 1})
        ctx2 = ctx.with_params({"a": 99})
        assert ctx2.params["a"] == 99
        assert ctx.params["a"] == 1

    def test_with_metadata_returns_new(self):
        ctx = WorkflowContext.create("wf")
        ctx2 = ctx.with_metadata({"source": "test"})
        assert ctx2 is not ctx
        assert ctx2.metadata["source"] == "test"

    def test_chained_mutations(self):
        ctx = (
            WorkflowContext.create("wf")
            .with_output("s1", {"a": 1})
            .with_output("s2", {"b": 2})
            .with_params({"done": True})
        )
        assert ctx.has_output("s1")
        assert ctx.has_output("s2")
        assert ctx.params["done"] is True

    def test_deep_copy_independence(self):
        """Mutating context outputs after copy doesn't affect original."""
        ctx = WorkflowContext.create("wf")
        ctx2 = ctx.with_output("step", {"rows": [1, 2, 3]})
        ctx3 = ctx2.with_output("step2", {"extra": True})
        # Original ctx2 is unchanged by ctx3 creation
        assert "step2" not in ctx2.outputs
        assert ctx3.outputs["step"]["rows"] == [1, 2, 3]


# ---------------------------------------------------------------------------
# Serialization round-trip
# ---------------------------------------------------------------------------


class TestSerialization:
    def test_to_dict_fields(self):
        ctx = WorkflowContext.create("wf", params={"tier": "OTC"}, partition={"date": "2025-01-01"})
        d = ctx.to_dict()
        assert d["workflow_name"] == "wf"
        assert d["params"]["tier"] == "OTC"
        assert d["partition"]["date"] == "2025-01-01"
        assert "run_id" in d
        assert "execution" in d
        assert "started_at" in d

    def test_roundtrip(self):
        ctx = WorkflowContext.create("wf", params={"x": 42}, batch_id="b1")
        ctx = ctx.with_output("step1", {"count": 100})
        d = ctx.to_dict()
        ctx2 = WorkflowContext.from_dict(d)
        assert ctx2.workflow_name == "wf"
        assert ctx2.params["x"] == 42
        assert ctx2.outputs["step1"]["count"] == 100
        assert ctx2.run_id == ctx.run_id

    def test_from_dict_minimal(self):
        ctx = WorkflowContext.from_dict({})
        assert ctx.workflow_name == ""
        assert ctx.params == {}

    def test_from_dict_with_started_at_string(self):
        ctx = WorkflowContext.from_dict({"started_at": "2025-01-01T00:00:00+00:00"})
        assert ctx.started_at.year == 2025


# ---------------------------------------------------------------------------
# Repr
# ---------------------------------------------------------------------------


class TestRepr:
    def test_repr(self):
        ctx = WorkflowContext.create("my.wf")
        ctx = ctx.with_output("step1", {})
        r = repr(ctx)
        assert "my.wf" in r
        assert "step1" in r
