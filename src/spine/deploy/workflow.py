"""Workflow orchestrators for deploy-spine.

Provides high-level orchestrators that coordinate the full testbed
and deployment lifecycle: validation → container startup → execution
→ log collection → teardown → result aggregation.

Why This Matters — Financial Data Pipelines:
    A testbed run against 3 backends involves 15+ operations (validate
    Docker, resolve specs, create network, start 3 containers, wait for
    health, run schema × 3, run tests × 3, collect logs × 3, tear down).
    ``TestbedRunner`` encapsulates this into a single ``run()`` call that
    returns a structured ``TestbedRunResult``.

Why This Matters — General Pipelines:
    The runner pattern separates orchestration logic from execution logic.
    ``TestbedRunner`` uses ``ContainerManager`` for containers and
    ``TestbedExecutor`` for workloads — swapping either is straightforward.

Key Concepts:
    TestbedRunner: Config → ``TestbedRunResult``. Runs backends sequentially
        or in parallel via ``ThreadPoolExecutor``. Auto-teardown unless
        ``keep_containers=True``.
    DeploymentRunner: Config → ``DeploymentResult``. Delegates to
        ``docker compose`` CLI for up/down/restart/status.
    create_testbed_workflow(): Factory that returns a ``spine.orchestration.Workflow``
        wrapping TestbedRunner — enables scheduling and history tracking.
    create_deployment_workflow(): Factory for deployment Workflows.

Architecture Decisions:
    - Sequential by default: ``parallel=True`` uses ThreadPoolExecutor
      with ``max_parallel`` cap. Thread-safe because each backend gets
      its own ContainerInfo and result object.
    - Network-per-run: All containers in a run share a bridge network
      for DNS resolution (e.g., ``testbed-postgresql`` is resolvable).
    - Teardown in finally: Containers are stopped even if tests fail.
    - Workflow factories are optional: They require ``spine.orchestration``
      which is part of spine-core but may not be installed in minimal
      deployments. ImportError is raised with a clear message.

Best Practices:
    - Use ``TestbedRunner`` for programmatic testbed runs.
    - Use ``create_testbed_workflow()`` when you need scheduling,
      history, and retry semantics from the orchestration engine.
    - Set ``keep_containers=True`` during debug sessions to inspect
      container state after test failures.

Related Modules:
    - :mod:`spine.deploy.config` — TestbedConfig and DeploymentConfig
    - :mod:`spine.deploy.container` — Container lifecycle management
    - :mod:`spine.deploy.executor` — Test and schema execution
    - :mod:`spine.deploy.log_collector` — Output collection
    - :mod:`spine.deploy.results` — TestbedRunResult and DeploymentResult
    - :mod:`spine.orchestration.workflow` — Workflow engine (optional)

Tags:
    workflow, orchestration, testbed, deployment, runner, parallel
"""

from __future__ import annotations

import logging
import time
from typing import Any

from spine.deploy.backends import BACKENDS, BackendSpec, get_backend
from spine.deploy.config import TestbedConfig
from spine.deploy.container import ContainerInfo, ContainerManager
from spine.deploy.executor import TestbedExecutor
from spine.deploy.log_collector import LogCollector
from spine.deploy.results import BackendResult, OverallStatus, TestbedRunResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Testbed Runner (high-level orchestrator)
# ---------------------------------------------------------------------------


