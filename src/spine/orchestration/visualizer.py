"""Workflow Visualizer — render workflows as Mermaid diagrams or ASCII.

Generates visual representations of workflow DAGs for documentation,
debugging, and log output.  Uses existing ``Workflow`` graph methods
(``dependency_graph()``, ``topological_order()``) to build adjacency
information.

Architecture::

    Workflow
    ├── .steps
    ├── .dependency_graph()
    └── .topological_order()
        │
        ▼
    visualize_mermaid(workflow)  → str (Mermaid graph TD)
    visualize_ascii(workflow)   → str (box drawing)
    visualize_summary(workflow) → dict (metadata)

    Mermaid step shapes:
    - PIPELINE  → [pipeline_name]  (rectangle)
    - LAMBDA    → (handler_name)   (rounded)
    - CHOICE    → {condition}      (diamond)
    - WAIT      → [[wait]]         (subroutine)
    - MAP       → [/fan-out/]      (parallelogram)

Example::

    from spine.orchestration.visualizer import visualize_mermaid, visualize_ascii
    from spine.orchestration import Workflow, Step

    workflow = Workflow(
        name="etl.pipeline",
        steps=[
            Step.pipeline("extract", "data.extract"),
            Step.lambda_("transform", transform_fn),
            Step.pipeline("load", "data.load"),
        ],
    )

    print(visualize_mermaid(workflow))
    # graph TD
    #     extract["extract<br/>data.extract"]
    #     transform("transform")
    #     load["load<br/>data.load"]
    #     extract --> transform
    #     transform --> load

    print(visualize_ascii(workflow))
    # ┌─────────┐    ┌───────────┐    ┌──────┐
    # │ extract │───▶│ transform │───▶│ load │
    # └─────────┘    └───────────┘    └──────┘

See Also:
    spine.orchestration.linter — static workflow analysis
    spine.orchestration.playground — interactive execution
"""

from __future__ import annotations

import logging
from typing import Any

from spine.orchestration.step_types import Step, StepType
from spine.orchestration.workflow import Workflow

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Mermaid rendering
# ---------------------------------------------------------------------------

def _mermaid_node(step: Step) -> str:
    """Return a Mermaid node definition for a step."""
    name = step.name
    label = name

    if step.step_type == StepType.PIPELINE and step.pipeline_name:
        label = f"{name}<br/>{step.pipeline_name}"
        return f'    {name}["{label}"]'

    elif step.step_type == StepType.LAMBDA:
        return f'    {name}("{label}")'

    elif step.step_type == StepType.CHOICE:
        return f"    {name}{{{label}}}"

    elif step.step_type == StepType.WAIT:
        return f'    {name}[["{label}"]]'

    elif step.step_type == StepType.MAP:
        return f'    {name}[/"{label}"/]'

    else:
        return f'    {name}["{label}"]'


def _mermaid_style(step: Step) -> str | None:
    """Return optional Mermaid style for a step type."""
    styles = {
        StepType.PIPELINE: "fill:#e3f2fd,stroke:#1565c0",
        StepType.LAMBDA: "fill:#f3e5f5,stroke:#7b1fa2",
        StepType.CHOICE: "fill:#fff3e0,stroke:#e65100",
        StepType.WAIT: "fill:#e8f5e9,stroke:#2e7d32",
        StepType.MAP: "fill:#fce4ec,stroke:#c62828",
    }
    style = styles.get(step.step_type)
    if style:
        return f"    style {step.name} {style}"
    return None


