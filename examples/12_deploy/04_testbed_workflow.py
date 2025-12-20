#!/usr/bin/env python3
"""Testbed Workflow — Multi-backend database verification.

The testbed runner orchestrates container lifecycle, test execution,
log collection, and result aggregation across multiple database
backends. This example shows the configuration, result model flow,
and reporting — without starting real containers.

Demonstrates:
    1. Configuring a testbed run with multiple backends
    2. Simulating the testbed execution phases
    3. Building result objects for each backend
    4. Computing aggregate status
    5. Generating summary reports
    6. Exploring output directory structure

Architecture:
    ┌────────────┐    ┌──────────────┐    ┌──────────────┐
    │ TestbedConfig ──▶ TestbedRunner ──▶ TestbedRunResult│
    └────────────┘    └──────┬───────┘    └──────────────┘
                             │
         ┌───────────────────┼───────────────────┐
         ▼                   ▼                   ▼
    ┌──────────┐       ┌──────────┐       ┌──────────┐
    │PostgreSQL│       │  MySQL   │       │TimescaleDB│
    │container │       │container │       │container  │
    └────┬─────┘       └────┬─────┘       └────┬─────┘
         │                   │                   │
         ▼                   ▼                   ▼
    BackendResult       BackendResult       BackendResult

Key Concepts:
    - **TestbedRunner**: High-level orchestrator (config → result)
    - **TestbedRunResult**: Aggregate result with per-backend details
    - **BackendResult.compute_status()**: Derives PASSED/FAILED from sub-results
    - **LogCollector**: Structures output into an organized directory

See Also:
    - ``01_quickstart.py`` — Config and result model basics
    - ``05_result_models.py`` — Deep dive into result lifecycle
    - ``spine.deploy.workflow`` — TestbedRunner source

Run:
    python examples/12_deploy/04_testbed_workflow.py

Expected Output:
    Simulated testbed run with per-backend results and summary.
"""

import tempfile
from pathlib import Path

from spine.deploy.config import TestbedConfig
from spine.deploy.backends import get_backend, get_backends, CONTAINER_BACKENDS
from spine.deploy.results import (
    BackendResult,
    OverallStatus,
    SchemaResult,
    TestbedRunResult,
    TestResult,
    TestFailure,
    ExampleResult,
    ExampleRun,
)
from spine.deploy.log_collector import LogCollector


def _simulate_backend_run(backend_name: str, pass_tests: bool = True) -> BackendResult:
    """Simulate running tests against a backend (no Docker needed)."""
    spec = get_backend(backend_name)

    schema = SchemaResult(
        backend=backend_name,
        tables_expected=23,
        tables_created=23 if pass_tests else 20,
        tables_missing=[] if pass_tests else ["core_alert_events", "core_alert_rules", "core_data_sources"],
        success=pass_tests,
        duration_ms=350.0,
    )

    failures = []
    if not pass_tests:
        failures.append(TestFailure(
            name="test_schema_tables",
            message="3 tables missing",
        ))

    tests = TestResult(
        backend=backend_name,
        passed=56 if pass_tests else 50,
        failed=0 if pass_tests else 3,
        skipped=2,
        duration_seconds=11.5,
        failures=failures,
    )

    br = BackendResult(
        backend=backend_name,
        image=spec.image,
        startup_ms=1500.0,
        schema_result=schema,
        tests=tests,
    )
    br.overall_status = br.compute_status()
    return br