class TestbedRunner:
    """Orchestrates a full testbed run across multiple backends.

    This is the main entry point for programmatic testbed execution.
    It coordinates container lifecycle, test execution, log collection,
    and result aggregation.

    Parameters
    ----------
    config
        Testbed configuration.

    Example::

        from spine.deploy import TestbedRunner, TestbedConfig

        config = TestbedConfig(backends=["postgresql", "mysql"])
        runner = TestbedRunner(config)
        result = runner.run()
        print(result.summary)
    """

    def __init__(self, config: TestbedConfig) -> None:
        self.config = config
        self.container_mgr = ContainerManager(
            network_prefix=config.network_prefix,
        )
        self.executor = TestbedExecutor()
        self.log_collector = LogCollector(config.output_dir, config.run_id)
        self._containers: list[tuple[BackendSpec, ContainerInfo]] = []
        self._network: str | None = None

    def run(self) -> TestbedRunResult:
        """Execute the full testbed run.

        Returns
        -------
        TestbedRunResult
            Aggregated results from all backends.
        """
        result = TestbedRunResult(run_id=self.config.run_id)

        try:
            # Phase 1: Validate
            self._validate_environment()

            # Phase 2: Resolve backend specs
            specs = self._resolve_backends()

            # Phase 3: Create network
            self._network = self.container_mgr.create_network(self.config.run_id)

            # Phase 4: Run each backend
            if self.config.parallel and len(specs) > 1:
                result.backends = self._run_parallel(specs)
            else:
                result.backends = self._run_sequential(specs)

            # Phase 5: Collect logs & generate reports
            self.log_collector.write_summary(result)
            if self.config.output_format in ("html", "all"):
                self.log_collector.write_html_report(result)

        except Exception as e:
            result.error = str(e)
            logger.error("testbed.failed", extra={"error": str(e)})

        finally:
            # Phase 6: Teardown
            if not self.config.keep_containers:
                self._teardown()
            result.mark_complete()

        logger.info("testbed.complete", extra={"summary": result.summary})
        return result

    # ------------------------------------------------------------------
    # Private methods
    # ------------------------------------------------------------------

    def _validate_environment(self) -> None:
        """Validate that Docker is available."""
        # Check if any backends need Docker
        needs_docker = any(
            b != "sqlite" for b in self.config.backends
        )
        if needs_docker and not ContainerManager.is_docker_available():
            raise RuntimeError(
                "Docker is required for container backends but is not available. "
                "Install Docker or use --backend sqlite for in-process testing."
            )

    def _resolve_backends(self) -> list[BackendSpec]:
        """Resolve backend names to specs."""
        if self.config.backends == ["all"]:
            return list(BACKENDS.values())
        return [get_backend(name) for name in self.config.backends]

    def _run_sequential(self, specs: list[BackendSpec]) -> list[BackendResult]:
        """Run backends one at a time."""
        results = []
        for spec in specs:
            result = self._run_single_backend(spec)
            results.append(result)
        return results

    def _run_parallel(self, specs: list[BackendSpec]) -> list[BackendResult]:
        """Run backends in parallel using ThreadPoolExecutor."""
        from concurrent.futures import ThreadPoolExecutor, as_completed

        results: list[BackendResult] = []
        max_workers = min(self.config.max_parallel, len(specs))

        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {
                pool.submit(self._run_single_backend, spec): spec
                for spec in specs
            }
            for future in as_completed(futures):
                spec = futures[future]
                try:
                    br = future.result(timeout=self.config.backend_timeout_seconds)
                except Exception as e:
                    br = BackendResult(
                        backend=spec.name,
                        image=spec.image,
                        error=str(e),
                        overall_status=OverallStatus.ERROR,
                    )
                results.append(br)

        return results

    def _run_single_backend(self, spec: BackendSpec) -> BackendResult:
        """Run all test phases against a single backend."""
        br = BackendResult(backend=spec.name, image=spec.image)
        start = time.time()

        try:
            # Start container (unless SQLite)
            if spec.image:
                info = self.container_mgr.start_backend(
                    spec, self.config.run_id, network=self._network,
                )
                self._containers.append((spec, info))
                br.container_id = info.container_id
                br.container_name = info.container_name
                br.startup_ms = (time.time() - start) * 1000
                connection_url = info.connection_url or spec.connection_url()
            else:
                # SQLite: in-process
                output = self.config.output_dir / self.config.run_id
                output.mkdir(parents=True, exist_ok=True)
                connection_url = f"sqlite:///{output / 'test.db'}"
                br.startup_ms = 0.0

            br.connection_url = connection_url

            # Schema verification
            if self.config.run_schema:
                br.schema_result = self.executor.run_schema_verification(
                    connection_url=connection_url,
                    dialect_name=spec.dialect,
                    schema_dir=None,
                )
                self.log_collector.save_schema_result(br.schema_result, spec.name)

            # Test suite
            if self.config.run_tests:
                br.tests = self.executor.run_test_suite(
                    connection_url=connection_url,
                    backend=spec.name,
                    test_filter=self.config.test_filter,
                    timeout=self.config.backend_timeout_seconds,
                    output_dir=self.log_collector.backend_dir(spec.name),
                )
                self.log_collector.save_test_result(br.tests, spec.name)

            # Examples
            if self.config.run_examples:
                br.examples = self.executor.run_examples(
                    connection_url=connection_url,
                    backend=spec.name,
                    categories=self.config.example_categories,
                )
                self.log_collector.save_example_result(br.examples, spec.name)

            # Collect container logs
            if br.container_name:
                self.log_collector.capture_container_logs(br.container_name, spec.name)

        except Exception as e:
            br.error = str(e)
            logger.error(
                "backend.failed",
                extra={"backend": spec.name, "error": str(e)},
            )

        br.overall_status = br.compute_status()
        return br

    def _teardown(self) -> None:
        """Stop all containers and remove network."""
        for spec, info in self._containers:
            try:
                self.container_mgr.stop_container(info)
            except Exception as e:
                logger.warning(
                    "teardown.failed",
                    extra={"container": info.container_name, "error": str(e)},
                )

        if self._network:
            try:
                self.container_mgr.remove_network(self._network)
            except Exception:
                pass

        self._containers.clear()
        self._network = None


