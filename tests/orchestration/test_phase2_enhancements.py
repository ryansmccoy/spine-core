"""Tests for Phase 2 workflow enhancements.

Covers:
- Step.depends_on field
- Workflow execution_policy, cycle detection, topological ordering
- Parallel execution via WorkflowRunner
- Workflow registry (register/get/list/clear)
- Workflow YAML parsing (WorkflowSpec)
- Workflow executor (execution bridge)
"""

import pytest

from spine.orchestration import (
    Step,
    StepResult,
    Workflow,
    WorkflowRunner,
    WorkflowStatus,
)
from spine.orchestration.workflow import (
    ExecutionMode,
    FailurePolicy,
    WorkflowExecutionPolicy,
)


# ===========================================================================
# Step.depends_on
# ===========================================================================


class TestStepDependsOn:
    """Step depends_on field."""

    def test_default_empty(self):
        step = Step.operation("a", "p1")
        assert step.depends_on == ()

    def test_operation_with_depends_on(self):
        step = Step.operation("b", "p2", depends_on=("a",))
        assert step.depends_on == ("a",)

    def test_lambda_with_depends_on(self):
        step = Step.lambda_("v", lambda ctx, cfg: StepResult.ok(), depends_on=("ingest",))
        assert step.depends_on == ("ingest",)

    def test_depends_on_serialized(self):
        step = Step.operation("b", "p1", depends_on=("a",))
        d = step.to_dict()
        assert d["depends_on"] == ["a"]

    def test_depends_on_empty_omitted_from_dict(self):
        step = Step.operation("a", "p1")
        d = step.to_dict()
        # Empty depends_on is still present but empty
        assert d.get("depends_on", []) == []


# ===========================================================================
# Workflow execution_policy + dependency validation
# ===========================================================================