def main() -> None:
    """Simulate a full testbed workflow."""

    # ═══════════════════════════════════════════════════════════
    print("=" * 60)
    print("Deploy-Spine — Testbed Workflow")
    print("=" * 60)

    # --- 1. Configure ---
    print("\n--- 1. Testbed Configuration ---")
    config = TestbedConfig(
        backends=["postgresql", "mysql", "timescaledb"],
        run_tests=True,
        run_schema=True,
        run_examples=False,
        parallel=True,
        timeout_seconds=900,
    )
    print(f"  backends         : {config.backends}")
    print(f"  run_schema       : {config.run_schema}")
    print(f"  run_tests        : {config.run_tests}")
    print(f"  parallel         : {config.parallel}")
    print(f"  timeout          : {config.timeout_seconds}s")
    print(f"  output_format    : {config.output_format}")

    # --- 2. Simulate backend runs ---
    print("\n--- 2. Per-Backend Results ---")
    backend_results = [
        _simulate_backend_run("postgresql", pass_tests=True),
        _simulate_backend_run("mysql", pass_tests=True),
        _simulate_backend_run("timescaledb", pass_tests=False),  # Simulate partial failure
    ]

    for br in backend_results:
        status_icon = "✓" if br.overall_status == OverallStatus.PASSED else "✗"
        print(f"\n  [{br.backend}] {status_icon} {br.overall_status.value}")
        print(f"    image      : {br.image}")
        print(f"    startup    : {br.startup_ms:.0f}ms")
        if br.schema_result:
            print(f"    schema     : {br.schema_result.tables_created}/{br.schema_result.tables_expected} tables")
            if br.schema_result.tables_missing:
                print(f"    missing    : {br.schema_result.tables_missing}")
        if br.tests:
            print(f"    tests      : {br.tests.passed} passed, {br.tests.failed} failed, {br.tests.skipped} skipped")
            for f in br.tests.failures:
                print(f"    failure    : {f.name} — {f.message}")

    # --- 3. Aggregate result ---
    print("\n--- 3. Aggregate TestbedRunResult ---")
    result = TestbedRunResult(
        run_id=config.run_id,
        backends=backend_results,
    )
    result.mark_complete()

    print(f"  run_id      : {result.run_id}")
    print(f"  status      : {result.overall_status.value}")
    print(f"  duration    : {result.duration_seconds:.1f}s")
    print(f"  summary     : {result.summary}")

    # --- 4. All-pass scenario ---
    print("\n--- 4. All-Pass Scenario ---")
    all_pass = TestbedRunResult(
        run_id="all-pass-001",
        backends=[
            _simulate_backend_run("postgresql", pass_tests=True),
            _simulate_backend_run("mysql", pass_tests=True),
        ],
    )
    all_pass.mark_complete()
    print(f"  status  : {all_pass.overall_status.value}")
    print(f"  summary : {all_pass.summary}")

    # --- 5. Log collector output structure ---
    print("\n--- 5. Output Directory Structure ---")
    with tempfile.TemporaryDirectory() as tmpdir:
        collector = LogCollector(Path(tmpdir), config.run_id)

        # Create backend subdirectories
        for br in backend_results:
            bd = collector.backend_dir(br.backend)
            # Write dummy artifacts
            (bd / "schema.json").write_text('{"success": true}')
            (bd / "container.log").write_text("Starting database...")

        # Write summary
        collector.write_summary(result)

        # Show structure
        print(f"  Output root: {collector.run_dir.name}/")
        for item in sorted(collector.run_dir.rglob("*")):
            rel = item.relative_to(collector.run_dir)
            prefix = "  " if item.is_dir() else "  "
            icon = "📁" if item.is_dir() else "📄"
            size = f" ({item.stat().st_size} bytes)" if item.is_file() else ""
            print(f"    {icon} {rel}{size}")

    # --- 6. Serialisation ---
    print("\n--- 6. Serialisation ---")
    data = result.model_dump()
    print(f"  Top-level keys: {sorted(data.keys())}")
    print(f"  Backends count: {len(data['backends'])}")
    print(f"  First backend : {data['backends'][0]['backend']}")

    # ═══════════════════════════════════════════════════════════
    print("\n" + "=" * 60)
    print("✓ Testbed workflow simulation complete.")
    print("=" * 60)


if __name__ == "__main__":
    main()