# ---------------------------------------------------------------------------
# Deployment Runner (service-level orchestrator)
# ---------------------------------------------------------------------------


class DeploymentRunner:
    """Orchestrates service deployments.

    Manages starting, stopping, and monitoring Spine ecosystem
    services via Docker Compose or direct container management.

    Parameters
    ----------
    config
        Deployment configuration.
    """

    def __init__(self, config: Any) -> None:
        from spine.deploy.config import DeploymentConfig

        self.config: DeploymentConfig = config
        self.container_mgr = ContainerManager()

    def run(self) -> Any:
        """Execute the deployment operation."""
        from spine.deploy.results import DeploymentResult

        result = DeploymentResult(
            run_id=self.config.run_id,
            mode=self.config.mode.value,
        )

        try:
            if self.config.mode.value == "up":
                self._deploy_up(result)
            elif self.config.mode.value == "down":
                self._deploy_down(result)
            elif self.config.mode.value == "status":
                self._check_status(result)
            elif self.config.mode.value == "restart":
                self._deploy_down(result)
                self._deploy_up(result)
            else:
                result.error = f"Unknown mode: {self.config.mode}"
        except Exception as e:
            result.error = str(e)

        result.mark_complete()
        return result

    def _deploy_up(self, result: Any) -> None:
        """Start services using docker compose."""
        import subprocess

        cmd = ["docker", "compose"]

        # Add compose files
        if self.config.compose_files:
            for f in self.config.compose_files:
                cmd.extend(["-f", f])
        else:
            cmd.extend(["-f", "docker-compose.yml"])

        if self.config.project_name:
            cmd.extend(["--project-name", self.config.project_name])

        cmd.append("up")

        if self.config.build:
            cmd.append("--build")
        if self.config.detach:
            cmd.append("-d")
        if self.config.remove_orphans:
            cmd.append("--remove-orphans")

        # Profile
        if self.config.profile:
            cmd.insert(2, "--profile")
            cmd.insert(3, self.config.profile)

        # Specific services
        if self.config.targets:
            cmd.extend(self.config.targets)

        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=self.config.timeout_seconds,
        )

        if proc.returncode != 0:
            result.error = proc.stderr

        # Check status after deploy
        if self.config.wait:
            self._check_status(result)

    def _deploy_down(self, result: Any) -> None:
        """Stop services using docker compose."""
        import subprocess

        cmd = ["docker", "compose"]

        if self.config.compose_files:
            for f in self.config.compose_files:
                cmd.extend(["-f", f])
        else:
            cmd.extend(["-f", "docker-compose.yml"])

        if self.config.project_name:
            cmd.extend(["--project-name", self.config.project_name])

        cmd.append("down")

        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=self.config.timeout_seconds,
        )

        if proc.returncode != 0:
            result.error = proc.stderr

    def _check_status(self, result: Any) -> None:
        """Check status of deployed services."""
        import json as json_mod
        import subprocess

        cmd = ["docker", "compose"]

        if self.config.compose_files:
            for f in self.config.compose_files:
                cmd.extend(["-f", f])
        else:
            cmd.extend(["-f", "docker-compose.yml"])

        cmd.extend(["ps", "--format", "json"])

        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )

        if proc.returncode == 0 and proc.stdout.strip():
            from spine.deploy.results import ServiceStatus

            for line in proc.stdout.strip().splitlines():
                try:
                    data = json_mod.loads(line)
                    svc = ServiceStatus(
                        name=data.get("Service", data.get("Name", "unknown")),
                        container_id=data.get("ID", ""),
                        container_name=data.get("Name", ""),
                        image=data.get("Image", ""),
                        status=_map_compose_status(data.get("State", "")),
                    )
                    result.services.append(svc)
                except (json_mod.JSONDecodeError, KeyError):
                    pass


