#!/usr/bin/env python3
"""Compose Generation — Build docker-compose YAML on the fly.

deploy-spine can generate ``docker-compose.yml`` files dynamically
for testbed runs and service deployments. This avoids maintaining
hand-written compose files for every backend combination.

Demonstrates:
    1. Generating a testbed compose file for multiple backends
    2. Generating a deployment compose file for services
    3. Inspecting the generated YAML structure
    4. Writing compose files to disk (temp directory)
    5. Customising test commands and volumes

Architecture:
    BackendSpec[]  ──▶  generate_testbed_compose()   ──▶  YAML string
    ServiceSpec[]  ──▶  generate_deployment_compose() ──▶  YAML string
                                                              │
                                                              ▼
                                                     write_compose_file()

Key Concepts:
    - **generate_testbed_compose**: Creates one DB service per backend +
      a runner service that depends on all of them
    - **generate_deployment_compose**: Creates services for a full
      Spine ecosystem deployment
    - **write_compose_file**: Persists YAML to disk

See Also:
    - ``02_backend_registry.py`` — Where backend specs come from
    - ``04_testbed_workflow.py`` — Using compose in a full testbed run
    - ``spine.deploy.compose`` — Module source

Run:
    python examples/12_deploy/03_compose_generation.py

Expected Output:
    Generated YAML content and file paths.
"""

import tempfile
from pathlib import Path

from spine.deploy.backends import POSTGRESQL, MYSQL, get_backends
from spine.deploy.compose import (
    generate_testbed_compose,
    generate_deployment_compose,
    write_compose_file,
)
from spine.deploy.backends import SERVICES


def main() -> None:
    """Generate and inspect docker-compose YAML files."""

    # ═══════════════════════════════════════════════════════════
    print("=" * 60)
    print("Deploy-Spine — Compose Generation")
    print("=" * 60)

    # --- 1. Testbed compose ---
    print("\n--- 1. Testbed Compose (PostgreSQL + MySQL) ---")
    backends = [POSTGRESQL, MYSQL]
    yaml_str = generate_testbed_compose(
        backends=backends,
        run_id="demo-abc123",
        spine_image="spine-core:latest",
    )
    # Show first 40 lines
    lines = yaml_str.strip().split("\n")
    preview = "\n".join(lines[:40])
    print(f"  Generated {len(lines)} lines of YAML")
    print(f"  Preview (first 40 lines):\n")
    for line in lines[:40]:
        print(f"    {line}")
    if len(lines) > 40:
        print(f"    ... ({len(lines) - 40} more lines)")

    # --- 2. Custom test command ---
    print("\n--- 2. Custom Test Command ---")
    yaml_custom = generate_testbed_compose(
        backends=[POSTGRESQL],
        run_id="custom-001",
        spine_image="spine-core:dev",
        test_command="pytest tests/ -x --tb=short -q",
    )
    custom_lines = yaml_custom.strip().split("\n")
    print(f"  Generated {len(custom_lines)} lines with custom test command")

    # --- 3. Deployment compose ---
    print("\n--- 3. Deployment Compose ---")
    service_specs = list(SERVICES.values())[:3]  # First 3 services
    yaml_deploy = generate_deployment_compose(
        services=service_specs,
        run_id="deploy-001",
    )
    deploy_lines = yaml_deploy.strip().split("\n")
    print(f"  Generated {len(deploy_lines)} lines for deployment")
    print(f"  Preview (first 30 lines):\n")
    for line in deploy_lines[:30]:
        print(f"    {line}")
    if len(deploy_lines) > 30:
        print(f"    ... ({len(deploy_lines) - 30} more lines)")

    # --- 4. Write to disk ---
    print("\n--- 4. Write to Disk ---")
    with tempfile.TemporaryDirectory() as tmpdir:
        # Testbed
        testbed_path = Path(tmpdir) / "docker-compose.testbed.yml"
        write_compose_file(yaml_str, testbed_path)
        print(f"  Wrote testbed compose : {testbed_path.name} ({testbed_path.stat().st_size} bytes)")

        # Deployment
        deploy_path = Path(tmpdir) / "docker-compose.deploy.yml"
        write_compose_file(yaml_deploy, deploy_path)
        print(f"  Wrote deploy compose  : {deploy_path.name} ({deploy_path.stat().st_size} bytes)")

        # Verify content
        content = testbed_path.read_text()
        assert "postgresql" in content.lower() or "postgres" in content.lower()
        print(f"  ✓ Files verified (content contains backend names)")

    # --- 5. Single-backend compose ---
    print("\n--- 5. Single-Backend Compose (SQLite skipped) ---")
    from spine.deploy.backends import SQLITE
    # SQLite is in-process — no container needed
    print(f"  SQLite image: '{SQLITE.image}' (empty = in-process)")
    print(f"  SQLite port:  {SQLITE.port} (0 = no container)")

    pg_only = generate_testbed_compose(
        backends=[POSTGRESQL],
        run_id="single-001",
    )
    pg_lines = pg_only.strip().split("\n")
    print(f"  PostgreSQL-only compose: {len(pg_lines)} lines")

    # ═══════════════════════════════════════════════════════════
    print("\n" + "=" * 60)
    print("✓ Compose generation complete — no Docker required.")
    print("=" * 60)


if __name__ == "__main__":
    main()