class TestWorkflowExecutionPolicy:
    """Workflow execution_policy and dependency helpers."""

    def test_default_policy(self):
        wf = Workflow(name="t", steps=[Step.operation("a", "p1")])
        assert wf.execution_policy.mode == ExecutionMode.SEQUENTIAL
        assert wf.execution_policy.max_concurrency == 4
        assert wf.execution_policy.on_failure == FailurePolicy.STOP

    def test_custom_policy(self):
        policy = WorkflowExecutionPolicy(
            mode=ExecutionMode.PARALLEL,
            max_concurrency=8,
            timeout_seconds=300,
            on_failure=FailurePolicy.CONTINUE,
        )
        wf = Workflow(name="t", steps=[Step.operation("a", "p1")], execution_policy=policy)
        assert wf.execution_policy.mode == ExecutionMode.PARALLEL
        assert wf.execution_policy.max_concurrency == 8
        assert wf.execution_policy.timeout_seconds == 300

    def test_has_dependencies_false(self):
        wf = Workflow(
            name="t",
            steps=[Step.operation("a", "p1"), Step.operation("b", "p2")],
        )
        assert wf.has_dependencies() is False

    def test_has_dependencies_true(self):
        wf = Workflow(
            name="t",
            steps=[
                Step.operation("a", "p1"),
                Step.operation("b", "p2", depends_on=("a",)),
            ],
        )
        assert wf.has_dependencies() is True

    def test_dependency_graph(self):
        wf = Workflow(
            name="t",
            steps=[
                Step.operation("a", "p1"),
                Step.operation("b", "p2", depends_on=("a",)),
                Step.operation("c", "p3", depends_on=("a", "b")),
            ],
        )
        graph = wf.dependency_graph()
        # Graph is dep -> dependents (outgoing edges)
        assert graph == {"a": ["b", "c"], "b": ["c"]}

    def test_topological_order_linear(self):
        wf = Workflow(
            name="t",
            steps=[
                Step.operation("a", "p1"),
                Step.operation("b", "p2", depends_on=("a",)),
                Step.operation("c", "p3", depends_on=("b",)),
            ],
        )
        order = wf.topological_order()
        assert order.index("a") < order.index("b") < order.index("c")

    def test_topological_order_diamond(self):
        wf = Workflow(
            name="t",
            steps=[
                Step.operation("a", "p1"),
                Step.operation("b", "p2", depends_on=("a",)),
                Step.operation("c", "p3", depends_on=("a",)),
                Step.operation("d", "p4", depends_on=("b", "c")),
            ],
        )
        order = wf.topological_order()
        assert order.index("a") < order.index("b")
        assert order.index("a") < order.index("c")
        assert order.index("b") < order.index("d")
        assert order.index("c") < order.index("d")

    def test_cycle_detection(self):
        """Cycle in depends_on raises ValueError."""
        with pytest.raises(ValueError, match="[Cc]ycle"):
            Workflow(
                name="t",
                steps=[
                    Step.operation("a", "p1", depends_on=("b",)),
                    Step.operation("b", "p2", depends_on=("a",)),
                ],
            )

    def test_unknown_dependency_rejected(self):
        """Dependency on nonexistent step raises ValueError."""
        with pytest.raises(ValueError, match="unknown"):
            Workflow(
                name="t",
                steps=[
                    Step.operation("a", "p1", depends_on=("nonexistent",)),
                ],
            )

    def test_to_dict_includes_policy(self):
        policy = WorkflowExecutionPolicy(
            mode=ExecutionMode.PARALLEL,
            max_concurrency=2,
            on_failure=FailurePolicy.CONTINUE,
        )
        wf = Workflow(
            name="t",
            steps=[Step.operation("a", "p1")],
            execution_policy=policy,
        )
        d = wf.to_dict()
        assert "execution_policy" in d
        assert d["execution_policy"]["mode"] == "parallel"
        assert d["execution_policy"]["max_concurrency"] == 2

    def test_from_dict_roundtrip(self):
        policy = WorkflowExecutionPolicy(
            mode=ExecutionMode.PARALLEL,
            max_concurrency=2,
            timeout_seconds=60,
            on_failure=FailurePolicy.CONTINUE,
        )
        wf = Workflow(
            name="t",
            steps=[
                Step.operation("a", "p1"),
                Step.operation("b", "p2", depends_on=("a",)),
            ],
            execution_policy=policy,
        )
        d = wf.to_dict()
        wf2 = Workflow.from_dict(d)
        assert wf2.name == "t"
        assert len(wf2.steps) == 2
        assert wf2.steps[1].depends_on == ("a",)
        assert wf2.execution_policy.mode == ExecutionMode.PARALLEL
        assert wf2.execution_policy.max_concurrency == 2
        assert wf2.execution_policy.timeout_seconds == 60
        assert wf2.execution_policy.on_failure == FailurePolicy.CONTINUE


# ===========================================================================
# Parallel execution
# ===========================================================================


