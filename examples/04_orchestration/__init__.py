"""Orchestration — Workflows, step adapters, DAG execution, and YAML specs.

The orchestration engine composes Operations (08_framework) into
multi-step Workflows with context passing, error policies, parallel
execution, persistence, and declarative YAML definitions.

Examples are grouped into six logical sections.  Read top-to-bottom
for a progressive tour, or jump to a section by number.

FOUNDATIONS — how workflows work
──────────────────────────────────
    01 — Workflow basics (sequential lambda steps)
    02 — Operation vs Workflow comparison
    03 — WorkflowContext (cross-step data passing)

STEP CONFIGURATION — how steps are defined
──────────────────────────────────────────
    04 — Step adapters (plain Python → workflow steps)
    05 — Choice & branching (conditional routing)
    06 — Error policies (failure handling, retry)

EXECUTION — how workflows run
─────────────────────────────────
    07 — Parallel DAG (diamond-shaped fan-out / fan-in)
    08 — Tracked runner (database-backed execution)
    09 — Workflow playground (interactive debugging)

REGISTRY & SERIALIZATION — how workflows are stored and shared
───────────────────────────────────────────────────────
    10 — Workflow registry & YAML specs
    11 — Workflow serialization (to_dict, from_dict, to_yaml)
    12 — Managed workflows (import existing code, full lifecycle)

ADVANCED — specialized execution modes
────────────────────────────────────────
    13 — Workflow templates (ETL, fan-out, branch, retry, batch)
    14 — ContainerRunnable (orchestration ↔ container bridge)
    15 — Runnable protocol (operation execution interface)

INTEGRATION — real-world use cases
───────────────────────────────────
    16 — Webhook triggers (HTTP-triggered workflows)
    17 — SEC ETL workflow (9-step operation with quality gates)
    18 — Parallel vs multiprocessing (Pool vs DAG threads)
"""