def visualize_mermaid(workflow: Workflow, *, direction: str = "TD",
                       include_styles: bool = True,
                       title: str | None = None) -> str:
    """Render a workflow as a Mermaid graph.

    Parameters
    ----------
    workflow
        The workflow to visualize.
    direction
        Graph direction: ``"TD"`` (top-down), ``"LR"`` (left-right).
    include_styles
        If True, include color styles for step types.
    title
        Optional title displayed above the graph.

    Returns
    -------
    str
        Complete Mermaid graph definition.
    """
    lines: list[str] = []

    if title:
        lines.append(f"---")
        lines.append(f"title: {title}")
        lines.append(f"---")

    lines.append(f"graph {direction}")

    # Node definitions
    for step in workflow.steps:
        lines.append(_mermaid_node(step))

    lines.append("")  # blank line before edges

    # Edges
    if workflow.has_dependencies():
        # DAG mode: use depends_on edges
        for step in workflow.steps:
            for dep in step.depends_on:
                lines.append(f"    {dep} --> {step.name}")
            # Choice step edges
            if step.step_type == StepType.CHOICE:
                if step.then_step:
                    lines.append(f"    {step.name} -->|true| {step.then_step}")
                if step.else_step:
                    lines.append(f"    {step.name} -->|false| {step.else_step}")
    else:
        # Sequential mode: chain steps in order
        for i in range(len(workflow.steps) - 1):
            current = workflow.steps[i]
            next_step = workflow.steps[i + 1]

            if current.step_type == StepType.CHOICE:
                if current.then_step:
                    lines.append(f"    {current.name} -->|true| {current.then_step}")
                if current.else_step:
                    lines.append(f"    {current.name} -->|false| {current.else_step}")
            else:
                lines.append(f"    {current.name} --> {next_step.name}")

    # Styles
    if include_styles:
        styles = []
        for step in workflow.steps:
            s = _mermaid_style(step)
            if s:
                styles.append(s)
        if styles:
            lines.append("")
            lines.extend(styles)

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# ASCII rendering
# ---------------------------------------------------------------------------

def visualize_ascii(workflow: Workflow) -> str:
    """Render a workflow as an ASCII box diagram.

    Parameters
    ----------
    workflow
        The workflow to visualize.

    Returns
    -------
    str
        Multi-line ASCII diagram.

    Note
    ----
    For complex DAGs with many branches, the Mermaid output is
    recommended.  ASCII rendering works best for sequential workflows
    and simple fan-out patterns.
    """
    if not workflow.steps:
        return f"(empty workflow: {workflow.name})"

    # Type indicators
    type_indicators = {
        StepType.PIPELINE: "P",
        StepType.LAMBDA: "λ",
        StepType.CHOICE: "?",
        StepType.WAIT: "⏳",
        StepType.MAP: "⇶",
    }

    if workflow.has_dependencies():
        return _ascii_dag(workflow, type_indicators)
    else:
        return _ascii_sequential(workflow, type_indicators)


def _ascii_sequential(workflow: Workflow, indicators: dict[StepType, str]) -> str:
    """Render a sequential workflow as a horizontal chain."""
    lines: list[str] = []
    lines.append(f"Workflow: {workflow.name}")
    lines.append("")

    boxes: list[str] = []
    for step in workflow.steps:
        ind = indicators.get(step.step_type, "·")
        label = f"[{ind}] {step.name}"
        width = len(label) + 2
        top = "┌" + "─" * width + "┐"
        mid = "│ " + label + " │"
        bot = "└" + "─" * width + "┘"
        boxes.append((top, mid, bot))

    # Build 3-line output with arrows between boxes
    top_line = ""
    mid_line = ""
    bot_line = ""

    for i, (top, mid, bot) in enumerate(boxes):
        top_line += top
        mid_line += mid
        bot_line += bot

        if i < len(boxes) - 1:
            top_line += "    "
            mid_line += "───▶"
            bot_line += "    "

    lines.append(top_line)
    lines.append(mid_line)
    lines.append(bot_line)

    return "\n".join(lines)


