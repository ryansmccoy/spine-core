#!/usr/bin/env python3
"""Backend Registry — Browse, filter, and inspect database backend specs.

The deploy backend registry holds immutable ``BackendSpec`` objects for
every supported database engine. Each spec carries everything needed
to start a container, wait for readiness, and build a connection URL.

Demonstrates:
    1. Listing all registered backends with metadata
    2. Filtering by license requirements
    3. Inspecting connection URL templates and health checks
    4. Building runtime connection URLs
    5. Browsing the service registry

Architecture:
    ┌─────────────────────────────────────────────────────┐
    │              BackendSpec (frozen dataclass)          │
    │  name │ dialect │ image │ port │ healthcheck_cmd    │
    │  env │ connection_url_template │ requires_license   │
    └────────────────────┬────────────────────────────────┘
                         │
    ┌────────────────────▼────────────────────────────────┐
    │  BACKENDS dict   (6 entries)                        │
    │  SQLITE │ POSTGRESQL │ MYSQL │ DB2 │ ORACLE │ TS   │
    └─────────────────────────────────────────────────────┘

Key Concepts:
    - **BackendSpec**: Frozen dataclass — one per database engine
    - **CONTAINER_BACKENDS**: Backends that run in Docker (excludes SQLite)
    - **FREE_BACKENDS**: Open-source backends with no license restrictions
    - **ServiceSpec**: Deployable service (API, worker, infra)

See Also:
    - ``01_quickstart.py`` — Overview of configs and results
    - ``03_compose_generation.py`` — Generating compose files from specs
    - ``spine.deploy.backends`` — Module source

Run:
    python examples/12_deploy/02_backend_registry.py

Expected Output:
    Detailed backend specs, connection URLs, and health-check commands.
"""

from spine.deploy.backends import (
    BACKENDS,
    CONTAINER_BACKENDS,
    FREE_BACKENDS,
    SERVICES,
    APP_SERVICES,
    INFRA_SERVICES,
    BackendSpec,
    ServiceSpec,
    get_backend,
    get_backends,
    get_service,
    get_services_by_profile,
)


def main() -> None:
    """Explore the deploy backend and service registries."""

    # ═══════════════════════════════════════════════════════════
    print("=" * 60)
    print("Deploy-Spine — Backend Registry")
    print("=" * 60)

    # --- 1. List all backends ---
    print("\n--- 1. All Registered Backends ---")
    for name, spec in sorted(BACKENDS.items()):
        print(f"\n  [{spec.name}]")
        print(f"    dialect          : {spec.dialect}")
        print(f"    image            : {spec.image or '(no container)'}")
        print(f"    port             : {spec.port or 'N/A'}")
        print(f"    startup_timeout  : {spec.startup_timeout}s")
        print(f"    requires_license : {spec.requires_license}")
        if spec.notes:
            print(f"    notes            : {spec.notes}")

    # --- 2. Filter by license ---
    print("\n--- 2. Free vs Licensed ---")
    print(f"  Free backends ({len(FREE_BACKENDS)}):")
    for name in sorted(FREE_BACKENDS):
        print(f"    ✓ {name}")

    licensed = [n for n, s in BACKENDS.items() if s.requires_license]
    print(f"\n  Licensed backends ({len(licensed)}):")
    for name in sorted(licensed):
        print(f"    ⚠ {name}")

    # --- 3. Connection URL building ---
    print("\n--- 3. Connection URL Templates ---")
    for name, spec in sorted(BACKENDS.items()):
        if not spec.connection_url_template:
            continue
        print(f"  {name:15s} → {spec.connection_url_template}")

    print("\n  Runtime URLs (localhost defaults):")
    for name in CONTAINER_BACKENDS:
        spec = get_backend(name)
        url = spec.connection_url(host="localhost")
        print(f"    {name:15s} → {url}")

    # --- 4. Health-check commands ---
    print("\n--- 4. Health-check Commands ---")
    for name in CONTAINER_BACKENDS:
        spec = get_backend(name)
        if spec.healthcheck_cmd:
            cmd = " ".join(spec.healthcheck_cmd)
            print(f"  {name:15s} → {cmd}")

    # --- 5. Environment variables ---
    print("\n--- 5. Container Environment ---")
    for name in CONTAINER_BACKENDS:
        spec = get_backend(name)
        if spec.env:
            print(f"  [{name}]")
            for k, v in spec.env.items():
                print(f"    {k}={v}")

    # --- 6. get_backends() helper ---
    print("\n--- 6. Bulk Lookup ---")
    specs = get_backends(["postgresql", "mysql"])
    print(f"  Requested 2 backends, got {len(specs)}:")
    for s in specs:
        print(f"    {s.name} ({s.dialect})")

    # --- 7. Service registry ---
    print("\n--- 7. Service Registry ---")
    print(f"  Total services     : {len(SERVICES)}")
    print(f"  App services       : {len(APP_SERVICES)}")
    print(f"  Infra services     : {len(INFRA_SERVICES)}")

    for name, svc in sorted(SERVICES.items()):
        profiles = ", ".join(svc.compose_profiles) if svc.compose_profiles else "none"
        print(f"\n  [{svc.name}]")
        print(f"    category  : {svc.category}")
        print(f"    image     : {svc.image}")
        print(f"    profiles  : {profiles}")
        if svc.port:
            print(f"    ports     : {svc.internal_port} → {svc.port}")

    # --- 8. Profile filtering ---
    print("\n--- 8. Services by Profile ---")
    for profile in ("apps", "infra", "full"):
        svcs = get_services_by_profile(profile)
        names = [s.name for s in svcs]
        print(f"  '{profile}' ({len(svcs)}): {', '.join(names)}")

    # ═══════════════════════════════════════════════════════════
    print("\n" + "=" * 60)
    print("✓ Backend registry exploration complete.")
    print("=" * 60)


if __name__ == "__main__":
    main()
