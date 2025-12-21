"""Tests for ``spine.orchestration.exceptions``."""

from spine.core.errors import OrchestrationError
from spine.orchestration.exceptions import (
    CycleDetectedError,
    DependencyError,
    GroupError,
    GroupNotFoundError,
    InvalidGroupSpecError,
    PlanResolutionError,
    StepNotFoundError,
)


class TestOrchestrationExceptions:
    def test_group_error_base(self):
        e = GroupError("base")
        assert isinstance(e, OrchestrationError)
        assert str(e) == "base"

    def test_group_not_found(self):
        e = GroupNotFoundError("ingest")
        assert e.group_name == "ingest"
        assert "ingest" in str(e)

    def test_step_not_found(self):
        e = StepNotFoundError("step1", "op_missing")
        assert e.step_name == "step1"
        assert e.operation_name == "op_missing"
        assert "step1" in str(e) and "op_missing" in str(e)

    def test_cycle_detected(self):
        e = CycleDetectedError(["a", "b", "c", "a"])
        assert e.cycle == ["a", "b", "c", "a"]
        assert "a -> b -> c -> a" in str(e)

    def test_plan_resolution(self):
        e = PlanResolutionError("can't resolve", group_name="g1")
        assert e.group_name == "g1"
        assert "can't resolve" in str(e)

    def test_plan_resolution_no_group(self):
        e = PlanResolutionError("failed")
        assert e.group_name is None

    def test_invalid_group_spec(self):
        e = InvalidGroupSpecError("bad spec", field="steps")
        assert e.field == "steps"
        assert "bad spec" in str(e)

    def test_invalid_group_spec_no_field(self):
        e = InvalidGroupSpecError("invalid")
        assert e.field is None

    def test_dependency_error(self):
        e = DependencyError("s1", ["dep_a", "dep_b"])
        assert e.step_name == "s1"
        assert e.missing_deps == ["dep_a", "dep_b"]
        assert "dep_a, dep_b" in str(e)
