#!/usr/bin/env python3
"""Workflow Visualizer — Mermaid, ASCII, and summary output.

Demonstrates three visualization modes for workflow graphs:
``visualize_mermaid()`` for rich Mermaid diagrams, ``visualize_ascii()``
for terminal-friendly output, and ``visualize_summary()`` for
structural metrics.

Demonstrates:
    1. Mermaid diagram     — paste into GitHub PRs, docs, or live editors
    2. ASCII visualization — terminal-friendly step chains and DAGs
    3. Summary metrics     — step count, depth, critical path, tier
    4. DAG workflows       — dependency-based graphs
    5. Choice workflows    — branching paths
    6. Customization       — direction, title, styles

Architecture::

    visualize_mermaid(workflow)
    ├── graph direction (TD/LR/BT/RL)
    ├── step-type shapes:
    │   ├── pipeline  → rectangle    [name]
    │   ├── lambda    → rounded      (name)
    │   ├── choice    → diamond      {name}
    │   ├── wait      → subroutine   [[name]]
    │   └── map       → parallelogram [/name/]
    ├── dependency edges (-->)
    └── optional color styles + title

    visualize_ascii(workflow)
    ├── sequential → horizontal chain with ───▶
    └── DAG        → vertical list with depends_on info

    visualize_summary(workflow) → dict
    ├── step_count, edge_count
    ├── step_types, has_branches
    ├── max_depth, critical_path
    ├── tier (micro/small/medium/large/enterprise)
    └── pipeline_names

Key Concepts:
    - **Mermaid**: Standards-based, renders in GitHub, Notion, VS Code.
    - **ASCII**: Zero dependencies, works in any terminal or log file.
    - **Summary**: Machine-readable metrics for dashboards and CI gates.

See Also:
    - ``01_workflow_basics.py``  — workflow construction
    - ``07_parallel_dag.py``     — DAG parallelism
    - ``19_workflow_linter.py``  — static analysis
    - :mod:`spine.orchestration.visualizer`

Run:
    python examples/04_orchestration/21_workflow_visualizer.py

Expected Output:
    Mermaid diagram code, ASCII box chains, and summary dicts
    for sequential, DAG, and choice workflows.
"""

from spine.orchestration.step_types import Step
from spine.orchestration.workflow import Workflow
from spine.orchestration.visualizer import (
    visualize_mermaid,
    visualize_ascii,
    visualize_summary,
)


def _make_sequential() -> Workflow:
    """Three-step sequential pipeline."""
    return Workflow(
        name="etl_pipeline",
        steps=[
            Step.pipeline("extract", "data-extract"),
            Step.pipeline("transform", "data-transform"),
            Step.pipeline("load", "data-load"),
        ],
    )


def _make_dag() -> Workflow:
    """Four-step DAG with parallel branches."""
    return Workflow(
        name="parallel_dag",
        steps=[
            Step.pipeline("fetch_a", "fetch-a"),
            Step.pipeline("fetch_b", "fetch-b"),
            Step.pipeline("merge", "merge", depends_on=["fetch_a", "fetch_b"]),
            Step.pipeline("publish", "publish", depends_on=["merge"]),
        ],
    )


def _make_choice() -> Workflow:
    """Choice branching workflow."""
    return Workflow(
        name="decision_flow",
        steps=[
            Step.pipeline("validate", "validator"),
            Step.choice("route", condition=lambda ctx: True, then_step="process", else_step="reject"),
            Step.pipeline("process", "processor"),
            Step.pipeline("reject", "rejector"),
        ],
    )


def main() -> None:
    # ------------------------------------------------------------------
    # 1. Mermaid diagram — sequential pipeline
    # ------------------------------------------------------------------
    print(f"\n{'='*60}")
    print("1. Mermaid diagram (sequential)")
    print(f"{'='*60}")

    wf = _make_sequential()
    mermaid = visualize_mermaid(wf)
    print(mermaid)

    # ------------------------------------------------------------------
    # 2. Mermaid diagram — DAG with title and styles
    # ------------------------------------------------------------------
    print(f"\n{'='*60}")
    print("2. Mermaid diagram (DAG with title)")
    print(f"{'='*60}")

    dag = _make_dag()
    mermaid = visualize_mermaid(dag, direction="LR", title="Parallel DAG", include_styles=True)
    print(mermaid)

    # ------------------------------------------------------------------
    # 3. Mermaid diagram — choice workflow
    # ------------------------------------------------------------------
    print(f"\n{'='*60}")
    print("3. Mermaid diagram (choice branching)")
    print(f"{'='*60}")

    choice = _make_choice()
    mermaid = visualize_mermaid(choice)
    print(mermaid)

    # ------------------------------------------------------------------
    # 4. ASCII visualization — sequential
    # ------------------------------------------------------------------
    print(f"\n{'='*60}")
    print("4. ASCII visualization (sequential)")
    print(f"{'='*60}")

    ascii_out = visualize_ascii(wf)
    print(ascii_out)

    # ------------------------------------------------------------------
    # 5. ASCII visualization — DAG
    # ------------------------------------------------------------------
    print(f"\n{'='*60}")
    print("5. ASCII visualization (DAG)")
    print(f"{'='*60}")

    ascii_out = visualize_ascii(dag)
    print(ascii_out)

    # ------------------------------------------------------------------
    # 6. Summary metrics — sequential
    # ------------------------------------------------------------------
    print(f"\n{'='*60}")
    print("6. Summary metrics (sequential)")
    print(f"{'='*60}")

    summary = visualize_summary(wf)
    for key, val in summary.items():
        print(f"   {key}: {val}")

    # ------------------------------------------------------------------
    # 7. Summary metrics — DAG
    # ------------------------------------------------------------------
    print(f"\n{'='*60}")
    print("7. Summary metrics (DAG)")
    print(f"{'='*60}")

    summary = visualize_summary(dag)
    for key, val in summary.items():
        print(f"   {key}: {val}")

    # ------------------------------------------------------------------
    # 8. Summary metrics — choice
    # ------------------------------------------------------------------
    print(f"\n{'='*60}")
    print("8. Summary metrics (choice)")
    print(f"{'='*60}")

    summary = visualize_summary(choice)
    for key, val in summary.items():
        print(f"   {key}: {val}")

    # ------------------------------------------------------------------
    # 9. Tier classification
    # ------------------------------------------------------------------
    print(f"\n{'='*60}")
    print("9. Tier classification")
    print(f"{'='*60}")

    for wf_obj in [_make_sequential(), _make_dag(), _make_choice()]:
        s = visualize_summary(wf_obj)
        print(f"   {s['workflow_name']:20s} → {s['tier']} ({s['step_count']} steps)")

    print(f"\n{'='*60}")
    print("Done — workflow visualizer example complete")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
