#!/usr/bin/env python3
"""Deploy Quickstart — Configuration, backends, and result models.

The deploy package provides container-based deployment and testbed
orchestration for the Spine ecosystem. This example walks through
the core building blocks without starting any containers.

Demonstrates:
    1. Creating deployment configurations with sensible defaults
    2. Creating testbed configurations for multi-backend testing
    3. Browsing the backend registry (6 database engines)
    4. Inspecting service specifications
    5. Working with result models (status, serialisation)

Architecture:
    ┌──────────────────────────────────────────────────────────┐
    │                  Configuration Layer                      │
    │  DeploymentConfig │ TestbedConfig │ TestbedSettings       │
    ├──────────────────────────────────────────────────────────┤
    │                   Backend Registry                        │
    │  POSTGRESQL │ MYSQL │ DB2 │ ORACLE │ SQLITE │ TIMESCALE  │
    ├──────────────────────────────────────────────────────────┤
    │                   Result Models                           │
    │  BackendResult │ TestbedRunResult │ DeploymentResult      │
    └──────────────────────────────────────────────────────────┘

Key Concepts:
    - **DeploymentConfig**: Controls service deployment mode and targets
    - **TestbedConfig**: Controls which backends to test and how
    - **BackendSpec**: Immutable spec for a database container
    - **OverallStatus**: Enum tracking PASSED/FAILED/PARTIAL/ERROR

See Also:
    - ``02_backend_registry.py`` — Deep dive into backend specifications
    - ``03_compose_generation.py`` — Dynamic docker-compose YAML creation
    - ``spine.deploy.config`` — Configuration module

Run:
    python examples/12_deploy/01_quickstart.py

Expected Output:
    Configuration summaries, backend listing, and result model demos.
"""

from spine.deploy.config import DeploymentConfig, DeploymentMode, TestbedConfig, TestbedSettings
from spine.deploy.backends import (
    BACKENDS,
    CONTAINER_BACKENDS,
    FREE_BACKENDS,
    SERVICES,
    get_backend,
    get_backends,
)
from spine.deploy.results import (
    BackendResult,
    DeploymentResult,
    OverallStatus,
    SchemaResult,
    ServiceStatus,
    TestbedRunResult,
    TestResult,
)


