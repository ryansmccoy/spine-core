#!/usr/bin/env python3
"""Container Lifecycle — Docker container management patterns.

The ContainerManager handles starting, health-waiting, stopping,
and cleaning up database and service containers via the ``docker``
CLI (subprocess). This example demonstrates the full API without
requiring Docker — it probes availability, shows command construction,
and simulates the lifecycle.

Demonstrates:
    1. Docker availability detection
    2. ContainerInfo data model
    3. Backend container start parameters (command construction)
    4. Service container start parameters
    5. Network isolation per run
    6. Health-check polling with exponential backoff
    7. Label-based orphan cleanup
    8. Graceful degradation when Docker is absent

Architecture:
    ContainerManager
        ├── is_docker_available()     ← static check
        ├── create_network(run_id)
        ├── start_backend(spec, run_id)
        │       ├── docker run --detach ... ← subprocess
        │       ├── _get_mapped_port()
        │       └── _wait_for_healthy()     ← exponential backoff
        ├── start_service(spec, run_id)
        ├── stop_container(info)
        ├── collect_logs(info)
        └── cleanup_orphans()

Key Concepts:
    - **ContainerInfo**: Dataclass with container_id, host, port, network,
      connection_url, started_at. Has ``uptime_seconds`` property.
    - **Label-based tracking**: Every container gets ``spine.deploy.*``
      labels so cleanup can find them.
    - **DockerNotFoundError**: Raised when ``docker`` is not on PATH.
    - **ContainerStartError**: Raised when health timeout is exceeded.

See Also:
    - ``02_backend_registry.py`` — BackendSpec consumed by ContainerManager
    - ``04_testbed_workflow.py`` — TestbedRunner orchestrates containers
    - ``spine.deploy.container`` — Full source

Run:
    python examples/12_deploy/09_container_lifecycle.py

Expected Output:
    Docker availability check, ContainerInfo demo, command construction
    details, and lifecycle simulation.
"""

import time

from spine.deploy.backends import (
    BACKENDS,
    SERVICES,
    get_backend,
    get_service,
)
from spine.deploy.container import (
    ContainerInfo,
    ContainerManager,
    ContainerStartError,
    DockerNotFoundError,
)