def _map_compose_status(state: str) -> str:
    """Map Docker Compose state to our status values."""
    state = state.lower()
    if state in ("running", "healthy"):
        return state
    if "unhealthy" in state:
        return "unhealthy"
    if "exit" in state:
        return "exited"
    if "starting" in state or "created" in state:
        return "starting"
    return "not_found"


# ---------------------------------------------------------------------------
# Workflow factory (for spine.orchestration integration)
# ---------------------------------------------------------------------------


def create_testbed_workflow(backends: list[str] | None = None) -> Any:
    """Create a spine-core Workflow that orchestrates a testbed run.

    This is a reference implementation showing how to use the
    spine-core orchestration engine for real workloads.

    Parameters
    ----------
    backends
        Backend names. Defaults to ["postgresql"].

    Returns
    -------
    Workflow
        A spine-core Workflow instance.
    """
    try:
        from spine.orchestration.step_types import Step
        from spine.orchestration.workflow import (
            ExecutionMode,
            FailurePolicy,
            Workflow,
            WorkflowExecutionPolicy,
        )
    except ImportError:
        raise ImportError("spine.orchestration is required for workflow creation")

    backends = backends or ["postgresql"]

    def validate_env(ctx: Any, config: dict[str, Any]) -> Any:
        from spine.orchestration.step_result import StepResult
        if not ContainerManager.is_docker_available():
            docker_needed = any(b != "sqlite" for b in backends)
            if docker_needed:
                return StepResult.fail("Docker is not available")
        return StepResult.ok(output={"docker_available": True})

    def run_testbed(ctx: Any, config: dict[str, Any]) -> Any:
        from spine.orchestration.step_result import StepResult
        tc = TestbedConfig(backends=backends)
        runner = TestbedRunner(tc)
        result = runner.run()
        return StepResult.ok(output={
            "summary": result.summary,
            "status": result.overall_status.value,
            "run_id": result.run_id,
        })

    steps = [
        Step.lambda_("validate_environment", validate_env),
        Step.lambda_("run_testbed", run_testbed),
    ]

    return Workflow(
        name="deploy.testbed",
        steps=steps,
        domain="spine.deploy",
        description=f"Testbed verification against {', '.join(backends)}",
        version=1,
        tags=["deploy", "testbed", "verification"],
        execution_policy=WorkflowExecutionPolicy(
            mode=ExecutionMode.SEQUENTIAL,
            timeout_seconds=1800,
            on_failure=FailurePolicy.CONTINUE,
        ),
    )


def create_deployment_workflow(
    targets: list[str] | None = None,
    profile: str = "apps",
) -> Any:
    """Create a spine-core Workflow for service deployment.

    Parameters
    ----------
    targets
        Service names to deploy.
    profile
        Docker Compose profile.

    Returns
    -------
    Workflow
    """
    try:
        from spine.orchestration.step_types import Step
        from spine.orchestration.workflow import (
            ExecutionMode,
            FailurePolicy,
            Workflow,
            WorkflowExecutionPolicy,
        )
    except ImportError:
        raise ImportError("spine.orchestration is required for workflow creation")

    def deploy_services(ctx: Any, config: dict[str, Any]) -> Any:
        from spine.deploy.config import DeploymentConfig
        from spine.orchestration.step_result import StepResult
        dc = DeploymentConfig(targets=targets or [], profile=profile)
        runner = DeploymentRunner(dc)
        result = runner.run()
        return StepResult.ok(output={
            "summary": result.summary,
            "status": result.overall_status.value,
        })

    def check_health(ctx: Any, config: dict[str, Any]) -> Any:
        from spine.deploy.config import DeploymentConfig, DeploymentMode
        from spine.orchestration.step_result import StepResult
        dc = DeploymentConfig(targets=targets or [], mode=DeploymentMode.STATUS)
        runner = DeploymentRunner(dc)
        result = runner.run()
        all_healthy = all(
            s.status in ("running", "healthy") for s in result.services
        )
        if not all_healthy:
            return StepResult.fail(f"Not all services healthy: {result.summary}")
        return StepResult.ok(output={"summary": result.summary})

    steps = [
        Step.lambda_("deploy", deploy_services),
        Step.lambda_("health_check", check_health),
    ]

    return Workflow(
        name="deploy.services",
        steps=steps,
        domain="spine.deploy",
        description=f"Deploy Spine services (profile={profile})",
        version=1,
        tags=["deploy", "services", profile],
        execution_policy=WorkflowExecutionPolicy(
            mode=ExecutionMode.SEQUENTIAL,
            timeout_seconds=600,
            on_failure=FailurePolicy.STOP,
        ),
    )
