"""
Deploy router — testbed execution and service deployment via API.

Provides endpoints for programmatic deployment management and
testbed execution without the CLI.

Endpoints:
    POST   /deploy/testbed              Start a testbed run
    GET    /deploy/testbed/{run_id}     Get testbed results
    GET    /deploy/backends             List available backends
    GET    /deploy/services             List available services
    POST   /deploy/up                   Deploy services
    POST   /deploy/down                 Stop services
    GET    /deploy/status               Current deployment status

Manifesto:
    Deployment state should be queryable so CI/CD pipelines
    and operators can verify which version is running.

Tags:
    spine-core, api, deploy, version, release

Doc-Types: API_REFERENCE
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel, Field

router = APIRouter(prefix="/deploy")


# ── Request / Response Schemas ───────────────────────────────────────────


class TestbedRequest(BaseModel):
    """Request body for starting a testbed run."""

    backends: list[str] = Field(
        default=["sqlite"],
        description="Backend(s) to test. Use ['all'] for all.",
    )
    parallel: bool = Field(default=False, description="Run backends in parallel.")
    run_schema: bool = Field(default=True, description="Run schema verification.")
    run_tests: bool = Field(default=True, description="Run test suite.")
    run_examples: bool = Field(default=False, description="Run examples.")
    test_filter: str | None = Field(default=None, description="Pytest -k filter.")
    timeout: int = Field(default=600, description="Per-backend timeout seconds.")
    keep_containers: bool = Field(default=False, description="Keep containers after run.")


class DeployRequest(BaseModel):
    """Request body for deploying services."""

    targets: list[str] = Field(default=[], description="Specific services.")
    profile: str = Field(default="apps", description="Compose profile.")
    compose_files: list[str] | None = Field(default=None, description="Compose files.")
    build: bool = Field(default=False, description="Build images.")
    project_name: str | None = Field(default=None, description="Project name.")


class BackendInfo(BaseModel):
    """Backend information response."""

    name: str
    dialect: str
    image: str | None
    port: int
    requires_license: bool


class ServiceInfo(BaseModel):
    """Service information response."""

    name: str
    image: str
    port: int
    profiles: list[str]
    healthcheck_url: str | None


# ── Testbed Endpoints ────────────────────────────────────────────────────


# In-memory cache for recent runs (for simple use; production would use DB)
_recent_runs: dict[str, Any] = {}


@router.post("/testbed", status_code=202)
async def start_testbed(
    body: TestbedRequest,
    background_tasks: BackgroundTasks,
) -> dict[str, Any]:
    """Start a testbed run.

    Returns immediately with a run_id. The testbed executes
    in the background.
    """
    from spine.deploy.config import TestbedConfig
    from spine.deploy.workflow import TestbedRunner

    config = TestbedConfig(
        backends=body.backends,
        parallel=body.parallel,
        run_schema=body.run_schema,
        run_tests=body.run_tests,
        run_examples=body.run_examples,
        test_filter=body.test_filter,
        backend_timeout_seconds=body.timeout,
        keep_containers=body.keep_containers,
    )

    run_id = config.run_id

    def _execute() -> None:
        runner = TestbedRunner(config)
        result = runner.run()
        _recent_runs[run_id] = result.model_dump()

    _recent_runs[run_id] = {"status": "running", "run_id": run_id}
    background_tasks.add_task(_execute)

    return {"run_id": run_id, "status": "accepted", "backends": body.backends}


@router.get("/testbed/{run_id}")
async def get_testbed_result(run_id: str) -> dict[str, Any]:
    """Get the result of a testbed run."""
    if run_id not in _recent_runs:
        return {"error": "not_found", "run_id": run_id}
    return _recent_runs[run_id]


# ── Deploy Endpoints ─────────────────────────────────────────────────────


@router.post("/up", status_code=202)
async def deploy_up(body: DeployRequest) -> dict[str, Any]:
    """Deploy services."""
    from spine.deploy.config import DeploymentConfig, DeploymentMode
    from spine.deploy.workflow import DeploymentRunner

    config = DeploymentConfig(
        mode=DeploymentMode.UP,
        targets=body.targets,
        profile=body.profile,
        compose_files=body.compose_files,
        build=body.build,
        project_name=body.project_name,
    )

    runner = DeploymentRunner(config)
    result = runner.run()
    return result.model_dump()


@router.post("/down")
async def deploy_down(body: DeployRequest | None = None) -> dict[str, Any]:
    """Stop services."""
    from spine.deploy.config import DeploymentConfig, DeploymentMode
    from spine.deploy.workflow import DeploymentRunner

    config = DeploymentConfig(
        mode=DeploymentMode.DOWN,
        compose_files=body.compose_files if body else None,
        project_name=body.project_name if body else None,
    )

    runner = DeploymentRunner(config)
    result = runner.run()
    return result.model_dump()


@router.get("/status")
async def deploy_status() -> dict[str, Any]:
    """Check deployment status."""
    from spine.deploy.config import DeploymentConfig, DeploymentMode
    from spine.deploy.workflow import DeploymentRunner

    config = DeploymentConfig(mode=DeploymentMode.STATUS)
    runner = DeploymentRunner(config)
    result = runner.run()
    return result.model_dump()


# ── Info Endpoints ───────────────────────────────────────────────────────


@router.get("/backends")
async def list_backends() -> list[BackendInfo]:
    """List all available database backends."""
    from spine.deploy.backends import BACKENDS

    return [
        BackendInfo(
            name=name,
            dialect=spec.dialect,
            image=spec.image or None,
            port=spec.port,
            requires_license=spec.requires_license,
        )
        for name, spec in BACKENDS.items()
    ]


@router.get("/services")
async def list_services() -> list[ServiceInfo]:
    """List all available services."""
    from spine.deploy.backends import SERVICES

    return [
        ServiceInfo(
            name=name,
            image=spec.image,
            port=spec.port,
            profiles=spec.compose_profiles,
            healthcheck_url=spec.healthcheck_url,
        )
        for name, spec in SERVICES.items()
    ]