class TestParallelExecution:
    """WorkflowRunner parallel execution mode."""

    @staticmethod
    def _make_step_fn(name: str, output: dict | None = None):
        """Create a lambda handler that succeeds."""
        return lambda ctx, cfg: StepResult.ok(output=output or {"step": name})

    def test_parallel_diamond(self, noop_runnable):
        """Parallel execution of a diamond DAG."""
        wf = Workflow(
            name="diamond",
            steps=[
                Step.lambda_("a", self._make_step_fn("a")),
                Step.lambda_("b", self._make_step_fn("b"), depends_on=("a",)),
                Step.lambda_("c", self._make_step_fn("c"), depends_on=("a",)),
                Step.lambda_("d", self._make_step_fn("d"), depends_on=("b", "c")),
            ],
            execution_policy=WorkflowExecutionPolicy(
                mode=ExecutionMode.PARALLEL,
                max_concurrency=4,
            ),
        )
        runner = WorkflowRunner(runnable=noop_runnable)
        result = runner.execute(wf)
        assert result.status == WorkflowStatus.COMPLETED
        assert set(result.completed_steps) == {"a", "b", "c", "d"}

    def test_parallel_linear_chain(self, noop_runnable):
        """Linear chain degenerates to sequential in parallel mode."""
        wf = Workflow(
            name="linear",
            steps=[
                Step.lambda_("a", self._make_step_fn("a")),
                Step.lambda_("b", self._make_step_fn("b"), depends_on=("a",)),
                Step.lambda_("c", self._make_step_fn("c"), depends_on=("b",)),
            ],
            execution_policy=WorkflowExecutionPolicy(mode=ExecutionMode.PARALLEL),
        )
        runner = WorkflowRunner(runnable=noop_runnable)
        result = runner.execute(wf)
        assert result.status == WorkflowStatus.COMPLETED
        assert result.completed_steps == ["a", "b", "c"]

    def test_parallel_stop_on_failure(self, noop_runnable):
        """Parallel mode stops on first failure with STOP policy."""

        def fail_fn(ctx, cfg):
            return StepResult.fail("intentional failure")

        wf = Workflow(
            name="fail_test",
            steps=[
                Step.lambda_("a", self._make_step_fn("a")),
                Step.lambda_("b", fail_fn, depends_on=("a",)),
                Step.lambda_("c", self._make_step_fn("c"), depends_on=("b",)),
            ],
            execution_policy=WorkflowExecutionPolicy(
                mode=ExecutionMode.PARALLEL,
                on_failure=FailurePolicy.STOP,
            ),
        )
        runner = WorkflowRunner(runnable=noop_runnable)
        result = runner.execute(wf)
        assert result.status == WorkflowStatus.FAILED
        assert "b" in result.failed_steps

    def test_parallel_continue_on_failure(self, noop_runnable):
        """Parallel mode continues past failures with CONTINUE policy."""

        def fail_fn(ctx, cfg):
            return StepResult.fail("intentional failure")

        wf = Workflow(
            name="continue_test",
            steps=[
                Step.lambda_("a", self._make_step_fn("a")),
                Step.lambda_("b", fail_fn, depends_on=("a",)),
                Step.lambda_("c", self._make_step_fn("c"), depends_on=("a",)),
            ],
            execution_policy=WorkflowExecutionPolicy(
                mode=ExecutionMode.PARALLEL,
                on_failure=FailurePolicy.CONTINUE,
            ),
        )
        runner = WorkflowRunner(runnable=noop_runnable)
        result = runner.execute(wf)
        # c should still succeed since it depends only on a
        assert "a" in result.completed_steps
        assert "c" in result.completed_steps
        assert "b" in result.failed_steps

    def test_sequential_mode_unchanged(self, noop_runnable):
        """SEQUENTIAL mode still works as before (no parallel path)."""
        wf = Workflow(
            name="seq_test",
            steps=[
                Step.lambda_("a", self._make_step_fn("a")),
                Step.lambda_("b", self._make_step_fn("b")),
            ],
            execution_policy=WorkflowExecutionPolicy(mode=ExecutionMode.SEQUENTIAL),
        )
        runner = WorkflowRunner(runnable=noop_runnable)
        result = runner.execute(wf)
        assert result.status == WorkflowStatus.COMPLETED


# ===========================================================================
# Workflow Registry
# ===========================================================================


