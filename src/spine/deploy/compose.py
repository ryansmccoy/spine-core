"""Dynamic Docker Compose generation for deploy-spine.

Generates ``docker-compose.yml`` files on-the-fly for testbed runs
and service deployments. Eliminates hand-maintained compose files —
the backend registry is the single source of truth.

Why This Matters — Financial Data Operations:
    Running the test suite against PostgreSQL + MySQL + TimescaleDB
    requires a compose file with 3 backend services, a runner service
    with ``depends_on: service_healthy``, correct environment variables,
    and resource limits. Generating this from ``BackendSpec`` objects
    prevents copy-paste drift across compose files.

Why This Matters — General Operations:
    Any project with multiple deployment topologies (dev, CI, staging)
    benefits from generated compose files. The same ``ServiceSpec``
    registry drives ``docker compose up --profile apps`` in dev and
    the full stack in CI.

Key Concepts:
    generate_testbed_compose: Creates one DB service per backend + a
        ``testbed-runner`` service that depends on all backends.
    generate_deployment_compose: Creates services with port mappings,
        health checks, dependency ordering, and resource limits.
    write_compose_file: Persists YAML string to disk.
    _yaml_dumps: Uses PyYAML if available, else JSON (valid YAML).

Architecture Decisions:
    - YAML string output (not dict): Callers get a ready-to-write string
      with a human-readable header comment.
    - PyYAML optional: Falls back to ``json.dumps(indent=2)`` which is
      valid YAML. Keeps spine-core dependency-light.
    - Resource limits: Testbed backend containers default to 512MB / 1 CPU
      to prevent CI runners from being overwhelmed.
    - ``depends_on: service_healthy``: Runner waits for all backends to
      pass health checks before starting tests.

Related Modules:
    - :mod:`spine.deploy.backends` — Source of BackendSpec and ServiceSpec
    - :mod:`spine.deploy.workflow` — Consumes generated compose content
    - :mod:`spine.deploy.container` — Alternative to compose for direct management

Tags:
    compose, docker, yaml, generation, deployment, testbed
"""

from __future__ import annotations

import json
import logging
from typing import Any

from spine.deploy.backends import BackendSpec, ServiceSpec

logger = logging.getLogger(__name__)


