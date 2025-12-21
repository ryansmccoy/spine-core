"""Core primitives — Result pattern, errors, temporal, quality, idempotency, hashing, tagging.

The core module provides the foundational building blocks that every
other spine layer depends on: explicit Result types, structured errors,
temporal primitives, data-quality gates, caching, versioning, and
domain-specific finance utilities.

Examples are grouped into six logical sections.  Read top-to-bottom
for a progressive tour, or jump to a section by number.

RESULTS & ERRORS — explicit success/failure handling
─────────────────────────────────────────────────────
    01 — Result pattern (Ok/Err instead of exceptions)
    02 — Error handling (structured error types, retry decisions)
    03 — Advanced errors (SpineError hierarchy, error chaining)
    04 — Reject handling (capture validation failures without stopping)

TEMPORAL & WINDOWS — time-aware data primitives
────────────────────────────────────────────────
    05 — WeekEnding (Friday-anchored fiscal periods)
    06 — Temporal envelope (PIT-correct bi-temporal records)
    07 — Rolling windows (time-series aggregations)
    08 — Watermark tracking (cursor-based incremental progress)

DATA QUALITY — validation and correctness
──────────────────────────────────────────
    09 — Quality checks (automated data validation)
    10 — Idempotency (safe, re-runnable operations)
    11 — Anomaly recording (structured anomaly tracking)
    12 — Content hashing (deduplication via deterministic hashing)

LIFECYCLE & TRACKING — execution context and state
───────────────────────────────────────────────────
    13 — Execution context (lineage, correlation IDs)
    14 — Work manifest (stage tracking for operations)
    15 — Backfill planning (checkpoint-based backfill)
    16 — Cache backends (tiered caching with swappable protocols)

CONTENT & VERSIONING — immutable data management
─────────────────────────────────────────────────
    17 — Versioned content (immutable version history)
    18 — Domain primitives (enums, timestamps, shared types)
    19 — Tagging (multi-dimensional faceted search)
    20 — Asset tracking (Dagster-inspired data artifacts)

FINANCE & CONFIG — domain-specific utilities
─────────────────────────────────────────────
    21 — Finance adjustments (factor-based per-share math)
    22 — Finance corrections (observation-change taxonomy)
    23 — Feature flags (runtime toggling with env overrides)
    24 — Secrets resolver (pluggable credential management)
"""