class TestWorkflowRegistry:
    """Workflow registry operations."""

    def setup_method(self):
        from spine.orchestration.workflow_registry import clear_workflow_registry

        clear_workflow_registry()

    def teardown_method(self):
        from spine.orchestration.workflow_registry import clear_workflow_registry

        clear_workflow_registry()

    def test_register_and_get(self):
        from spine.orchestration.workflow_registry import get_workflow, register_workflow

        wf = Workflow(name="test.wf", steps=[Step.operation("a", "p1")])
        register_workflow(wf)
        assert get_workflow("test.wf") is wf

    def test_register_duplicate_raises(self):
        from spine.orchestration.workflow_registry import register_workflow

        wf = Workflow(name="dup", steps=[Step.operation("a", "p1")])
        register_workflow(wf)
        with pytest.raises(ValueError, match="already registered"):
            register_workflow(wf)

    def test_get_missing_raises(self):
        from spine.orchestration.workflow_registry import WorkflowNotFoundError, get_workflow

        with pytest.raises(WorkflowNotFoundError):
            get_workflow("nonexistent")

    def test_list_workflows(self):
        from spine.orchestration.workflow_registry import list_workflows, register_workflow

        register_workflow(Workflow(name="b.wf", steps=[Step.operation("a", "p1")]))
        register_workflow(Workflow(name="a.wf", steps=[Step.operation("a", "p1")]))
        assert list_workflows() == ["a.wf", "b.wf"]

    def test_list_workflows_by_domain(self):
        from spine.orchestration.workflow_registry import list_workflows, register_workflow

        register_workflow(Workflow(name="ingest.wf", steps=[Step.operation("a", "p1")], domain="ingest"))
        register_workflow(Workflow(name="export.wf", steps=[Step.operation("a", "p1")], domain="export"))
        assert list_workflows(domain="ingest") == ["ingest.wf"]

    def test_workflow_exists(self):
        from spine.orchestration.workflow_registry import register_workflow, workflow_exists

        assert workflow_exists("x") is False
        register_workflow(Workflow(name="x", steps=[Step.operation("a", "p1")]))
        assert workflow_exists("x") is True

    def test_clear_registry(self):
        from spine.orchestration.workflow_registry import (
            clear_workflow_registry,
            list_workflows,
            register_workflow,
        )

        register_workflow(Workflow(name="x", steps=[Step.operation("a", "p1")]))
        clear_workflow_registry()
        assert list_workflows() == []

    def test_decorator_factory(self):
        from spine.orchestration.workflow_registry import get_workflow, register_workflow

        @register_workflow
        def my_factory():
            return Workflow(name="factory.wf", steps=[Step.operation("a", "p1")])

        assert get_workflow("factory.wf").name == "factory.wf"

    def test_registry_stats(self):
        from spine.orchestration.workflow_registry import (
            get_workflow_registry_stats,
            register_workflow,
        )

        register_workflow(Workflow(name="a", steps=[Step.operation("x", "p1")], domain="d1"))
        register_workflow(Workflow(name="b", steps=[Step.operation("x", "p1")], domain="d1"))
        register_workflow(Workflow(name="c", steps=[Step.operation("x", "p1")], domain="d2"))
        stats = get_workflow_registry_stats()
        assert stats["total_workflows"] == 3
        assert stats["workflows_by_domain"]["d1"] == 2
        assert stats["workflows_by_domain"]["d2"] == 1


# ===========================================================================
# Workflow YAML
# ===========================================================================


