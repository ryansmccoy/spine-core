"""Tests for architecture invariants."""

import ast
import pytest
from pathlib import Path


class TestArchitectureInvariants:
    """Tests that verify architectural constraints are maintained."""

    @pytest.fixture
    def src_path(self):
        """Path to source code."""
        return Path(__file__).parent.parent / "src" / "market_spine"

    def test_dispatcher_is_single_execution_entrypoint(self, src_path):
        """Verify that only Dispatcher calls ledger.create_execution()."""
        violations = []

        for py_file in src_path.rglob("*.py"):
            if "test_" in py_file.name:
                continue

            content = py_file.read_text()

            # Skip the dispatcher itself
            if py_file.name == "dispatcher.py":
                continue

            # Check for direct create_execution calls
            if "create_execution" in content and "ledger" in content:
                if ".create_execution(" in content:
                    violations.append(str(py_file))

        assert not violations, f"create_execution called outside Dispatcher: {violations}"

    def test_run_pipeline_is_single_processing_point(self, src_path):
        """Verify that only runner.py and cli.py call pipeline handlers directly.

        CLI is allowed to call run_pipeline for local (non-dispatched) execution.
        """
        violations = []

        for py_file in src_path.rglob("*.py"):
            if "test_" in py_file.name:
                continue

            # Skip the runner itself and CLI (CLI can call run_pipeline for local execution)
            if py_file.name in ("runner.py", "cli.py"):
                continue

            content = py_file.read_text()

            # Check for direct handler calls
            if "pipeline_def.handler(" in content:
                violations.append(str(py_file))

        assert not violations, f"pipeline handlers called outside runner: {violations}"

    def test_api_does_not_call_run_pipeline(self, src_path):
        """Verify that API routes don't call run_pipeline directly."""
        api_path = src_path / "api"
        violations = []

        for py_file in api_path.rglob("*.py"):
            content = py_file.read_text()

            if "run_pipeline" in content and "from" in content:
                # Check if it's actually importing run_pipeline
                if "from market_spine.pipelines.runner import" in content:
                    violations.append(str(py_file))
                if "from market_spine.pipelines import run_pipeline" in content:
                    violations.append(str(py_file))

        assert not violations, f"API routes import run_pipeline: {violations}"

    def test_backend_submit_signature(self, src_path):
        """Verify that all backends have consistent submit signature."""
        backends_path = src_path / "backends"
        required_params = {"execution_id", "pipeline", "lane"}

        for py_file in backends_path.glob("*.py"):
            if py_file.name == "__init__.py":
                continue

            content = py_file.read_text()
            tree = ast.parse(content)

            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef) and node.name == "submit":
                    # Get parameter names (excluding self)
                    params = {arg.arg for arg in node.args.args if arg.arg != "self"}
                    assert required_params.issubset(params), (
                        f"{py_file.name} submit() missing params: {required_params - params}"
                    )

    def test_no_direct_celery_task_calls_in_api(self, src_path):
        """Verify API doesn't call Celery tasks directly except through backend."""
        api_path = src_path / "api"
        allowed_tasks = ["retry_dead_letter_task"]  # This one is allowed in DLQ endpoint

        for py_file in api_path.rglob("*.py"):
            content = py_file.read_text()

            # Check for .delay() or .apply_async() calls
            if ".delay(" in content or ".apply_async(" in content:
                # Check if it's an allowed task
                is_allowed = any(task in content for task in allowed_tasks)
                if not is_allowed:
                    if "run_pipeline_task" in content:
                        pytest.fail(
                            f"{py_file} calls Celery task directly. "
                            "Use Dispatcher.submit() instead."
                        )

    def test_models_are_dataclasses(self, src_path):
        """Verify that domain models use dataclasses."""
        models_file = src_path / "core" / "models.py"
        content = models_file.read_text()
        tree = ast.parse(content)

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                # Check if it has @dataclass decorator
                decorators = [
                    d.id if isinstance(d, ast.Name) else None for d in node.decorator_list
                ]
                if node.name in ["Execution", "ExecutionEvent", "DeadLetter"]:
                    assert "dataclass" in decorators, f"{node.name} should be a dataclass"
