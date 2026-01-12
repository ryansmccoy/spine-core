"""
Spine-Core Usage Examples for Intermediate Tier.

These examples demonstrate how to use spine-core primitives in the
intermediate tier context (PostgreSQL-backed with async support).

Examples:
    - error_handling: SpineError hierarchy and Result[T] pattern
    - sources: FileSource for CSV/PSV data ingestion
    - alerts: AlertChannel framework for notifications
    - workflow: Workflow orchestration v2 with data passing
    - finra_workflow: Complete FINRA pipeline example

Each example is designed to be run standalone:
    cd market-spine-intermediate
    uv run python -m examples.error_handling
"""
