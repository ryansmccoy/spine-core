"""Execution engine — WorkSpec, handlers, dispatcher, executors, lifecycle, ledger.

The execution layer turns WorkSpecs into running tasks via Handlers,
Dispatchers, and Executors.  It manages the full lifecycle from
submission through completion, with async support, batching, health
checks, and persistent audit trails.

Examples are grouped into six logical sections.  Read top-to-bottom
for a progressive tour, or jump to a section by number.

WORK DESCRIPTION — what to execute
───────────────────────────────────
    01 — WorkSpec basics (the universal work description)
    02 — Handler registration (mapping specs to functions)
    03 — Dispatcher basics (central hub for submitting work)

LIFECYCLE — how execution progresses
──────────────────────────────────────
    04 — Run lifecycle (RunRecord state transitions)
    05 — Memory executor (in-process async for dev/test)
    06 — Local executor (thread-pool for I/O concurrency)

ASYNC & INTEGRATION — concurrent execution patterns
─────────────────────────────────────────────────────
    07 — Async patterns (coordination strategies)
    08 — FastAPI integration (REST APIs for operations)
    09 — Execution ledger (persistent audit trail)

ANALYTICS & BATCH — querying and bulk execution
─────────────────────────────────────────────────
    10 — Execution repository (analytics queries)
    11 — Batch execution (coordinated multi-operation runs)
    12 — Health checks (system health monitoring)

TRACKING — automatic execution recording
──────────────────────────────────────────
    13 — Tracked execution (context manager for auto-recording)
    14 — Worker loop (background polling engine)
    15 — Async local executor (native asyncio, no threads)

ADVANCED — specialized patterns
────────────────────────────────
    16 — Async batch executor (bounded fan-out)
    17 — State machine (enforced lifecycle transitions)
    18 — Hot-reload adapter (dynamic config reload at runtime)

JOB ENGINE RUNTIMES — container job execution
──────────────────────────────────────────────
    19 — Local process adapter (subprocess execution, all 9 operations)
    20 — Job engine lifecycle (submit → status → cancel → logs → cleanup)
    21 — Runtime router (multi-adapter registry, routing, health)
    22 — Spec validator (pre-flight capability & budget checks)
    23 — Workflow packager (pack/inspect/unpack .pyz archives)
"""