def _ascii_dag(workflow: Workflow, indicators: dict[StepType, str]) -> str:
    """Render a DAG workflow as a vertical list with dependency info."""
    lines: list[str] = []
    lines.append(f"Workflow: {workflow.name} (DAG)")
    lines.append("")

    order = workflow.topological_order()
    step_map = {s.name: s for s in workflow.steps}

    for name in order:
        step = step_map.get(name)
        if step is None:
            continue

        ind = indicators.get(step.step_type, "·")
        deps = ", ".join(step.depends_on) if step.depends_on else "(root)"
        detail = ""
        if step.step_type == StepType.PIPELINE and step.pipeline_name:
            detail = f" → {step.pipeline_name}"
        elif step.step_type == StepType.CHOICE:
            parts = []
            if step.then_step:
                parts.append(f"then={step.then_step}")
            if step.else_step:
                parts.append(f"else={step.else_step}")
            detail = f" → {', '.join(parts)}" if parts else ""

        lines.append(f"  [{ind}] {name}{detail}")
        lines.append(f"       depends_on: {deps}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Summary / metadata
# ---------------------------------------------------------------------------

def visualize_summary(workflow: Workflow) -> dict[str, Any]:
    """Return metadata about the workflow's structure.

    Parameters
    ----------
    workflow
        The workflow to analyze.

    Returns
    -------
    dict
        Metadata including step_count, edge_count, step_types,
        has_branches, max_depth, tier, and critical_path.
    """
    step_count = len(workflow.steps)
    step_names = {s.name for s in workflow.steps}

    # Count edges
    edge_count = sum(len(s.depends_on) for s in workflow.steps)
    # Also count implicit sequential edges if no deps
    if not workflow.has_dependencies() and step_count > 1:
        edge_count = step_count - 1

    # Step type distribution
    type_counts: dict[str, int] = {}
    for step in workflow.steps:
        t = step.step_type.value
        type_counts[t] = type_counts.get(t, 0) + 1

    # Check for branches
    has_branches = workflow.has_choice_steps() or workflow.has_dependencies()

    # Max depth (longest path in DAG)
    max_depth = _compute_max_depth(workflow)

    # Critical path (longest chain of steps)
    critical_path = _compute_critical_path(workflow)

    return {
        "workflow_name": workflow.name,
        "step_count": step_count,
        "edge_count": edge_count,
        "step_types": type_counts,
        "has_branches": has_branches,
        "has_dependencies": workflow.has_dependencies(),
        "max_depth": max_depth,
        "critical_path": critical_path,
        "tier": workflow.required_tier(),
        "pipeline_names": workflow.pipeline_names(),
    }


def _compute_max_depth(workflow: Workflow) -> int:
    """Compute maximum depth of the dependency graph."""
    if not workflow.steps:
        return 0
    if not workflow.has_dependencies():
        return len(workflow.steps)

    # Build adjacency and compute depth with dynamic programming
    depths: dict[str, int] = {}
    step_map = {s.name: s for s in workflow.steps}
    adjacency = workflow.dependency_graph()

    def depth(name: str) -> int:
        if name in depths:
            return depths[name]
        step = step_map.get(name)
        if step is None or not step.depends_on:
            depths[name] = 1
            return 1
        max_dep = max(depth(d) for d in step.depends_on if d in step_map)
        depths[name] = max_dep + 1
        return depths[name]

    return max(depth(s.name) for s in workflow.steps)


def _compute_critical_path(workflow: Workflow) -> list[str]:
    """Compute the critical path (longest chain of steps)."""
    if not workflow.steps:
        return []
    if not workflow.has_dependencies():
        return [s.name for s in workflow.steps]

    step_map = {s.name: s for s in workflow.steps}

    # Find the step with maximum depth and trace back
    depths: dict[str, int] = {}
    parents: dict[str, str | None] = {}

    def depth(name: str) -> int:
        if name in depths:
            return depths[name]
        step = step_map.get(name)
        if step is None or not step.depends_on:
            depths[name] = 1
            parents[name] = None
            return 1
        best_dep = None
        best_depth = 0
        for d in step.depends_on:
            if d in step_map:
                dd = depth(d)
                if dd > best_depth:
                    best_depth = dd
                    best_dep = d
        depths[name] = best_depth + 1
        parents[name] = best_dep
        return depths[name]

    for s in workflow.steps:
        depth(s.name)

    # Find the deepest step
    deepest = max(workflow.steps, key=lambda s: depths.get(s.name, 0))

    # Trace back the path
    path: list[str] = []
    current: str | None = deepest.name
    while current is not None:
        path.append(current)
        current = parents.get(current)

    path.reverse()
    return path