def main() -> None:
    """Demonstrate container lifecycle management."""

    print("=" * 60)
    print("Deploy-Spine — Container Lifecycle")
    print("=" * 60)

    # --- 1. Docker availability ---
    print("\n--- 1. Docker Availability ---")
    docker_available = ContainerManager.is_docker_available()
    print(f"  Docker available : {docker_available}")
    if not docker_available:
        print("  (Container operations will be simulated)")

    # --- 2. ContainerInfo data model ---
    print("\n--- 2. ContainerInfo Data Model ---")
    info = ContainerInfo(
        container_id="abc123def456",
        container_name="spine-testbed-postgresql-a1b2c3d4",
        host="localhost",
        port=5432,
        internal_port=5432,
        network="spine-testbed-a1b2c3d4",
        image="postgres:16.4-alpine",
        image_digest="sha256:abc123...",
        connection_url="postgresql://spine:spine@localhost:5432/spine",
        started_at=time.time() - 30,  # 30 seconds ago
        labels={
            "spine.deploy.run_id": "a1b2c3d4",
            "spine.deploy.backend": "postgresql",
            "spine.deploy.type": "backend",
        },
    )

    print(f"  container_id     : {info.container_id}")
    print(f"  container_name   : {info.container_name}")
    print(f"  host:port        : {info.host}:{info.port}")
    print(f"  internal_port    : {info.internal_port}")
    print(f"  network          : {info.network}")
    print(f"  image            : {info.image}")
    print(f"  connection_url   : {info.connection_url}")
    print(f"  uptime_seconds   : {info.uptime_seconds:.1f}s")
    print(f"  labels           : {len(info.labels)} labels")

    # --- 3. Backend container command construction ---
    print("\n--- 3. Backend Start Parameters ---")
    run_id = "demo-run-12345678"
    for name in ["postgresql", "mysql", "db2"]:
        spec = get_backend(name)
        container_name = f"spine-testbed-{spec.name}-{run_id[:8]}"
        network = f"spine-testbed-{run_id[:8]}"

        print(f"\n  [{spec.name}]")
        print(f"    container  : {container_name}")
        print(f"    network    : {network}")
        print(f"    image      : {spec.image}")
        print(f"    port       : {spec.port}")
        print(f"    env vars   : {len(spec.env)} ({', '.join(spec.env.keys())})")
        print(f"    healthcheck: {' '.join(spec.healthcheck_cmd)}")
        print(f"    timeout    : {spec.startup_timeout}s")

        # Show the docker run command that would be constructed
        cmd_parts = ["docker", "run", "--detach"]
        cmd_parts.extend(["--name", container_name])
        cmd_parts.extend(["--network", network])
        for k, v in spec.env.items():
            cmd_parts.extend(["--env", f"{k}={v}"])
        cmd_parts.append(spec.image)
        # Truncate for display
        cmd_str = " ".join(cmd_parts)
        if len(cmd_str) > 100:
            cmd_str = cmd_str[:97] + "..."
        print(f"    command    : {cmd_str}")

    # --- 4. Service container parameters ---
    print("\n--- 4. Service Start Parameters ---")
    for name in ["spine-core-api", "postgres", "redis"]:
        svc = get_service(name)
        container_name = f"spine-deploy-{svc.name}-{run_id[:8]}"
        print(f"\n  [{svc.name}]")
        print(f"    container  : {container_name}")
        print(f"    image      : {svc.image}")
        print(f"    port       : {svc.port} → {svc.internal_port}")
        print(f"    profiles   : {svc.compose_profiles}")
        if svc.healthcheck_url:
            print(f"    healthcheck: curl {svc.healthcheck_url}")

    # --- 5. Network isolation ---
    print("\n--- 5. Network Isolation ---")
    run_ids = ["abc12345", "def67890", "ghi11111"]
    for rid in run_ids:
        network = f"spine-testbed-{rid[:8]}"
        print(f"  Run {rid[:8]} → network: {network}")
    print("  Each run gets its own bridge network for DNS isolation.")
    print("  Containers resolve each other by name within the network.")

    # --- 6. Health polling strategy ---
    print("\n--- 6. Health Polling (Exponential Backoff) ---")
    delay = 1.0
    max_delay = 5.0
    total_time = 0.0
    for attempt in range(1, 9):
        total_time += delay
        print(f"  Attempt {attempt}: wait {delay:.1f}s (cumulative: {total_time:.1f}s)")
        delay = min(delay * 2, max_delay)
    print(f"  Strategy: double delay each attempt, cap at {max_delay}s")

    # --- 7. Error handling patterns ---
    print("\n--- 7. Error Handling ---")

    # DockerNotFoundError
    print("  DockerNotFoundError:")
    print("    Raised when docker CLI is not on PATH")
    print("    → Use ContainerManager.is_docker_available() to check first")

    # ContainerStartError
    print("  ContainerStartError:")
    print("    Raised when container fails to start or health times out")
    print("    → Captures last 20 lines of container logs for diagnosis")

    # Graceful fallback
    print("  Graceful fallback:")
    print("    Use --backend sqlite for zero-Docker testing")

    # --- 8. Lifecycle simulation ---
    print("\n--- 8. Lifecycle Simulation ---")
    phases = [
        ("validate",      "Check Docker is available"),
        ("create_network", "Create isolated bridge network"),
        ("start_backend",  "docker run --detach + healthcheck"),
        ("wait_healthy",   "Poll health with exponential backoff"),
        ("run_workloads",  "Schema verification + tests + examples"),
        ("collect_logs",   "docker logs --timestamps → file"),
        ("stop_container", "docker stop + docker rm"),
        ("remove_network", "docker network rm"),
    ]
    for i, (phase, desc) in enumerate(phases, 1):
        icon = "✓" if i <= 8 else " "
        print(f"  {icon} {i}. {phase:20s} — {desc}")

    # --- 9. Cleanup patterns ---
    print("\n--- 9. Orphan Cleanup ---")
    print("  ContainerManager.cleanup_orphans() finds containers by label:")
    print(f"    Label filter: spine.deploy.type")
    print(f"    Network filter: spine-testbed-*")
    print("  Use: spine-core deploy clean")
    print("  Or:  ContainerManager().cleanup_orphans()")

    print("\n" + "=" * 60)
    print("✓ Container lifecycle demo complete.")
    print("=" * 60)


if __name__ == "__main__":
    main()