def main() -> None:
    """Walk through deploy-spine core building blocks."""

    # ═══════════════════════════════════════════════════════════
    # Section 1: DeploymentConfig
    # ═══════════════════════════════════════════════════════════
    print("=" * 60)
    print("Deploy-Spine — Quickstart")
    print("=" * 60)

    print("\n--- 1. DeploymentConfig ---")
    config = DeploymentConfig(
        targets=["spine-core-api", "postgresql"],
        mode=DeploymentMode.UP,
        profile="apps",
        timeout_seconds=600,
    )
    print(f"  targets        : {config.targets}")
    print(f"  mode           : {config.mode.value}")
    print(f"  profile        : {config.profile}")
    print(f"  timeout        : {config.timeout_seconds}s")
    print(f"  run_id         : {config.run_id} (auto-generated)")
    print(f"  detach         : {config.detach}")
    print(f"  remove_orphans : {config.remove_orphans}")

    # ═══════════════════════════════════════════════════════════
    # Section 2: TestbedConfig
    # ═══════════════════════════════════════════════════════════
    print("\n--- 2. TestbedConfig ---")
    testbed = TestbedConfig(
        backends=["postgresql", "mysql"],
        run_tests=True,
        run_schema=True,
        run_examples=False,
        parallel=True,
        max_parallel=4,
    )
    print(f"  backends       : {testbed.backends}")
    print(f"  run_schema     : {testbed.run_schema}")
    print(f"  run_tests      : {testbed.run_tests}")
    print(f"  parallel       : {testbed.parallel}")
    print(f"  max_parallel   : {testbed.max_parallel}")
    print(f"  run_id         : {testbed.run_id} (auto-generated)")
    print(f"  output_format  : {testbed.output_format}")

    # ═══════════════════════════════════════════════════════════
    # Section 3: Backend Registry
    # ═══════════════════════════════════════════════════════════
    print("\n--- 3. Backend Registry ---")
    print(f"  All backends ({len(BACKENDS)}):")
    for name, spec in BACKENDS.items():
        license_note = " [requires license]" if spec.requires_license else ""
        print(f"    {name:15s} → {spec.image or '(in-process)'}{license_note}")

    print(f"\n  Container backends ({len(CONTAINER_BACKENDS)}):")
    for name in CONTAINER_BACKENDS:
        print(f"    {name}")

    print(f"\n  Free backends ({len(FREE_BACKENDS)}):")
    for name in FREE_BACKENDS:
        print(f"    {name}")

    # Lookup by name
    pg = get_backend("postgresql")
    print(f"\n  Lookup 'postgresql':")
    print(f"    dialect   : {pg.dialect}")
    print(f"    image     : {pg.image}")
    print(f"    port      : {pg.port}")
    print(f"    url       : {pg.connection_url()}")

    # ═══════════════════════════════════════════════════════════
    # Section 4: Service Registry
    # ═══════════════════════════════════════════════════════════
    print("\n--- 4. Service Registry ---")
    print(f"  All services ({len(SERVICES)}):")
    for name, svc in SERVICES.items():
        print(f"    {name:20s} → {svc.category:10s} {svc.image}")

    # ═══════════════════════════════════════════════════════════
    # Section 5: Result Models
    # ═══════════════════════════════════════════════════════════
    print("\n--- 5. Result Models ---")

    # BackendResult with sub-results
    schema = SchemaResult(
        backend="postgresql",
        tables_expected=23,
        tables_created=23,
        success=True,
        duration_ms=450.0,
    )
    tests = TestResult(
        backend="postgresql",
        passed=58,
        failed=0,
        skipped=2,
        duration_seconds=12.5,
    )
    br = BackendResult(
        backend="postgresql",
        image="postgres:16-alpine",
        startup_ms=1200.0,
        schema_result=schema,
        tests=tests,
    )
    br.overall_status = br.compute_status()
    print(f"  BackendResult:")
    print(f"    backend  : {br.backend}")
    print(f"    status   : {br.overall_status.value}")
    print(f"    schema   : {schema.tables_created}/{schema.tables_expected} tables")
    print(f"    tests    : {tests.passed} passed, {tests.failed} failed ({tests.total} total)")

    # TestbedRunResult
    result = TestbedRunResult(run_id="demo-001", backends=[br])
    result.mark_complete()
    print(f"\n  TestbedRunResult:")
    print(f"    run_id   : {result.run_id}")
    print(f"    status   : {result.overall_status.value}")
    print(f"    duration : {result.duration_seconds:.1f}s")
    print(f"    summary  : {result.summary}")

    # DeploymentResult
    deploy_result = DeploymentResult(
        run_id="deploy-001",
        mode="up",
        services=[
            ServiceStatus(name="postgresql", status="healthy"),
            ServiceStatus(name="spine-core-api", status="running"),
        ],
    )
    deploy_result.mark_complete()
    print(f"\n  DeploymentResult:")
    print(f"    run_id   : {deploy_result.run_id}")
    print(f"    status   : {deploy_result.overall_status.value}")
    print(f"    summary  : {deploy_result.summary}")

    # Serialisation
    data = deploy_result.model_dump()
    print(f"\n  JSON keys  : {sorted(data.keys())}")

    # ═══════════════════════════════════════════════════════════
    # Section 6: TestbedSettings
    # ═══════════════════════════════════════════════════════════
    print("\n--- 6. TestbedSettings ---")
    settings = TestbedSettings()
    print(f"  enable_testbed        : {settings.enable_testbed}")
    print(f"  enable_deploy         : {settings.enable_deploy}")
    print(f"  default_backends      : {settings.default_backends}")
    print(f"  default_profile       : {settings.default_profile}")
    print(f"  results_retention     : {settings.results_retention_days} days")

    # ═══════════════════════════════════════════════════════════
    # Summary
    # ═══════════════════════════════════════════════════════════
    print("\n" + "=" * 60)
    print("✓ Quickstart complete — no containers needed.")
    print("=" * 60)


if __name__ == "__main__":
    main()
