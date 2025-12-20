#!/usr/bin/env python3
"""Result Models — Lifecycle, aggregation, and serialisation.

The deploy result models form a hierarchy: individual test/schema
results roll up into per-backend results, which roll up into an
overall testbed or deployment result. This example explores every
result type, its lifecycle methods, and serialisation.

Demonstrates:
    1. OverallStatus enum and transitions
    2. SchemaResult — table verification outcomes
    3. TestResult — pytest execution outcomes
    4. BackendResult — aggregating sub-results with compute_status()
    5. DeploymentResult — service health tracking with mark_complete()
    6. JobResult — generic container job tracking
    7. Full serialisation round-trip

Architecture:
    SchemaResult ─┐
    TestResult ───┤
    ExampleResult ┼──▶ BackendResult ──▶ TestbedRunResult
    SmokeResult ──┘

    ServiceStatus ──▶ DeploymentResult

Key Concepts:
    - **compute_status()**: Derives PASSED/FAILED/PARTIAL from sub-results
    - **mark_complete()**: Finalises timestamps, duration, and summary
    - **OverallStatus.PARTIAL**: At least one pass and one fail

See Also:
    - ``04_testbed_workflow.py`` — Results in the context of a full run
    - ``spine.deploy.results`` — Module source

Run:
    python examples/12_deploy/05_result_models.py

Expected Output:
    Detailed result model demos with status transitions and JSON output.
"""

from spine.deploy.results import (
    BackendResult,
    DeploymentResult,
    ExampleResult,
    ExampleRun,
    JobResult,
    OverallStatus,
    SchemaResult,
    ServiceStatus,
    SmokeResult,
    TestbedRunResult,
    TestFailure,
    TestResult,
)