class TestWorkflowYaml:
    """WorkflowSpec YAML parsing."""

    def test_minimal_spec(self):
        from spine.orchestration.workflow_yaml import WorkflowSpec

        data = {
            "apiVersion": "spine.io/v1",
            "kind": "Workflow",
            "metadata": {"name": "test.wf"},
            "spec": {
                "steps": [{"name": "a", "operation": "p1"}],
            },
        }
        spec = WorkflowSpec.model_validate(data)
        wf = spec.to_workflow()
        assert wf.name == "test.wf"
        assert len(wf.steps) == 1

    def test_full_spec(self):
        from spine.orchestration.workflow_yaml import WorkflowSpec

        data = {
            "apiVersion": "spine.io/v1",
            "kind": "Workflow",
            "metadata": {
                "name": "ingest.daily",
                "domain": "ingest",
                "version": 2,
                "description": "Daily ingest",
                "tags": ["daily", "ingest"],
            },
            "spec": {
                "defaults": {"batch_size": 1000},
                "steps": [
                    {"name": "fetch", "operation": "ingest.fetch"},
                    {"name": "normalize", "operation": "ingest.normalize", "depends_on": ["fetch"]},
                    {"name": "store", "operation": "ingest.store", "depends_on": ["normalize"]},
                ],
                "policy": {
                    "execution": "parallel",
                    "max_concurrency": 8,
                    "on_failure": "continue",
                    "timeout_seconds": 600,
                },
            },
        }
        spec = WorkflowSpec.model_validate(data)
        wf = spec.to_workflow()
        assert wf.name == "ingest.daily"
        assert wf.domain == "ingest"
        assert wf.version == 2
        assert wf.tags == ["daily", "ingest"]
        assert wf.defaults == {"batch_size": 1000}
        assert len(wf.steps) == 3
        assert wf.steps[1].depends_on == ("fetch",)
        assert wf.execution_policy.mode == ExecutionMode.PARALLEL
        assert wf.execution_policy.max_concurrency == 8
        assert wf.execution_policy.on_failure == FailurePolicy.CONTINUE
        assert wf.execution_policy.timeout_seconds == 600

    def test_duplicate_step_names_rejected(self):
        from pydantic import ValidationError

        from spine.orchestration.workflow_yaml import WorkflowSpec

        data = {
            "metadata": {"name": "t"},
            "spec": {
                "steps": [
                    {"name": "a", "operation": "p1"},
                    {"name": "a", "operation": "p2"},
                ],
            },
        }
        with pytest.raises(ValidationError, match="Duplicate"):
            WorkflowSpec.model_validate(data)

    def test_invalid_dependency_rejected(self):
        from pydantic import ValidationError

        from spine.orchestration.workflow_yaml import WorkflowSpec

        data = {
            "metadata": {"name": "t"},
            "spec": {
                "steps": [
                    {"name": "a", "operation": "p1", "depends_on": ["nonexistent"]},
                ],
            },
        }
        with pytest.raises(ValidationError, match="unknown"):
            WorkflowSpec.model_validate(data)

    def test_self_dependency_rejected(self):
        from pydantic import ValidationError

        from spine.orchestration.workflow_yaml import WorkflowSpec

        data = {
            "metadata": {"name": "t"},
            "spec": {
                "steps": [
                    {"name": "a", "operation": "p1", "depends_on": ["a"]},
                ],
            },
        }
        with pytest.raises(ValidationError, match="cannot depend on itself"):
            WorkflowSpec.model_validate(data)

    def test_from_yaml_string(self):
        pytest.importorskip("yaml")
        from spine.orchestration.workflow_yaml import WorkflowSpec

        yaml_str = """\
apiVersion: spine.io/v1
kind: Workflow
metadata:
  name: test.wf
  domain: test
spec:
  steps:
    - name: fetch
      operation: test.fetch
    - name: process
      operation: test.process
      depends_on: [fetch]
  policy:
    execution: parallel
"""
        spec = WorkflowSpec.from_yaml(yaml_str)
        wf = spec.to_workflow()
        assert wf.name == "test.wf"
        assert wf.steps[1].depends_on == ("fetch",)
        assert wf.execution_policy.mode == ExecutionMode.PARALLEL

    def test_validate_yaml_workflow_convenience(self):
        from spine.orchestration.workflow_yaml import validate_yaml_workflow

        data = {
            "apiVersion": "spine.io/v1",
            "kind": "Workflow",
            "metadata": {"name": "t"},
            "spec": {
                "steps": [{"name": "a", "operation": "p1"}],
            },
        }
        wf = validate_yaml_workflow(data)
        assert isinstance(wf, Workflow)
        assert wf.name == "t"

    def test_wrong_kind_rejected(self):
        from pydantic import ValidationError

        from spine.orchestration.workflow_yaml import WorkflowSpec

        data = {
            "apiVersion": "spine.io/v1",
            "kind": "OperationGroup",
            "metadata": {"name": "t"},
            "spec": {"steps": [{"name": "a", "operation": "p1"}]},
        }
        with pytest.raises(ValidationError):
            WorkflowSpec.model_validate(data)

    def test_extra_fields_rejected(self):
        from pydantic import ValidationError

        from spine.orchestration.workflow_yaml import WorkflowSpec

        data = {
            "metadata": {"name": "t"},
            "spec": {
                "steps": [{"name": "a", "operation": "p1", "extra_field": True}],
            },
        }
        with pytest.raises(ValidationError):
            WorkflowSpec.model_validate(data)


# ===========================================================================
# Workflow Executor
# ===========================================================================


class TestWorkflowExecutor:
    """Execution-layer workflow bridge."""

    def test_execute_workflow_convenience(self):
        from spine.execution.workflow_executor import execute_workflow

        wf = Workflow(
            name="direct",
            steps=[Step.lambda_("a", lambda ctx, cfg: StepResult.ok(output={"v": 1}))],
        )
        result = execute_workflow(wf, dry_run=False)
        assert result.status == WorkflowStatus.COMPLETED

    def test_execute_workflow_dry_run(self):
        from spine.execution.workflow_executor import execute_workflow

        wf = Workflow(
            name="dry",
            steps=[Step.operation("a", "nonexistent.operation")],
        )
        result = execute_workflow(wf, dry_run=True)
        assert result.status == WorkflowStatus.COMPLETED
