"""Container lifecycle management for deploy-spine.

Manages ephemeral containers via the ``docker`` CLI (subprocess).
No ``docker-py`` dependency — spine-core stays dependency-light.

Why This Matters — Financial Data Pipelines:
    During a testbed run, the testbed runner needs to start a PostgreSQL
    container, wait until it passes health checks, run the test suite,
    collect logs, and tear it down — all in under 5 minutes. The
    ``ContainerManager`` handles this lifecycle with exponential-backoff
    health polling and automatic orphan cleanup.

Why This Matters — General Pipelines:
    Container lifecycle management via CLI subprocess is portable across
    Docker Desktop, Podman, Colima, and CI runners. No native Docker
    SDK means no version conflicts or platform-specific wheels.

Key Concepts:
    ContainerManager: Main class — ``start_backend()``, ``start_service()``,
        ``stop_container()``, ``cleanup_orphans()``.
    ContainerInfo: Runtime state of a running container (ID, name, host,
        port, connection URL, uptime).
    DockerNotFoundError: Raised when ``docker`` is not on PATH.
    ContainerStartError: Raised when a container fails to start or
        does not become healthy within the startup timeout.

Architecture Decisions:
    - subprocess, not docker-py: Avoids a heavy dependency and works with
      any container runtime exposing a ``docker`` CLI.
    - Label-based tracking: Every container gets ``spine.deploy.*`` labels
      so ``cleanup_orphans()`` can find and remove them.
    - Network isolation: Each run gets its own bridge network so backend
      containers can resolve each other by name.
    - Exponential backoff with cap: Health polling starts at 1s, doubles
      to 5s max — responsive for fast starts, patient for slow ones.

Best Practices:
    - Always call ``stop_container()`` in a ``finally`` block or use
      ``TestbedRunner`` which handles teardown automatically.
    - Use ``is_docker_available()`` before operations to fail fast.
    - Set ``keep_containers=True`` in ``TestbedConfig`` for debugging.

Related Modules:
    - :mod:`spine.deploy.backends` — BackendSpec and ServiceSpec consumed here
    - :mod:`spine.deploy.workflow` — TestbedRunner orchestrates ContainerManager
    - :mod:`spine.deploy.log_collector` — Captures logs from running containers

Tags:
    container, docker, lifecycle, subprocess, health, network, cleanup
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from typing import Any

from spine.deploy.backends import BackendSpec, ServiceSpec

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class ContainerInfo:
    """Runtime information about a running container."""

    container_id: str
    container_name: str
    host: str
    port: int
    internal_port: int
    network: str
    image: str
    image_digest: str | None = None
    connection_url: str | None = None
    started_at: float = 0.0
    labels: dict[str, str] = field(default_factory=dict)

    @property
    def uptime_seconds(self) -> float:
        return time.time() - self.started_at if self.started_at else 0.0


class DockerNotFoundError(RuntimeError):
    """Raised when Docker CLI is not available."""


class ContainerStartError(RuntimeError):
    """Raised when a container fails to start or become healthy."""


class ContainerManager:
    """Manages ephemeral containers for testing and deployment.

    Uses the ``docker`` CLI via subprocess. Docker must be installed
    and accessible on the system PATH.

    Parameters
    ----------
    network_prefix
        Prefix for Docker network names (e.g., ``spine-testbed``).
    label_prefix
        Label prefix for container identification (e.g., ``spine.deploy``).

    Example::

        mgr = ContainerManager()
        info = mgr.start_backend(POSTGRESQL, run_id="abc123")
        # ... run tests ...
        mgr.stop_container(info)
    """

    def __init__(
        self,
        network_prefix: str = "spine-deploy",
        label_prefix: str = "spine.deploy",
    ) -> None:
        self.network_prefix = network_prefix
        self.label_prefix = label_prefix
        self._docker_cmd = self._find_docker()

    # ------------------------------------------------------------------
    # Docker CLI discovery
    # ------------------------------------------------------------------

    @staticmethod
    def _find_docker() -> str:
        """Find the docker CLI binary."""
        docker = shutil.which("docker")
        if docker is None:
            raise DockerNotFoundError(
                "Docker CLI not found on PATH. Install Docker or add it to PATH.\n"
                "  - Windows: https://docs.docker.com/desktop/install/windows-install/\n"
                "  - Linux:   https://docs.docker.com/engine/install/\n"
                "  - macOS:   https://docs.docker.com/desktop/install/mac-install/"
            )
        return docker

    @staticmethod
    def is_docker_available() -> bool:
        """Check if Docker is installed and the daemon is running."""
        docker = shutil.which("docker")
        if docker is None:
            return False
        try:
            result = subprocess.run(
                [docker, "info"],
                capture_output=True,
                timeout=10,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, OSError):
            return False

    # ------------------------------------------------------------------
    # Network management
    # ------------------------------------------------------------------

    def create_network(self, run_id: str) -> str:
        """Create an isolated Docker network for a run.

        Returns the network name.
        """
        network_name = f"{self.network_prefix}-{run_id[:8]}"
        self._run_docker(
            ["network", "create", "--driver", "bridge", network_name],
            check=False,  # Ignore if already exists
        )
        logger.info("network.created", extra={"network": network_name})
        return network_name

    def remove_network(self, network_name: str) -> None:
        """Remove a Docker network (ignores errors)."""
        self._run_docker(
            ["network", "rm", network_name],
            check=False,
        )
        logger.debug("network.removed", extra={"network": network_name})

    # ------------------------------------------------------------------
    # Backend (database) containers
    # ------------------------------------------------------------------

    def start_backend(
        self,
        spec: BackendSpec,
        run_id: str,
        network: str | None = None,
    ) -> ContainerInfo:
        """Start a database backend container.

        Parameters
        ----------
        spec
            Backend specification.
        run_id
            Unique run identifier for naming.
        network
            Docker network to attach (created if None).

        Returns
        -------
        ContainerInfo
            Information about the running container.

        Raises
        ------
        ContainerStartError
            If the container fails to start or become healthy.
        """
        if not spec.image:
            raise ContainerStartError(f"Backend {spec.name!r} has no Docker image (in-process only)")

        container_name = f"spine-testbed-{spec.name}-{run_id[:8]}"
        network = network or self.create_network(run_id)

        # Build docker run command
        cmd = [
            "run", "--detach",
            "--name", container_name,
            "--network", network,
            "--label", f"{self.label_prefix}.run_id={run_id}",
            "--label", f"{self.label_prefix}.backend={spec.name}",
            "--label", f"{self.label_prefix}.type=backend",
        ]

        # Environment variables
        for key, value in spec.env.items():
            cmd.extend(["--env", f"{key}={value}"])

        # Healthcheck
        if spec.healthcheck_cmd:
            cmd.extend([
                "--health-cmd", " ".join(spec.healthcheck_cmd),
                "--health-interval", "5s",
                "--health-timeout", "10s",
                "--health-retries", "10",
                "--health-start-period", "10s",
            ])

        cmd.append(spec.image)

        start_time = time.time()
        result = self._run_docker(cmd)
        container_id = result.stdout.strip()[:12]

        logger.info(
            "container.started",
            extra={"container": container_name, "image": spec.image, "backend": spec.name},
        )

        # Get mapped port
        mapped_port = self._get_mapped_port(container_name, spec.port)

        # Wait for healthy
        if spec.healthcheck_cmd:
            self._wait_for_healthy(container_name, spec.startup_timeout)

        startup_ms = (time.time() - start_time) * 1000

        # Get image digest
        image_digest = self._get_image_digest(spec.image)

        info = ContainerInfo(
            container_id=container_id,
            container_name=container_name,
            host="localhost",
            port=mapped_port,
            internal_port=spec.port,
            network=network,
            image=spec.image,
            image_digest=image_digest,
            connection_url=spec.connection_url(host="localhost", port=mapped_port),
            started_at=start_time,
        )

        logger.info(
            "backend.ready",
            extra={
                "backend": spec.name,
                "container": container_name,
                "port": mapped_port,
                "startup_ms": f"{startup_ms:.0f}",
            },
        )

        return info

    # ------------------------------------------------------------------
    # Service containers
    # ------------------------------------------------------------------

    def start_service(
        self,
        spec: ServiceSpec,
        run_id: str,
        network: str | None = None,
        extra_env: dict[str, str] | None = None,
    ) -> ContainerInfo:
        """Start a Spine service container.

        Parameters
        ----------
        spec
            Service specification.
        run_id
            Unique run identifier.
        network
            Docker network (created if None).
        extra_env
            Additional environment variables to inject.

        Returns
        -------
        ContainerInfo
        """
        container_name = f"spine-deploy-{spec.name}-{run_id[:8]}"
        network = network or self.create_network(run_id)

        cmd = [
            "run", "--detach",
            "--name", container_name,
            "--network", network,
            "--label", f"{self.label_prefix}.run_id={run_id}",
            "--label", f"{self.label_prefix}.service={spec.name}",
            "--label", f"{self.label_prefix}.type=service",
        ]

        # Port mapping
        cmd.extend(["-p", f"{spec.port}:{spec.internal_port}"])

        # Environment
        all_env = {**spec.env, **(extra_env or {})}
        for key, value in all_env.items():
            cmd.extend(["--env", f"{key}={value}"])

        # Labels
        for key, value in spec.labels.items():
            cmd.extend(["--label", f"{key}={value}"])

        # Healthcheck (HTTP-based)
        if spec.healthcheck_url:
            cmd.extend([
                "--health-cmd",
                f"curl -f http://localhost:{spec.internal_port}{spec.healthcheck_url} || exit 1",
                "--health-interval", "10s",
                "--health-timeout", "5s",
                "--health-retries", "5",
                "--health-start-period", "30s",
            ])

        cmd.append(spec.image)

        start_time = time.time()
        result = self._run_docker(cmd)
        container_id = result.stdout.strip()[:12]

        logger.info(
            "service.started",
            extra={"service": spec.name, "container": container_name, "port": spec.port},
        )

        return ContainerInfo(
            container_id=container_id,
            container_name=container_name,
            host="localhost",
            port=spec.port,
            internal_port=spec.internal_port,
            network=network,
            image=spec.image,
            started_at=start_time,
        )

    # ------------------------------------------------------------------
    # Container operations
    # ------------------------------------------------------------------

    def stop_container(self, info: ContainerInfo, timeout: int = 10) -> None:
        """Stop and remove a container."""
        self._run_docker(
            ["stop", "--time", str(timeout), info.container_name],
            check=False,
        )
        self._run_docker(
            ["rm", "--force", info.container_name],
            check=False,
        )
        logger.info("container.stopped", extra={"container": info.container_name})

    def collect_logs(self, info: ContainerInfo) -> str:
        """Capture container logs.

        Returns the log content as a string.
        """
        result = self._run_docker(
            ["logs", "--timestamps", info.container_name],
            check=False,
        )
        return result.stdout + result.stderr

    def get_container_status(self, container_name: str) -> str:
        """Get container status (running, exited, etc.)."""
        result = self._run_docker(
            ["inspect", "--format", "{{.State.Status}}", container_name],
            check=False,
        )
        return result.stdout.strip() if result.returncode == 0 else "not_found"

    def get_container_health(self, container_name: str) -> str:
        """Get container health status (healthy, unhealthy, starting)."""
        result = self._run_docker(
            ["inspect", "--format", "{{.State.Health.Status}}", container_name],
            check=False,
        )
        status = result.stdout.strip()
        return status if status and result.returncode == 0 else "unknown"

    def list_containers(self, run_id: str | None = None) -> list[dict[str, Any]]:
        """List deploy-spine containers, optionally filtered by run_id."""
        label_filter = f"{self.label_prefix}.type"
        cmd = [
            "ps", "--all",
            "--filter", f"label={label_filter}",
            "--format", "{{json .}}",
        ]
        if run_id:
            cmd.extend(["--filter", f"label={self.label_prefix}.run_id={run_id}"])

        result = self._run_docker(cmd, check=False)
        containers = []
        for line in result.stdout.strip().splitlines():
            if line.strip():
                try:
                    containers.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        return containers

    def cleanup_orphans(self) -> int:
        """Remove all deploy-spine containers and networks.

        Returns the number of containers removed.
        """
        containers = self.list_containers()
        removed = 0
        for c in containers:
            name = c.get("Names", "")
            self._run_docker(["rm", "--force", name], check=False)
            removed += 1

        # Clean up networks
        result = self._run_docker(
            ["network", "ls", "--filter", f"name={self.network_prefix}", "--format", "{{.Name}}"],
            check=False,
        )
        for network in result.stdout.strip().splitlines():
            if network.strip():
                self._run_docker(["network", "rm", network.strip()], check=False)

        if removed:
            logger.info("cleanup.complete", extra={"containers_removed": removed})
        return removed

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _run_docker(
        self,
        args: list[str],
        check: bool = True,
        timeout: int = 60,
    ) -> subprocess.CompletedProcess[str]:
        """Run a docker CLI command."""
        cmd = [self._docker_cmd, *args]
        logger.debug("docker.exec", extra={"cmd": " ".join(cmd)})
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            if check and result.returncode != 0:
                raise ContainerStartError(
                    f"Docker command failed (exit {result.returncode}): "
                    f"{' '.join(args)}\n{result.stderr}"
                )
            return result
        except subprocess.TimeoutExpired as exc:
            raise ContainerStartError(
                f"Docker command timed out after {timeout}s: {' '.join(args)}"
            ) from exc

    def _get_mapped_port(self, container_name: str, internal_port: int) -> int:
        """Get the host-mapped port for a container's internal port."""
        result = self._run_docker(
            ["port", container_name, str(internal_port)],
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            # Output format: "0.0.0.0:12345" or ":::12345"
            port_str = result.stdout.strip().split(":")[-1]
            return int(port_str)
        # Fallback: use docker inspect
        result = self._run_docker(
            [
                "inspect",
                "--format",
                f"{{{{(index (index .NetworkSettings.Ports \"{internal_port}/tcp\") 0).HostPort}}}}",
                container_name,
            ],
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            return int(result.stdout.strip())
        # If port is not mapped (network-internal only), return internal port
        return internal_port

    def _wait_for_healthy(self, container_name: str, timeout: int) -> None:
        """Poll container health until healthy or timeout.

        Uses exponential backoff: 1s, 2s, 4s, 5s (capped), ...
        """
        deadline = time.time() + timeout
        delay = 1.0
        max_delay = 5.0

        while time.time() < deadline:
            health = self.get_container_health(container_name)
            if health == "healthy":
                return
            status = self.get_container_status(container_name)
            if status == "exited":
                logs = self._run_docker(["logs", "--tail", "20", container_name], check=False)
                raise ContainerStartError(
                    f"Container {container_name} exited before becoming healthy.\n"
                    f"Last logs:\n{logs.stdout + logs.stderr}"
                )
            time.sleep(delay)
            delay = min(delay * 2, max_delay)

        raise ContainerStartError(
            f"Container {container_name} did not become healthy within {timeout}s. "
            f"Last health status: {self.get_container_health(container_name)}"
        )

    def _get_image_digest(self, image: str) -> str | None:
        """Get the digest of a pulled image."""
        result = self._run_docker(
            ["inspect", "--format", "{{index .RepoDigests 0}}", image],
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
        return None
