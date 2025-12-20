"""
CLI: ``spine-core devtools`` — developer tools for workflow analysis.

Provides lint, visualize, dry-run, and composition commands that
operate on workflow definitions without requiring a running API or
database.
"""

from __future__ import annotations

import json
import sys

import typer

app = typer.Typer(no_args_is_help=True)


# ── spine-core devtools lint ─────────────────────────────────────────


@app.command("lint")
def lint_cmd(
    workflow_file: str = typer.Argument(
        ...,
        help="Python file containing a 'workflow' variable (Workflow instance).",
    ),
    variable: str = typer.Option(
        "workflow",
        "--var",
        "-v",
        help="Name of the Workflow variable in the file.",
    ),
    json_out: bool = typer.Option(False, "--json", "-j", help="Output as JSON."),
    strict: bool = typer.Option(False, "--strict", help="Exit non-zero on warnings too."),
) -> None:
    """Lint a workflow definition for errors and warnings.

    Loads a Python file, extracts the named Workflow variable, and
    runs the linter against it.

    Example:
        spine-core devtools lint my_workflow.py
        spine-core devtools lint my_workflow.py --var wf --json
    """
    workflow = _load_workflow(workflow_file, variable)

    from spine.orchestration.linter import lint_workflow

    result = lint_workflow(workflow)

    if json_out:
        data = {
            "passed": result.passed,
            "error_count": len(result.errors),
            "warning_count": len(result.warnings),
            "info_count": len(result.infos),
            "diagnostics": [
                {
                    "code": d.code,
                    "severity": d.severity.value,
                    "message": d.message,
                    "step_name": d.step_name,
                    "suggestion": d.suggestion,
                }
                for d in result.diagnostics
            ],
        }
        typer.echo(json.dumps(data, indent=2))
    else:
        typer.echo(result.summary())

    if not result.passed:
        raise typer.Exit(code=1)
    if strict and result.warnings:
        raise typer.Exit(code=1)


# ── spine-core devtools visualize ────────────────────────────────────


@app.command("visualize")
def visualize_cmd(
    workflow_file: str = typer.Argument(
        ...,
        help="Python file containing a 'workflow' variable.",
    ),
    variable: str = typer.Option("workflow", "--var", "-v"),
    fmt: str = typer.Option(
        "ascii",
        "--format",
        "-f",
        help="Output format: ascii, mermaid, summary.",
    ),
    output_file: str | None = typer.Option(
        None,
        "--output",
        "-o",
        help="Write output to file instead of stdout.",
    ),
) -> None:
    """Visualize a workflow definition.

    Produces an ASCII diagram, Mermaid chart, or text summary of
    the workflow's step graph.

    Example:
        spine-core devtools visualize my_workflow.py --format mermaid
        spine-core devtools visualize my_workflow.py -f ascii -o graph.txt
    """
    workflow = _load_workflow(workflow_file, variable)

    from spine.orchestration.visualizer import (
        visualize_ascii,
        visualize_mermaid,
        visualize_summary,
    )

    renderers = {
        "ascii": visualize_ascii,
        "mermaid": visualize_mermaid,
        "summary": visualize_summary,
    }

    if fmt not in renderers:
        typer.echo(f"Unknown format: {fmt}. Use: {', '.join(renderers)}", err=True)
        raise typer.Exit(code=1)

    text = renderers[fmt](workflow)

    if output_file:
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(text)
        typer.echo(f"Written to {output_file}")
    else:
        typer.echo(text)


# ── spine-core devtools dry-run ──────────────────────────────────────


@app.command("dry-run")
def dry_run_cmd(
    workflow_file: str = typer.Argument(
        ...,
        help="Python file containing a 'workflow' variable.",
    ),
    variable: str = typer.Option("workflow", "--var", "-v"),
    params: str | None = typer.Option(
        None,
        "--params",
        "-p",
        help="JSON string of parameters to pass to the workflow.",
    ),
    json_out: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Dry-run a workflow to preview its execution plan.

    Analyses the workflow structure, validates steps, and estimates
    execution time without actually running anything.

    Example:
        spine-core devtools dry-run my_workflow.py
        spine-core devtools dry-run my_workflow.py --params '{"tier": "NMS"}'
    """
    workflow = _load_workflow(workflow_file, variable)

    from spine.orchestration.dry_run import dry_run

    parsed_params = json.loads(params) if params else None
    result = dry_run(workflow, params=parsed_params)

    if json_out:
        data = {
            "workflow_name": result.workflow_name,
            "is_valid": result.is_valid,
            "execution_mode": result.execution_mode,
            "step_count": result.step_count,
            "total_estimated_seconds": result.total_estimated_seconds,
            "validation_issues": result.validation_issues,
            "execution_plan": [
                {
                    "step_name": s.step_name,
                    "step_type": s.step_type,
                    "order": s.order,
                    "estimated_seconds": s.estimated_seconds,
                    "will_execute": s.will_execute,
                    "dependencies": list(s.dependencies),
                    "notes": list(s.notes),
                }
                for s in result.execution_plan
            ],
        }
        typer.echo(json.dumps(data, indent=2))
    else:
        typer.echo(result.summary())

    if not result.is_valid:
        raise typer.Exit(code=1)


# ── spine-core devtools compose ──────────────────────────────────────


@app.command("compose")
def compose_cmd(
    operator: str = typer.Argument(
        ...,
        help="Composition operator: chain, parallel, retry, merge.",
    ),
) -> None:
    """Show usage info for composition operators.

    Prints documentation and examples for the requested composition
    operator (chain, parallel, conditional, retry, merge_workflows).

    Example:
        spine-core devtools compose chain
        spine-core devtools compose parallel
    """
    from spine.orchestration.composition import (
        chain,
        conditional,
        merge_workflows,
        parallel,
        retry,
    )

    docs = {
        "chain": chain,
        "parallel": parallel,
        "conditional": conditional,
        "retry": retry,
        "merge": merge_workflows,
        "merge_workflows": merge_workflows,
    }

    if operator not in docs:
        typer.echo(f"Unknown operator: {operator}. Available: {', '.join(sorted(set(docs)))}", err=True)
        raise typer.Exit(code=1)

    fn = docs[operator]
    typer.echo(f"=== {operator} ===\n")
    typer.echo(fn.__doc__ or "No documentation available.")


# ── Helpers ──────────────────────────────────────────────────────────


def _load_workflow(filepath: str, variable: str) -> object:
    """Load a Workflow variable from a Python file.

    Parameters
    ----------
    filepath
        Path to the Python source file.
    variable
        Name of the Workflow variable to extract.

    Returns
    -------
    Workflow
        The loaded workflow instance.
    """
    import importlib.util
    from pathlib import Path

    path = Path(filepath)
    if not path.exists():
        typer.echo(f"File not found: {filepath}", err=True)
        raise typer.Exit(code=1)

    spec = importlib.util.spec_from_file_location("_workflow_module", path)
    if spec is None or spec.loader is None:
        typer.echo(f"Cannot load module from: {filepath}", err=True)
        raise typer.Exit(code=1)

    module = importlib.util.module_from_spec(spec)
    sys.modules["_workflow_module"] = module

    try:
        spec.loader.exec_module(module)
    except Exception as e:
        typer.echo(f"Error loading {filepath}: {e}", err=True)
        raise typer.Exit(code=1) from e

    workflow = getattr(module, variable, None)
    if workflow is None:
        typer.echo(
            f"Variable '{variable}' not found in {filepath}. "
            f"Available: {[n for n in dir(module) if not n.startswith('_')]}",
            err=True,
        )
        raise typer.Exit(code=1)

    return workflow
