"""Framework — Operation building blocks, alerts, connectors, and structured logging.

This directory covers the **spine.framework** layer — reusable primitives
that you compose into the higher-level Workflow engine (04_orchestration).

HOW operations AND WORKFLOWS FIT TOGETHER
────────────────────────────────────────
    spine.framework (this directory)        spine.orchestration (04_*)
    ────────────────────────────────        ─────────────────────────────
    Operation  (single unit of work)   →    Step.operation("name")  (wired
    OperationRunner (execute by name)  →       into a Workflow)
    OperationRegistry (discover)       →    WorkflowRunner (orchestrates)
    OperationSpec / ParamDef           →    ManagedWorkflow (zero-coupling)
    AlertRegistry / channels          →    TrackedWorkflowRunner (persist)
    FileSource / connectors           →    Templates, YAML specs, DAGs
    Framework logging / timing        →    WorkflowPlayground (debug)

    Operation = "how to do one thing well"
    Workflow = "how to combine multiple things into a reliable process"

RECOMMENDED READING ORDER
─────────────────────────
    01 — Operation basics (define a Operation subclass)
    02 — Operation runner (execute by name, chain results)
    03 — Operation registry (discover and list operations)
    04 — Params validation (OperationSpec with ParamDef)
    05 — Alert routing (severity-filtered channels)
    06 — Source connectors (file ingestion with change detection)
    07 — Framework logging (structured logging with timing)

    THEN continue to 04_orchestration/ for Workflows:
    04_orchestration/01 — Workflow basics (composing steps)
    04_orchestration/12 — Managed workflow (import + lifecycle)
    04_orchestration/04 — Step adapters (zero framework coupling)
"""
