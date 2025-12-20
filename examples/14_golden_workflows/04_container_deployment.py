"""Container Deployment — same workflow running in Docker/Podman.

Demonstrates how to take any ManagedWorkflow and deploy it as a
containerized service using spine-core's deploy module:

    1. Define the workflow (plain Python functions)
    2. Generate a docker-compose.yml programmatically
    3. Run the testbed lifecycle (start → health → execute → teardown)
    4. Collect logs and results as structured JSON

The key insight: you write the workflow ONCE, then deploy it via:
    - SDK: wf.run()
    - CLI: spine-core deploy testbed --backend sqlite
    - Container: docker compose up (with generated compose file)

Spine modules used:
    - spine.deploy.compose    — generate_testbed_compose, generate_deployment_compose
    - spine.deploy.backends   — BackendSpec, BACKENDS registry
    - spine.deploy.config     — TestbedConfig
    - spine.deploy.results    — TestbedRunResult, BackendResult
    - spine.deploy.container  — ContainerManager
    - spine.deploy.workflow   — TestbedRunner
    - spine.orchestration     — ManagedWorkflow

Tier: Basic (spine-core only — Docker not required for this demo)
"""

from __future__ import annotations

import json
from typing import Any

# ═══════════════════════════════════════════════════════════════════════
# SECTION 1 — Backend Registry: what databases are supported
# ═══════════════════════════════════════════════════════════════════════
#
# spine-core ships with backend specs for PostgreSQL, MySQL, SQLite,
# and more.  Each spec defines image, port, health check, and connection URL.

from spine.deploy.backends import BACKENDS, BackendSpec, get_backend

print("=" * 72)
print("CONTAINER DEPLOYMENT PATTERNS")
print("=" * 72)

print("\n── Section 1: Backend Registry ─────────────────────────")
print(f"  Registered backends: {len(BACKENDS)}")
for name, spec in BACKENDS.items():
    print(f"    {name:15s} → image={spec.image or 'in-process':30s} port={spec.port or 'N/A'}")


# ═══════════════════════════════════════════════════════════════════════
# SECTION 2 — Compose Generation: dynamic docker-compose.yml
# ═══════════════════════════════════════════════════════════════════════
#
# generate_testbed_compose() creates a compose file from BackendSpecs.
# No hand-maintained YAML — the backend registry is the source of truth.

from spine.deploy.compose import generate_testbed_compose, generate_deployment_compose
from spine.deploy.backends import SERVICES

print("\n── Section 2: Compose Generation ───────────────────────")

# Generate a testbed compose for PostgreSQL + SQLite testing
backend_specs = [BACKENDS[b] for b in ["postgresql", "sqlite"] if b in BACKENDS]
testbed_yaml = generate_testbed_compose(
    backends=backend_specs,
    run_id="golden-workflow-test-001",
)

print(f"  Generated testbed compose ({len(testbed_yaml)} chars):")
# Show first 20 lines
for i, line in enumerate(testbed_yaml.split("\n")[:20]):
    print(f"    {line}")
if testbed_yaml.count("\n") > 20:
    print(f"    ... ({testbed_yaml.count(chr(10)) - 20} more lines)")

# Generate a deployment compose with services
service_specs = [SERVICES["spine-core-api"], SERVICES["postgres"]]
deploy_yaml = generate_deployment_compose(
    services=service_specs,
    run_id="golden-deploy-001",
    extra_env={
        "SPINE_LOG_LEVEL": "INFO",
        "SPINE_DB_URL": "postgresql://spine:spine@db:5432/spine",
    },
)

print(f"\n  Generated deployment compose ({len(deploy_yaml)} chars):")
for i, line in enumerate(deploy_yaml.split("\n")[:15]):
    print(f"    {line}")


# ═══════════════════════════════════════════════════════════════════════
# SECTION 3 — TestbedConfig: configure a testbed run
# ═══════════════════════════════════════════════════════════════════════
#
# TestbedConfig defines what to test, where to output, and how to run.

from spine.deploy.config import TestbedConfig

print("\n── Section 3: TestbedConfig ────────────────────────────")

config = TestbedConfig(
    backends=["sqlite"],  # Use in-process for this demo
    run_id="golden-workflow-demo",
    run_tests=True,
    run_schema=True,
    keep_containers=False,  # Auto-cleanup
    parallel=False,
    output_format="json",
)

print(f"  Run ID    : {config.run_id}")
print(f"  Backends  : {config.backends}")
print(f"  Tests     : {config.run_tests}")
print(f"  Schema    : {config.run_schema}")
print(f"  Parallel  : {config.parallel}")
print(f"  Cleanup   : {not config.keep_containers}")


# ═══════════════════════════════════════════════════════════════════════
# SECTION 4 — TestbedRunResult: structured output
# ═══════════════════════════════════════════════════════════════════════
#
# Results are structured Python objects, not log parsing.
# BackendResult has: backend, status, schema_result, tests, timing.

from spine.deploy.results import BackendResult, OverallStatus, TestbedRunResult

print("\n── Section 4: Result Models ────────────────────────────")

