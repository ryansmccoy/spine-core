"""Configuration models for deploy-spine.

Provides Pydantic v2 configuration models for all deployment and testbed
operations. Every field supports override via environment variables,
making these models suitable for both programmatic and CI/CD usage.

Why This Matters — Financial Data Pipelines:
    When running nightly database compatibility checks across PostgreSQL,
    MySQL, and TimescaleDB, configuration must be externally injectable.
    CI systems set ``SPINE_TESTBED_BACKENDS=postgresql,mysql`` and
    ``SPINE_TESTBED_PARALLEL=true`` without touching code.

Why This Matters — General Pipelines:
    Pydantic-based config with ``from_env()`` classmethod gives you
    twelve-factor app configuration: defaults in code, overrides from
    env vars, and keyword overrides on top. The ``model_validator`` auto-
    generates ``run_id`` to ensure every operation is traceable.

Key Concepts:
    DeploymentConfig: Service deployment (targets, mode, profile, compose files).
        Uses ``SPINE_DEPLOY_*`` env vars via ``from_env()``.
    TestbedConfig: Multi-backend testing (backends, phases, parallelism).
        Uses ``SPINE_TESTBED_*`` env vars via ``from_env()``.
    TestbedSettings: Feature flags for embedding in SpineCoreSettings
        (enable/disable testbed, default backends, retention).
    DeploymentMode: Enum — up, down, restart, status, logs.

Architecture Decisions:
    - Pydantic v2 (not dataclass): Enables ``model_dump_json()``,
      ``model_validate()``, and ``model_validator(mode="after")`` for
      auto-generating run_id.
    - from_env() classmethod: Explicit env-var parsing rather than
      ``pydantic-settings``, keeping the dependency surface small.
    - Override precedence: kwargs > env vars > field defaults.

Related Modules:
    - :mod:`spine.deploy.workflow` — Consumers of these configs
    - :mod:`spine.deploy.backends` — Backend specs referenced by name in configs
    - :mod:`spine.deploy.results` — Result models that pair with configs

Tags:
    config, settings, pydantic, deployment, testbed, environment
"""

from __future__ import annotations

import os
import uuid
from enum import Enum
from pathlib import Path
from typing import Any, Literal

try:
    from pydantic import BaseModel, Field, model_validator
except ImportError as _exc:
    raise ImportError(
        "spine.deploy.config requires pydantic. "
        "Install it with: pip install spine-core[models]"
    ) from _exc


class DeploymentMode(str, Enum):
    """Deployment operation mode."""

    UP = "up"  # Start services
    DOWN = "down"  # Stop services
    RESTART = "restart"  # Restart services
    STATUS = "status"  # Check service status
    LOGS = "logs"  # Stream/collect logs


class ServiceCategory(str, Enum):
    """Category of deployable service."""

    INFRA = "infra"  # Databases, caches, message brokers
    APP = "app"  # Spine API services
    WORKER = "worker"  # Background workers / Celery
    FRONTEND = "frontend"  # UI applications
    DOCS = "docs"  # Documentation sites
    TOOL = "tool"  # Utility / one-shot containers


class DeploymentConfig(BaseModel):
    """Configuration for a service deployment operation.

    Controls which services to deploy, how to deploy them, and where
    to collect output artifacts.

    Example::

        config = DeploymentConfig(
            targets=["spine-core-api", "postgresql"],
            mode=DeploymentMode.UP,
            profile="apps",
        )
    """

    # What to deploy
    targets: list[str] = Field(
        default_factory=list,
        description="Service names or target identifiers to deploy",
    )
    profile: str | None = Field(
        default=None,
        description="Docker Compose profile (infra, apps, full, minimal)",
    )
    mode: DeploymentMode = Field(
        default=DeploymentMode.UP,
        description="Deployment operation mode",
    )

    # Execution
    compose_files: list[str] = Field(
        default_factory=list,
        description="Additional compose files to merge (-f flags)",
    )
    env_file: str | None = Field(
        default=None,
        description="Path to .env file for container environment",
    )
    build: bool = Field(
        default=False,
        description="Build images before starting (--build)",
    )
    detach: bool = Field(
        default=True,
        description="Run containers in background (-d)",
    )
    remove_orphans: bool = Field(
        default=True,
        description="Remove containers for undefined services",
    )
    timeout_seconds: int = Field(
        default=300,
        description="Timeout for the entire deployment operation",
    )
    wait: bool = Field(
        default=True,
        description="Wait for services to be healthy before returning",
    )

    # Output
    output_dir: Path = Field(
        default=Path("deploy-results"),
        description="Directory for deployment logs and artifacts",
    )
    verbose: bool = Field(default=False, description="Enable verbose output")

    # Networking
    network: str | None = Field(
        default=None,
        description="Docker network name (auto-generated if not set)",
    )
    project_name: str | None = Field(
        default=None,
        description="Docker Compose project name (--project-name)",
    )

    # Internal
    run_id: str = Field(default="", description="Unique run identifier (auto-generated)")

    @model_validator(mode="after")
    def _set_defaults(self) -> DeploymentConfig:
        if not self.run_id:
            self.run_id = uuid.uuid4().hex[:12]
        return self

    @classmethod
    def from_env(cls, **overrides: Any) -> DeploymentConfig:
        """Create config from SPINE_DEPLOY_* environment variables."""
        env_map = {
            "targets": "SPINE_DEPLOY_TARGETS",
            "profile": "SPINE_DEPLOY_PROFILE",
            "mode": "SPINE_DEPLOY_MODE",
            "timeout_seconds": "SPINE_DEPLOY_TIMEOUT_SECONDS",
            "output_dir": "SPINE_DEPLOY_OUTPUT_DIR",
            "verbose": "SPINE_DEPLOY_VERBOSE",
            "network": "SPINE_DEPLOY_NETWORK",
            "project_name": "SPINE_DEPLOY_PROJECT_NAME",
        }
        values: dict[str, Any] = {}
        for field_name, env_var in env_map.items():
            env_val = os.environ.get(env_var)
            if env_val is not None:
                if field_name == "targets":
                    values[field_name] = [t.strip() for t in env_val.split(",") if t.strip()]
                elif field_name == "timeout_seconds":
                    values[field_name] = int(env_val)
                elif field_name == "verbose":
                    values[field_name] = env_val.lower() in ("true", "1", "yes")
                else:
                    values[field_name] = env_val
        values.update(overrides)
        return cls(**values)