def main() -> None:
    """Explore every deploy result model."""

    # ═══════════════════════════════════════════════════════════
    print("=" * 60)
    print("Deploy-Spine — Result Models Deep Dive")
    print("=" * 60)

    # --- 1. OverallStatus enum ---
    print("\n--- 1. OverallStatus Enum ---")
    for status in OverallStatus:
        print(f"  {status.value:12s} ({status.name})")

    # --- 2. SchemaResult ---
    print("\n--- 2. SchemaResult ---")
    schema_pass = SchemaResult(
        backend="postgresql",
        tables_expected=23,
        tables_created=23,
        success=True,
        duration_ms=320.0,
    )
    schema_fail = SchemaResult(
        backend="mysql",
        tables_expected=23,
        tables_created=20,
        tables_missing=["core_alert_events", "core_temporal_series", "core_temporal_snapshots"],
        success=False,
        duration_ms=480.0,
        error="3 tables failed to create (charset issue)",
    )
    print(f"  Pass: {schema_pass.tables_created}/{schema_pass.tables_expected} tables, success={schema_pass.success}")
    print(f"  Fail: {schema_fail.tables_created}/{schema_fail.tables_expected} tables, missing={schema_fail.tables_missing}")

    # --- 3. TestResult ---
    print("\n--- 3. TestResult ---")
    test_pass = TestResult(
        backend="postgresql",
        passed=58,
        failed=0,
        skipped=2,
        duration_seconds=12.3,
    )
    test_fail = TestResult(
        backend="mysql",
        passed=50,
        failed=5,
        skipped=3,
        errors=1,
        duration_seconds=15.7,
        failures=[
            TestFailure(name="test_temporal_insert", message="DATETIME precision mismatch"),
            TestFailure(name="test_json_query", message="JSON_EXTRACT not supported"),
        ],
    )
    print(f"  Pass: {test_pass.total} total, success={test_pass.success}")
    print(f"  Fail: {test_fail.total} total, success={test_fail.success}")
    print(f"  Failures:")
    for f in test_fail.failures:
        print(f"    • {f.name}: {f.message}")

    # --- 4. BackendResult with compute_status() ---
    print("\n--- 4. BackendResult + compute_status() ---")

    # Case: all pass
    br_pass = BackendResult(
        backend="postgresql",
        image="postgres:16-alpine",
        schema_result=schema_pass,
        tests=test_pass,
    )
    br_pass.overall_status = br_pass.compute_status()
    print(f"  All pass   → {br_pass.overall_status.value}")

    # Case: schema pass, tests fail
    br_partial = BackendResult(
        backend="mysql",
        image="mysql:8.0",
        schema_result=SchemaResult(backend="mysql", success=True, tables_expected=23, tables_created=23),
        tests=test_fail,
    )
    br_partial.overall_status = br_partial.compute_status()
    print(f"  Partial    → {br_partial.overall_status.value}")

    # Case: error
    br_error = BackendResult(
        backend="oracle",
        image="container-registry.oracle.com/database/express:21.3.0-xe",
        error="Container failed to start: license not accepted",
    )
    br_error.overall_status = br_error.compute_status()
    print(f"  Error      → {br_error.overall_status.value}")

    # Case: no results
    br_empty = BackendResult(backend="sqlite", image="")
    br_empty.overall_status = br_empty.compute_status()
    print(f"  No results → {br_empty.overall_status.value}")

    # --- 5. ExampleResult ---
    print("\n--- 5. ExampleResult ---")
    examples = ExampleResult(
        backend="postgresql",
        total=3,
        passed=2,
        failed=1,
        results=[
            ExampleRun(name="01_quickstart.py", status="passed", duration_ms=120.0),
            ExampleRun(name="02_workflow.py", status="passed", duration_ms=340.0),
            ExampleRun(name="03_advanced.py", status="failed", error="ImportError: no module 'foo'"),
        ],
    )
    for r in examples.results:
        icon = "✓" if r.status == "passed" else "✗"
        print(f"  {icon} {r.name}: {r.status} ({r.duration_ms:.0f}ms)")

    # --- 6. DeploymentResult with mark_complete() ---
    print("\n--- 6. DeploymentResult ---")
    deploy = DeploymentResult(
        run_id="deploy-demo-001",
        mode="up",
        services=[
            ServiceStatus(name="postgresql", status="healthy", ports={"5432": 5432}),
            ServiceStatus(name="spine-core-api", status="running", ports={"12000": 12000}),
            ServiceStatus(name="redis", status="unhealthy", error="Connection refused"),
        ],
    )
    deploy.mark_complete()
    print(f"  run_id   : {deploy.run_id}")
    print(f"  status   : {deploy.overall_status.value}")
    print(f"  summary  : {deploy.summary}")
    print(f"  duration : {deploy.duration_seconds:.1f}s")
    for svc in deploy.services:
        icon = "✓" if svc.status in ("running", "healthy") else "✗"
        print(f"    {icon} {svc.name}: {svc.status}")

    # --- 7. JobResult ---
    print("\n--- 7. JobResult ---")
    job = JobResult(
        job_id="migration-001",
        job_type="migration",
        metadata={"from_version": "0.4.0", "to_version": "0.5.0"},
    )
    job.mark_complete(exit_code=0)
    print(f"  job_id     : {job.job_id}")
    print(f"  job_type   : {job.job_type}")
    print(f"  status     : {job.overall_status.value}")
    print(f"  exit_code  : {job.exit_code}")
    print(f"  duration   : {job.duration_seconds:.1f}s")

    job_fail = JobResult(job_id="bad-job", job_type="script", error="Segfault")
    job_fail.mark_complete(exit_code=139)
    print(f"\n  Failed job : {job_fail.overall_status.value} (exit {job_fail.exit_code})")

    # --- 8. Serialisation round-trip ---
    print("\n--- 8. Serialisation ---")
    data = deploy.model_dump()
    restored = DeploymentResult.model_validate(data)
    assert restored.run_id == deploy.run_id
    assert restored.overall_status == deploy.overall_status
    assert len(restored.services) == len(deploy.services)
    print(f"  model_dump() keys: {sorted(data.keys())}")
    print(f"  model_validate()  : ✓ round-trip preserved")

    json_str = deploy.model_dump_json(indent=2)
    print(f"  JSON size         : {len(json_str)} bytes")

    # ═══════════════════════════════════════════════════════════
    print("\n" + "=" * 60)
    print("✓ Result models deep dive complete.")
    print("=" * 60)


if __name__ == "__main__":
    main()
