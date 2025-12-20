"""Golden Workflows — end-to-end "golden path" workflow patterns.

These examples demonstrate complete production-ready workflows that
wire together all spine-core building blocks into a single run:

    DB init → verify tables → ingest data → process/aggregate →
    quality gates → summary JSON → alerts → API exposure

Each example is self-contained and runnable with zero external deps.
The same workflow definition works across CLI, SDK, and API surfaces.

READING ORDER
─────────────
    01 — Golden path complete (all 7 phases in one workflow)
    02 — Multi-stage medallion (Bronze → Silver → Gold with quality gates)
    03 — Long-running monitor (timeouts, progress tracking, concurrency)
    04 — Container deployment (same workflow running in Docker/Podman)
    05 — CLI / SDK / API parity (one workflow, three interfaces)
    06 — E2E validate everything (8-phase: init → ingest → calculate → store → verify)
"""