class TestbedConfig(BaseModel):
    """Configuration for a multi-backend database testbed run.

    Controls which database backends to test against, what test phases
    to execute, and how to collect results.

    Example::

        config = TestbedConfig(
            backends=["postgresql", "mysql"],
            run_tests=True,
            run_examples=False,
            parallel=True,
        )
    """

    # What to test
    backends: list[str] = Field(
        default=["postgresql"],
        description="Database backends to test against",
    )
    run_schema: bool = Field(
        default=True,
        description="Verify schema creation against each backend",
    )
    run_tests: bool = Field(
        default=True,
        description="Run pytest suite against each backend",
    )
    run_examples: bool = Field(
        default=False,
        description="Run example scripts against each backend",
    )
    run_smoke: bool = Field(
        default=False,
        description="Run smoke tests against a live API",
    )
    test_filter: str | None = Field(
        default=None,
        description="pytest -k filter expression",
    )
    example_categories: list[str] | None = Field(
        default=None,
        description="Example categories to run (e.g., ['04_orchestration'])",
    )

    # Execution
    parallel: bool = Field(
        default=True,
        description="Run backends in parallel",
    )
    max_parallel: int = Field(
        default=4,
        description="Max concurrent backend containers",
    )
    timeout_seconds: int = Field(
        default=1800,
        description="Overall timeout (30 min default)",
    )
    backend_timeout_seconds: int = Field(
        default=300,
        description="Per-backend timeout (5 min default)",
    )
    startup_timeout_seconds: int = Field(
        default=120,
        description="Container startup timeout (2 min default)",
    )

    # Output
    output_dir: Path = Field(
        default=Path("testbed-results"),
        description="Directory for test results and logs",
    )
    output_format: Literal["json", "html", "junit", "all"] = Field(
        default="all",
        description="Output format(s) to generate",
    )
    keep_containers: bool = Field(
        default=False,
        description="Keep containers alive after run (for debugging)",
    )
    verbose: bool = Field(default=False, description="Enable verbose output")

    # Docker
    spine_image: str = Field(
        default="spine-core:latest",
        description="Docker image for the test runner",
    )
    network_prefix: str = Field(
        default="spine-testbed",
        description="Prefix for Docker networks",
    )

    # Internal
    run_id: str = Field(default="", description="Unique run identifier (auto-generated)")
    internal: bool = Field(
        default=False,
        description="True when running inside Docker (use container hostnames)",
    )

    @model_validator(mode="after")
    def _set_defaults(self) -> TestbedConfig:
        if not self.run_id:
            self.run_id = uuid.uuid4().hex[:12]
        return self

    @classmethod
    def from_env(cls, **overrides: Any) -> TestbedConfig:
        """Create config from SPINE_TESTBED_* environment variables."""
        env_map = {
            "backends": "SPINE_TESTBED_BACKENDS",
            "parallel": "SPINE_TESTBED_PARALLEL",
            "timeout_seconds": "SPINE_TESTBED_TIMEOUT_SECONDS",
            "output_dir": "SPINE_TESTBED_OUTPUT_DIR",
            "verbose": "SPINE_TESTBED_VERBOSE",
            "keep_containers": "SPINE_TESTBED_KEEP_CONTAINERS",
            "spine_image": "SPINE_TESTBED_IMAGE",
        }
        values: dict[str, Any] = {}
        for field_name, env_var in env_map.items():
            env_val = os.environ.get(env_var)
            if env_val is not None:
                if field_name == "backends":
                    values[field_name] = [b.strip() for b in env_val.split(",") if b.strip()]
                elif field_name in ("parallel", "verbose", "keep_containers"):
                    values[field_name] = env_val.lower() in ("true", "1", "yes")
                elif field_name == "timeout_seconds":
                    values[field_name] = int(env_val)
                else:
                    values[field_name] = env_val
        values.update(overrides)
        return cls(**values)


class TestbedSettings(BaseModel):
    """Feature flags for testbed functionality.

    Intended to be embedded in SpineCoreSettings or used standalone.
    """

    enable_testbed: bool = Field(
        default=True,
        description="Enable testbed commands in CLI and API",
    )
    enable_deploy: bool = Field(
        default=True,
        description="Enable deployment commands in CLI and API",
    )
    default_backends: list[str] = Field(
        default=["postgresql"],
        description="Default backends for testbed runs",
    )
    default_profile: str = Field(
        default="apps",
        description="Default Docker Compose profile for deployments",
    )
    results_retention_days: int = Field(
        default=30,
        description="How long to keep testbed results",
    )
