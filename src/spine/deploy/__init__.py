"""deploy-spine — Container-based deployment, job execution, and service orchestration.

deploy-spine is a general-purpose container orchestrator for the Spine ecosystem.
It manages the full lifecycle of containerized workloads — from ephemeral test
harnesses that verify schema compatibility across 6 database backends to
long-running multi-service deployments with health-gated readiness.

Why This Matters — Financial Data Operations:
    SEC EDGAR ingestion operations must work identically on PostgreSQL, MySQL,
    and TimescaleDB. A schema typo that passes on SQLite can silently lose
    temporal columns on PostgreSQL. The testbed runner catches these before
    they reach production by spinning up real database containers and running
    the full test suite against each.

Why This Matters — General Operations:
    Any multi-backend application benefits from automated compatibility
    testing. deploy-spine provides a "test matrix as code" approach: define
    which databases to test, which phases to run (schema, tests, examples,
    smoke), and get structured JSON/HTML reports. The same infrastructure
    handles service deployment — from ``docker compose up`` to health checks.

Key Concepts:
    DeploymentConfig: Pydantic model controlling service deployment (targets,
        mode, profiles, compose files).
    TestbedConfig: Pydantic model configuring multi-backend verification
        (backends, phases, parallelism, timeouts).
    TestbedRunner: High-level orchestrator — config in, ``TestbedRunResult`` out.
    DeploymentRunner: Orchestrates ``docker compose`` up/down/restart/status.
    BackendSpec: Frozen dataclass for each database engine (image, ports,
        healthcheck, connection URL template).
    ServiceSpec: Frozen dataclass for each deployable service (API, worker,
        infra).
    ContainerManager: Subprocess-based Docker CLI wrapper for container
        lifecycle management.
    LogCollector: Structures output into ``{run_id}/`` directories with
        JSON summaries and HTML reports.

Architecture Decisions:
    - subprocess-only: Uses ``docker`` CLI via subprocess, not ``docker-py``,
      to keep spine-core dependency-light and avoid version-pinning issues.
    - Pydantic v2 for config and results: Enables ``from_env()`` factory,
      ``model_dump_json()``, and type-safe validation.
    - Frozen dataclasses for specs: BackendSpec and ServiceSpec are immutable
      registries — no runtime mutation.
    - PyYAML optional: Compose generation falls back to JSON (which is valid
      YAML) if PyYAML is not installed.

Related Modules:
    - :mod:`spine.deploy.config` — Configuration models
    - :mod:`spine.deploy.results` — Structured result models
    - :mod:`spine.deploy.backends` — Backend and service registries
    - :mod:`spine.deploy.container` — Docker container lifecycle
    - :mod:`spine.deploy.compose` — Dynamic compose YAML generation
    - :mod:`spine.deploy.executor` — Test and task execution
    - :mod:`spine.deploy.log_collector` — Structured log collection
    - :mod:`spine.deploy.workflow` — Workflow orchestrators
    - :mod:`spine.cli.deploy` — CLI commands (``spine-core deploy``)
    - :mod:`spine.api.routers.deploy` — REST API endpoints

Architecture::

    ┌──────────────────────────────────────────────────────────────┐
    │                   deploy-spine                                │
    ├──────────────┬──────────────┬─────────────┬──────────────────┤
    │  Deployment  │   Testbed    │   Job/Task  │   Workflow       │
    │  Targets     │   Runner     │   Executor  │   Runner         │
    ├──────────────┴──────────────┴─────────────┴──────────────────┤
    │              Container Manager (docker CLI subprocess)        │
    ├──────────────────────────────────────────────────────────────┤
    │   Compose Generator │ Log Collector │ Result Models          │
    └──────────────────────────────────────────────────────────────┘

Tags:
    deploy, containers, docker, orchestration, testbed, jobs, workflows,
    multi-backend, compose, health-check

Example:
    >>> from spine.deploy import TestbedConfig, TestbedRunner
    >>> config = TestbedConfig(backends=["sqlite"], run_tests=False)
    >>> config.run_schema
    True
"""

from __future__ import annotations

from spine.deploy.config import DeploymentConfig, TestbedConfig, TestbedSettings
from spine.deploy.results import (
    BackendResult,
    DeploymentResult,
    ExampleResult,
    JobResult,
    OverallStatus,
    SchemaResult,
    ServiceStatus,
    TestbedRunResult,
    TestResult,
)
from spine.deploy.workflow import (
    DeploymentRunner,
    TestbedRunner,
    create_deployment_workflow,
    create_testbed_workflow,
)

__all__ = [
    "BackendResult",
    "DeploymentConfig",
    "DeploymentResult",
    "DeploymentRunner",
    "ExampleResult",
    "JobResult",
    "OverallStatus",
    "SchemaResult",
    "ServiceStatus",
    "TestbedConfig",
    "TestbedRunResult",
    "TestbedRunner",
    "TestbedSettings",
    "TestResult",
    "create_deployment_workflow",
    "create_testbed_workflow",
]
