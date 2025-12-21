"""Operations — Database lifecycle, runs, alerts, sources, processing, schedules, locks, DLQ, quality.

Operational examples show how to manage a running spine system:
database lifecycle, run management, alert routing, source CRUD,
data processing artefacts, schedule metadata, and lock/DLQ ops.

READING ORDER
─────────────
    01 — Database lifecycle (init, inspect, health-check, purge)
    02 — Run management (list, inspect, cancel, retry runs)
    03 — Workflow operations (list, inspect, run workflows)
    04 — Health & capabilities (aggregate checks, introspection)
    05 — Alert management (channels, delivery tracking)
    06 — Source management (data sources, fetches, cache)
    07 — Operation data (manifests, rejects, work items)
    08 — Schedule metadata (dependencies, expected schedules)
    09 — Locks, DLQ, quality (concurrency locks, dead letters)
    10 — Full table population (populate all 27 tables)
"""