# Simulated result (in real usage, TestbedRunner.run() returns this)
demo_result = TestbedRunResult(run_id="golden-workflow-demo")
demo_result.backends = [
    BackendResult(
        backend="sqlite",
        image="",
        overall_status=OverallStatus.PASSED,
        startup_ms=0.0,
        connection_url="sqlite:///test.db",
    ),
    BackendResult(
        backend="postgresql",
        image="postgres:16-alpine",
        overall_status=OverallStatus.PASSED,
        startup_ms=1234.5,
        connection_url="postgresql://spine:spine@localhost:10432/spine",
        container_id="abc123def456",
        container_name="testbed-postgresql",
    ),
]
demo_result.mark_complete()

print(f"  Run ID  : {demo_result.run_id}")
print(f"  Summary : {demo_result.summary}")
print(f"  Backends:")
for br in demo_result.backends:
    print(f"    {br.backend}: status={br.overall_status.value}, startup={br.startup_ms:.0f}ms")


# ═══════════════════════════════════════════════════════════════════════
# SECTION 5 — Workflow + Deploy integration
# ═══════════════════════════════════════════════════════════════════════
#
# The deploy module creates spine.orchestration.Workflow objects that
# wrap TestbedRunner — enabling scheduling, history, and retry.

from spine.orchestration.managed_workflow import ManagedWorkflow

print("\n── Section 5: Workflow → Container integration ────────")


def deploy_check_environment(**kwargs: Any) -> dict[str, Any]:
    """Step 1: Verify deployment prerequisites."""
    import shutil
    docker_available = shutil.which("docker") is not None
    podman_available = shutil.which("podman") is not None

    return {
        "docker_available": docker_available,
        "podman_available": podman_available,
        "container_runtime": "docker" if docker_available else "podman" if podman_available else "none",
    }


def deploy_generate_compose(**kwargs: Any) -> dict[str, Any]:
    """Step 2: Generate compose files for deployment."""
    backends = kwargs.get("backends", ["sqlite"])

    testbed = generate_testbed_compose(backends=backends, run_id="deploy-demo")

    return {
        "compose_generated": True,
        "compose_bytes": len(testbed),
        "backends": backends,
    }


def deploy_validate_schema(**kwargs: Any) -> dict[str, Any]:
    """Step 3: Validate database schema (pre-deploy check)."""
    from spine.core.connection import create_connection

    conn, info = create_connection(init_schema=True)

    # Verify core tables exist
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'core_%'"
    )
    tables = [row[0] for row in cursor.fetchall()]

    return {
        "schema_valid": len(tables) >= 5,
        "tables_found": len(tables),
        "backend": info.backend,
    }


def deploy_summary(**kwargs: Any) -> dict[str, Any]:
    """Step 4: Generate deployment summary."""
    return {
        "deployment_ready": True,
        "steps_completed": ["check_env", "generate_compose", "validate_schema"],
        "next_action": "docker compose up -d",
    }


wf = (
    ManagedWorkflow("golden.container_deploy")
    .step("check_env", deploy_check_environment)
    .step("gen_compose", deploy_generate_compose, config={"backends": ["sqlite", "postgresql"]})
    .step("validate_schema", deploy_validate_schema)
    .step("summary", deploy_summary)
    .build()
)

result = wf.run()
wf.show()


# ═══════════════════════════════════════════════════════════════════════
# SECTION 6 — CLI equivalents
# ═══════════════════════════════════════════════════════════════════════
#
# Everything above is also available via CLI:
#
#   # Run testbed against all backends
#   spine-core deploy testbed --backend all
#
#   # Run testbed against specific backends
#   spine-core deploy testbed --backend postgresql --backend mysql
#
#   # Start services
#   spine-core deploy up --profile standard
#
#   # Check status
#   spine-core deploy status
#
#   # View logs
#   spine-core deploy logs --service api --tail 50
#
#   # Teardown
#   spine-core deploy down
#
# These CLI commands call the same deploy module code shown above.

print("\n── Section 6: CLI Equivalents ──────────────────────────")
print("""
  CLI commands that map to the code above:

    spine-core deploy testbed --backend sqlite postgresql
    spine-core deploy up --profile standard
    spine-core deploy status
    spine-core deploy logs --service api
    spine-core deploy down

  Docker/Podman commands using generated compose:

    # Generate compose file
    spine-core deploy compose --backend postgresql --output docker-compose.generated.yml

    # Run with Docker
    docker compose -f docker-compose.generated.yml up -d

    # Run with Podman
    podman compose -f docker-compose.generated.yml up -d

  Same workflow, three deployment targets:

    SDK    → wf.run()                              (in-process)
    CLI    → spine-core deploy testbed              (local containers)
    CI/CD  → docker compose up                      (generated compose)
""")


# ═══════════════════════════════════════════════════════════════════════
# RECAP
# ═══════════════════════════════════════════════════════════════════════

print("=" * 72)
print("CONTAINER DEPLOYMENT — COMPLETE")
print("=" * 72)
print("""
  Deploy building blocks:

    BackendSpec           → Registry of supported databases
    generate_*_compose()  → Dynamic docker-compose.yml generation
    TestbedConfig         → Configure what/how to test
    TestbedRunner         → Full lifecycle: start → health → test → teardown
    TestbedRunResult      → Structured output (not log parsing)
    ContainerManager      → Direct container lifecycle (Docker/Podman/Colima)

  Zero-friction deployment:
    1. Write workflow as plain Python functions
    2. Wrap in ManagedWorkflow for persistence
    3. Generate compose files from backend registry
    4. Deploy with docker/podman compose
    5. Same CLI commands work everywhere
""")

wf.close()
