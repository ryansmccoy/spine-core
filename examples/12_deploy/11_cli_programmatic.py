#!/usr/bin/env python3
"""CLI Programmatic — Invoke deploy commands from Python.

The ``spine-core deploy`` CLI exposes testbed, deployment, and info
commands via Typer. This example shows how to invoke the same
operations programmatically — useful for notebooks, scripts, and
integrating deploy-spine into larger automation.

Demonstrates:
    1. Programmatic TestbedRunner invocation (SQLite, no Docker)
    2. Inspecting results at every level (backend, schema, tests)
    3. JSON output for CI artifact generation
    4. DeploymentRunner with status-check mode
    5. CLI command reference (what each command does)
    6. Filtering test runs by backend and test name

Architecture:
    CLI:    spine-core deploy testbed --backend sqlite
    Python: TestbedRunner(TestbedConfig(backends=["sqlite"])).run()

    Both produce the same TestbedRunResult — the CLI just adds
    Rich formatting and exit code handling.

Key Concepts:
    - **TestbedRunner.run()**: Config in → TestbedRunResult out.
    - **DeploymentRunner.run()**: Config in → DeploymentResult out.
    - **result.model_dump_json()**: Produces CI-ready JSON artifact.
    - **result.overall_status**: Exit code 0 for PASSED, 1 for FAILED.

See Also:
    - ``01_quickstart.py`` — Config and result model overview
    - ``08_schema_executor.py`` — Real schema + tests execution
    - ``10_workflow_integration.py`` — Wrapping as a Workflow
    - ``spine.cli.deploy`` — CLI command source

Run:
    python examples/12_deploy/11_cli_programmatic.py

Expected Output:
    SQLite testbed run with real test results, JSON output,
    and CLI command reference.
"""

import json
from pathlib import Path

from spine.deploy.config import (
    DeploymentConfig,
    DeploymentMode,
    TestbedConfig,
)
from spine.deploy.results import OverallStatus
from spine.deploy.workflow import TestbedRunner, DeploymentRunner


def main() -> None:
    """Run deploy operations programmatically."""

    print("=" * 60)
    print("Deploy-Spine — CLI Programmatic Access")
    print("=" * 60)

    # --- 1. SQLite Testbed Run ---
    print("\n--- 1. Programmatic Testbed Run (SQLite) ---")
    config = TestbedConfig(
        backends=["sqlite"],
        run_schema=True,
        run_tests=True,
        run_examples=False,
        test_filter="test_deploy",   # Only deploy tests — fast
        parallel=False,
    )
    print(f"  backends    : {config.backends}")
    print(f"  run_id      : {config.run_id}")
    print(f"  test_filter : {config.test_filter}")

    runner = TestbedRunner(config)
    result = runner.run()

    print(f"\n  Result:")
    print(f"    status    : {result.overall_status.value}")
    print(f"    duration  : {result.duration_seconds:.1f}s")
    print(f"    summary   : {result.summary}")
    print(f"    backends  : {len(result.backends)}")

    # --- 2. Deep result inspection ---
    print("\n--- 2. Deep Result Inspection ---")
    for br in result.backends:
        print(f"\n  [{br.backend}]")
        print(f"    status       : {br.overall_status.value}")
        print(f"    startup_ms   : {br.startup_ms:.0f}")

        if br.schema_result:
            sr = br.schema_result
            print(f"    schema       : {sr.tables_created} tables in {sr.duration_ms:.0f}ms")
            if sr.tables_extra:
                print(f"    extra tables : {len(sr.tables_extra)}")

        if br.tests:
            tr = br.tests
            print(f"    tests        : {tr.passed} passed, {tr.failed} failed, {tr.skipped} skipped")
            print(f"    test_time    : {tr.duration_seconds:.1f}s")
            if tr.failures:
                for f in tr.failures:
                    print(f"    FAIL: {f.name} — {f.message}")

        if br.error:
            print(f"    error        : {br.error}")

    # --- 3. JSON output (CI artifact) ---
    print("\n--- 3. JSON Output ---")
    json_data = json.loads(result.model_dump_json())

    # Show top-level structure
    print(f"  Top-level keys: {sorted(json_data.keys())}")
    print(f"  run_id        : {json_data['run_id']}")
    print(f"  overall_status: {json_data['overall_status']}")
    print(f"  backends      : {len(json_data['backends'])} entries")

    # Show how CI would use this
    print(f"\n  CI usage:")
    print(f"    exit_code = 0 if result.overall_status == OverallStatus.PASSED else 1")
    exit_code = 0 if result.overall_status == OverallStatus.PASSED else 1
    print(f"    exit_code = {exit_code}")

    # --- 4. DeploymentRunner (status mode) ---
    print("\n--- 4. DeploymentRunner (Status Check) ---")
    deploy_cfg = DeploymentConfig(
        mode=DeploymentMode.STATUS,
        targets=[],
    )
    print(f"  mode         : {deploy_cfg.mode.value}")
    print(f"  run_id       : {deploy_cfg.run_id}")

    # Note: status check requires Docker Compose running.
    # We show the API pattern without actually calling it.
    print(f"  DeploymentRunner(config).run() → DeploymentResult")
    print(f"  result.services → list of ServiceStatus")
    print(f"  Each ServiceStatus has: name, status, container_id, image")

    # --- 5. CLI Command Reference ---
    print("\n--- 5. CLI Command Reference ---")
    commands = [
        ("deploy testbed",                     "Run testbed (default: sqlite)"),
        ("deploy testbed -b postgresql -b mysql", "Multi-backend testbed"),
        ("deploy testbed -k test_anomalies",    "Filtered test run"),
        ("deploy testbed --parallel",           "Parallel execution"),
        ("deploy testbed --keep",               "Keep containers for debugging"),
        ("deploy testbed --json",               "JSON output for CI"),
        ("deploy up",                           "Start services (docker compose up)"),
        ("deploy down",                         "Stop services"),
        ("deploy status",                       "Check service health"),
        ("deploy restart",                      "Restart services"),
        ("deploy logs",                         "Tail service logs"),
        ("deploy backends",                     "List available backends"),
        ("deploy services",                     "List available services"),
        ("deploy clean",                        "Remove orphaned containers"),
    ]

    for cmd, desc in commands:
        print(f"  spine-core {cmd:42s} # {desc}")

    # --- 6. Programmatic equivalents ---
    print("\n--- 6. CLI → Python Equivalents ---")
    equivalents = [
        (
            "spine-core deploy testbed -b postgresql",
            'TestbedRunner(TestbedConfig(backends=["postgresql"])).run()',
        ),
        (
            "spine-core deploy testbed --all",
            'TestbedRunner(TestbedConfig(backends=["all"])).run()',
        ),
        (
            "spine-core deploy backends",
            "from spine.deploy.backends import BACKENDS; print(BACKENDS)",
        ),
        (
            "spine-core deploy up --profile apps",
            'DeploymentRunner(DeploymentConfig(mode=DeploymentMode.UP, profile="apps")).run()',
        ),
    ]

    for cli_cmd, python_code in equivalents:
        print(f"  CLI:    {cli_cmd}")
        print(f"  Python: {python_code}")
        print()

    print("=" * 60)
    print("✓ CLI programmatic access complete.")
    print("=" * 60)


if __name__ == "__main__":
    main()