def _yaml_dumps(data: dict[str, Any]) -> str:
    """Serialize dict to YAML string.

    Uses PyYAML if available, otherwise falls back to a simple
    JSON-style representation that Docker Compose accepts.
    """
    try:
        import yaml  # type: ignore[import-untyped]

        return yaml.dump(data, default_flow_style=False, sort_keys=False, allow_unicode=True)
    except ImportError:
        # Fallback: JSON is valid YAML
        return json.dumps(data, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Testbed compose generation
# ---------------------------------------------------------------------------


def generate_testbed_compose(
    backends: list[BackendSpec],
    run_id: str,
    spine_image: str = "spine-core:latest",
    test_command: str | None = None,
    output_volume: str = "testbed-results",
) -> str:
    """Generate a docker-compose YAML for a testbed run.

    Creates one service per backend database and a ``testbed-runner``
    service that depends on all backends (with ``condition: service_healthy``).

    Parameters
    ----------
    backends
        Database backend specifications.
    run_id
        Unique run identifier (used for naming).
    spine_image
        Docker image for the runner service.
    test_command
        Override the test command in the runner container.
    output_volume
        Volume name for test result artifacts.

    Returns
    -------
    str
        YAML string ready to write to a file.

    Example::

        from spine.deploy.backends import POSTGRESQL, MYSQL
        yaml_str = generate_testbed_compose([POSTGRESQL, MYSQL], "abc123")
        Path("docker-compose.testbed.yml").write_text(yaml_str)
    """
    network_name = f"spine-testbed-{run_id[:8]}"

    compose: dict[str, Any] = {
        "name": f"spine-testbed-{run_id[:8]}",
        "services": {},
        "networks": {
            network_name: {
                "driver": "bridge",
            },
        },
        "volumes": {
            output_volume: {},
        },
    }

    # Add backend services
    depends_on: dict[str, Any] = {}

    for spec in backends:
        if not spec.image:
            continue  # Skip SQLite (in-process)

        service_name = f"testbed-{spec.name}"
        service: dict[str, Any] = {
            "image": spec.image,
            "container_name": f"spine-testbed-{spec.name}-{run_id[:8]}",
            "networks": [network_name],
            "labels": [
                f"spine.deploy.run_id={run_id}",
                f"spine.deploy.backend={spec.name}",
                "spine.deploy.type=backend",
            ],
        }

        # Environment
        if spec.env:
            service["environment"] = spec.env

        # Healthcheck
        if spec.healthcheck_cmd:
            service["healthcheck"] = {
                "test": ["CMD-SHELL", " ".join(spec.healthcheck_cmd)],
                "interval": "5s",
                "timeout": "10s",
                "retries": 10,
                "start_period": "10s",
            }
            depends_on[service_name] = {"condition": "service_healthy"}
        else:
            depends_on[service_name] = {"condition": "service_started"}

        # Resource limits for CI efficiency
        service["deploy"] = {
            "resources": {
                "limits": {
                    "memory": "512M",
                    "cpus": "1.0",
                },
            },
        }

        compose["services"][service_name] = service

    # Add runner service
    runner_cmd = test_command or "spine-core testbed run --all --internal"
    compose["services"]["testbed-runner"] = {
        "image": spine_image,
        "container_name": f"spine-testbed-runner-{run_id[:8]}",
        "command": runner_cmd,
        "networks": [network_name],
        "depends_on": depends_on,
        "volumes": [
            f"{output_volume}:/app/testbed-results",
        ],
        "environment": {
            "SPINE_TESTBED_INTERNAL": "true",
            "SPINE_TESTBED_RUN_ID": run_id,
        },
        "labels": [
            f"spine.deploy.run_id={run_id}",
            "spine.deploy.type=runner",
        ],
    }

    header = (
        f"# Auto-generated by deploy-spine for testbed run {run_id}\n"
        f"# Usage: docker compose -f <this-file> up --abort-on-container-exit\n"
        f"#\n"
        f"# Backends: {', '.join(s.name for s in backends if s.image)}\n"
        f"# Run ID:   {run_id}\n\n"
    )
    return header + _yaml_dumps(compose)


# ---------------------------------------------------------------------------
# Deployment compose generation
# ---------------------------------------------------------------------------


def generate_deployment_compose(
    services: list[ServiceSpec],
    run_id: str,
    network_name: str | None = None,
    project_name: str | None = None,
    extra_env: dict[str, str] | None = None,
) -> str:
    """Generate a docker-compose YAML for a service deployment.

    Creates services with correct dependency ordering, health checks,
    port mappings, and environment configuration.

    Parameters
    ----------
    services
        Service specifications to deploy.
    run_id
        Unique deployment identifier.
    network_name
        Docker network name. Auto-generated if not provided.
    project_name
        Docker Compose project name.
    extra_env
        Additional environment variables for all services.

    Returns
    -------
    str
        YAML string ready to write to a file.
    """
    network = network_name or f"spine-deploy-{run_id[:8]}"
    project = project_name or f"spine-deploy-{run_id[:8]}"

    compose: dict[str, Any] = {
        "name": project,
        "services": {},
        "networks": {
            network: {
                "driver": "bridge",
            },
        },
        "volumes": {},
    }

    # Build service name set for dependency resolution
    service_names = {s.name for s in services}

    for spec in services:
        service: dict[str, Any] = {
            "container_name": f"spine-deploy-{spec.name}-{run_id[:8]}",
            "networks": [network],
            "labels": [
                f"spine.deploy.run_id={run_id}",
                f"spine.deploy.service={spec.name}",
                "spine.deploy.type=service",
                f"spine.deploy.category={spec.category}",
            ],
        }

        # Image or build
        if spec.build_context:
            service["build"] = {"context": f"./{spec.build_context}"}
            if spec.dockerfile:
                service["build"]["dockerfile"] = spec.dockerfile
        else:
            service["image"] = spec.image

        # Ports
        if spec.port and spec.internal_port:
            service["ports"] = [f"{spec.port}:{spec.internal_port}"]

        # Environment
        env = {**spec.env, **(extra_env or {})}
        if env:
            service["environment"] = env

        # Dependencies (only include if they're in this deployment)
        valid_deps = [d for d in spec.depends_on if d in service_names]
        if valid_deps:
            service["depends_on"] = {
                dep: {"condition": "service_healthy"} for dep in valid_deps
            }

        # Healthcheck
        if spec.healthcheck_url:
            service["healthcheck"] = {
                "test": [
                    "CMD-SHELL",
                    f"curl -f http://localhost:{spec.internal_port}{spec.healthcheck_url} || exit 1",
                ],
                "interval": "10s",
                "timeout": "5s",
                "retries": 5,
                "start_period": "30s",
            }

        # Volumes
        for vol_name, mount_path in spec.volumes.items():
            service.setdefault("volumes", []).append(f"{vol_name}:{mount_path}")
            compose["volumes"][vol_name] = {}

        # Labels from spec
        for key, value in spec.labels.items():
            service["labels"].append(f"{key}={value}")

        service["restart"] = "unless-stopped"

        compose["services"][spec.name] = service

    # Clean up empty volumes dict
    if not compose["volumes"]:
        del compose["volumes"]

    header = (
        f"# Auto-generated by deploy-spine for deployment {run_id}\n"
        f"# Project: {project}\n"
        f"# Services: {', '.join(s.name for s in services)}\n\n"
    )
    return header + _yaml_dumps(compose)


# ---------------------------------------------------------------------------
# Compose file operations
# ---------------------------------------------------------------------------


def write_compose_file(
    content: str,
    output_path: str | None = None,
    run_id: str = "",
) -> str:
    """Write compose YAML to a file.

    Parameters
    ----------
    content
        YAML content to write.
    output_path
        File path. Auto-generated if not provided.
    run_id
        Run ID for default filename.

    Returns
    -------
    str
        Path to the written file.
    """
    from pathlib import Path

    if output_path:
        path = Path(output_path)
    else:
        path = Path(f"docker-compose.deploy-{run_id[:8]}.yml")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    logger.info("compose.written", extra={"path": str(path)})
    return str(path)
