"""Deploy — Container orchestration, testbed runs, compose generation, and result models.

The deploy layer automates database backend verification via Docker:
compose generation, container lifecycle, schema execution, and
structured CI artifact output.

Examples are grouped into four logical sections.

CONFIGURATION — setup and backends
───────────────────────────────────
    01 — Quickstart (config, backends, result models)
    02 — Backend registry (browse, filter, inspect specs)
    03 — Compose generation (build docker-compose YAML)

TESTBED — multi-backend verification
──────────────────────────────────────
    04 — Testbed workflow (multi-backend DB verification)
    05 — Result models (lifecycle, aggregation, serialisation)
    06 — Log collector (structured output, HTML reports)

INFRASTRUCTURE — environment and containers
────────────────────────────────────────────
    07 — Environment configuration (build config from env vars)
    08 — Schema executor (verify table creation on real DB)
    09 — Container lifecycle (Docker container management)

INTEGRATION — workflow and CI
──────────────────────────────
    10 — Workflow integration (deploy as a spine-core workflow)
    11 — CLI programmatic (invoke deploy commands from Python)
    12 — CI artifacts (structured output for CI pipelines)
"""
