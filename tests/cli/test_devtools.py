"""Tests for spine.cli.devtools — CLI developer tools."""

from __future__ import annotations

import json
import tempfile
import textwrap
from pathlib import Path

import pytest
from typer.testing import CliRunner

from spine.cli.devtools import app


runner = CliRunner()


def _write_workflow_file(tmp_dir: Path, content: str, filename: str = "wf.py") -> Path:
    """Write a Python file with workflow content and return path."""
    filepath = tmp_dir / filename
    filepath.write_text(textwrap.dedent(content))
    return filepath


# ── lint command ─────────────────────────────────────────────────────


class TestLintCommand:
    """Tests for the 'devtools lint' command."""

    def test_lint_clean_workflow(self, tmp_path):
        f = _write_workflow_file(tmp_path, """
            from spine.orchestration.step_result import StepResult
            from spine.orchestration.step_types import Step
            from spine.orchestration.workflow import Workflow

            def handler(ctx, config):
                return StepResult.ok()

            workflow = Workflow(
                name="test.clean",
                steps=[
                    Step.lambda_("step_a", handler),
                    Step.lambda_("step_b", handler),
                ],
            )
        """)
        result = runner.invoke(app, ["lint", str(f)])
        assert result.exit_code == 0

    def test_lint_bad_workflow(self, tmp_path):
        f = _write_workflow_file(tmp_path, """
            from spine.orchestration.step_types import Step
            from spine.orchestration.workflow import Workflow

            workflow = Workflow(
                name="test.bad",
                steps=[
                    Step.lambda_("broken", None),
                ],
            )
        """)
        result = runner.invoke(app, ["lint", str(f)])
        assert result.exit_code == 1

    def test_lint_json_output(self, tmp_path):
        f = _write_workflow_file(tmp_path, """
            from spine.orchestration.step_result import StepResult
            from spine.orchestration.step_types import Step
            from spine.orchestration.workflow import Workflow

            def handler(ctx, config):
                return StepResult.ok()

            workflow = Workflow(
                name="test.json",
                steps=[Step.lambda_("a", handler)],
            )
        """)
        result = runner.invoke(app, ["lint", str(f), "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["passed"] is True

    def test_lint_missing_file(self):
        result = runner.invoke(app, ["lint", "nonexistent.py"])
        assert result.exit_code == 1

    def test_lint_custom_variable(self, tmp_path):
        f = _write_workflow_file(tmp_path, """
            from spine.orchestration.step_result import StepResult
            from spine.orchestration.step_types import Step
            from spine.orchestration.workflow import Workflow

            def handler(ctx, config):
                return StepResult.ok()

            my_wf = Workflow(
                name="test.custom",
                steps=[Step.lambda_("a", handler)],
            )
        """)
        result = runner.invoke(app, ["lint", str(f), "--var", "my_wf"])
        assert result.exit_code == 0


# ── visualize command ────────────────────────────────────────────────


class TestVisualizeCommand:
    """Tests for the 'devtools visualize' command."""

    def test_visualize_ascii(self, tmp_path):
        f = _write_workflow_file(tmp_path, """
            from spine.orchestration.step_result import StepResult
            from spine.orchestration.step_types import Step
            from spine.orchestration.workflow import Workflow

            def handler(ctx, config):
                return StepResult.ok()

            workflow = Workflow(
                name="test.viz",
                steps=[Step.lambda_("a", handler), Step.lambda_("b", handler)],
            )
        """)
        result = runner.invoke(app, ["visualize", str(f), "--format", "ascii"])
        assert result.exit_code == 0
        assert "a" in result.output

    def test_visualize_mermaid(self, tmp_path):
        f = _write_workflow_file(tmp_path, """
            from spine.orchestration.step_result import StepResult
            from spine.orchestration.step_types import Step
            from spine.orchestration.workflow import Workflow

            def handler(ctx, config):
                return StepResult.ok()

            workflow = Workflow(
                name="test.mermaid",
                steps=[Step.lambda_("a", handler), Step.lambda_("b", handler)],
            )
        """)
        result = runner.invoke(app, ["visualize", str(f), "--format", "mermaid"])
        assert result.exit_code == 0
        assert "graph" in result.output.lower() or "flowchart" in result.output.lower()

    def test_visualize_unknown_format(self, tmp_path):
        f = _write_workflow_file(tmp_path, """
            from spine.orchestration.step_types import Step
            from spine.orchestration.workflow import Workflow

            workflow = Workflow(name="test", steps=[])
        """)
        result = runner.invoke(app, ["visualize", str(f), "--format", "pdf"])
        assert result.exit_code == 1

    def test_visualize_to_file(self, tmp_path):
        f = _write_workflow_file(tmp_path, """
            from spine.orchestration.step_result import StepResult
            from spine.orchestration.step_types import Step
            from spine.orchestration.workflow import Workflow

            def handler(ctx, config):
                return StepResult.ok()

            workflow = Workflow(
                name="test.file",
                steps=[Step.lambda_("a", handler)],
            )
        """)
        outf = tmp_path / "output.txt"
        result = runner.invoke(app, ["visualize", str(f), "-o", str(outf)])
        assert result.exit_code == 0
        assert outf.exists()
        assert len(outf.read_text(encoding="utf-8")) > 0


# ── dry-run command ──────────────────────────────────────────────────


class TestDryRunCommand:
    """Tests for the 'devtools dry-run' command."""

    def test_dry_run_valid(self, tmp_path):
        f = _write_workflow_file(tmp_path, """
            from spine.orchestration.step_result import StepResult
            from spine.orchestration.step_types import Step
            from spine.orchestration.workflow import Workflow

            def handler(ctx, config):
                return StepResult.ok()

            workflow = Workflow(
                name="test.dryrun",
                steps=[
                    Step.lambda_("a", handler),
                    Step.operation("b", "data.process"),
                ],
            )
        """)
        result = runner.invoke(app, ["dry-run", str(f)])
        assert result.exit_code == 0
        assert "EXECUTION PLAN" in result.output

    def test_dry_run_json(self, tmp_path):
        f = _write_workflow_file(tmp_path, """
            from spine.orchestration.step_result import StepResult
            from spine.orchestration.step_types import Step
            from spine.orchestration.workflow import Workflow

            def handler(ctx, config):
                return StepResult.ok()

            workflow = Workflow(
                name="test.json",
                steps=[Step.lambda_("a", handler)],
            )
        """)
        result = runner.invoke(app, ["dry-run", str(f), "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["is_valid"] is True
        assert data["step_count"] == 1

    def test_dry_run_with_params(self, tmp_path):
        f = _write_workflow_file(tmp_path, """
            from spine.orchestration.step_result import StepResult
            from spine.orchestration.step_types import Step
            from spine.orchestration.workflow import Workflow

            def handler(ctx, config):
                return StepResult.ok()

            workflow = Workflow(
                name="test.params",
                steps=[Step.lambda_("a", handler)],
            )
        """)
        result = runner.invoke(app, ["dry-run", str(f), "--params", '{"tier": "NMS"}'])
        assert result.exit_code == 0

    def test_dry_run_invalid_exits_nonzero(self, tmp_path):
        f = _write_workflow_file(tmp_path, """
            from spine.orchestration.step_types import Step
            from spine.orchestration.workflow import Workflow

            workflow = Workflow(name="test.empty", steps=[])
        """)
        result = runner.invoke(app, ["dry-run", str(f)])
        assert result.exit_code == 1


# ── compose command ──────────────────────────────────────────────────


class TestComposeCommand:
    """Tests for the 'devtools compose' command."""

    def test_compose_chain(self):
        result = runner.invoke(app, ["compose", "chain"])
        assert result.exit_code == 0
        assert "chain" in result.output.lower()

    def test_compose_parallel(self):
        result = runner.invoke(app, ["compose", "parallel"])
        assert result.exit_code == 0

    def test_compose_unknown(self):
        result = runner.invoke(app, ["compose", "unknown_op"])
        assert result.exit_code == 1
