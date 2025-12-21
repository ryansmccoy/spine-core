"""Unit tests for spine.deploy package.

Tests configuration models, result models, backend specifications,
container management, compose generation, and workflow runners.
All container operations are mocked — no Docker required.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest


# ===========================================================================
# Config tests
# ===========================================================================


class TestDeploymentConfig:
    """Tests for DeploymentConfig model."""

    def test_defaults(self):
        from spine.deploy.config import DeploymentConfig

        config = DeploymentConfig()
        assert config.mode.value == "up"
        assert config.targets == []
        assert config.profile is None
        assert config.run_id  # auto-generated

    def test_custom_values(self):
        from spine.deploy.config import DeploymentConfig, DeploymentMode

        config = DeploymentConfig(
            mode=DeploymentMode.DOWN,
            targets=["postgres", "redis"],
            profile="infra",
        )
        assert config.mode == DeploymentMode.DOWN
        assert config.targets == ["postgres", "redis"]
        assert config.profile == "infra"

    def test_deployment_modes(self):
        from spine.deploy.config import DeploymentMode

        assert DeploymentMode.UP.value == "up"
        assert DeploymentMode.DOWN.value == "down"
        assert DeploymentMode.RESTART.value == "restart"
        assert DeploymentMode.STATUS.value == "status"
        assert DeploymentMode.LOGS.value == "logs"


class TestTestbedConfig:
    """Tests for TestbedConfig model."""

    def test_defaults(self):
        from spine.deploy.config import TestbedConfig

        config = TestbedConfig()
        assert config.backends == ["postgresql"]
        assert config.parallel is True
        assert config.keep_containers is False
        assert config.run_schema is True
        assert config.run_tests is True

    def test_run_id_auto_generated(self):
        from spine.deploy.config import TestbedConfig

        c1 = TestbedConfig()
        c2 = TestbedConfig()
        assert c1.run_id != c2.run_id
        assert len(c1.run_id) == 12  # hex[:12]

    def test_custom_backends(self):
        from spine.deploy.config import TestbedConfig

        config = TestbedConfig(backends=["postgresql", "mysql"])
        assert config.backends == ["postgresql", "mysql"]

    def test_all_backends(self):
        from spine.deploy.config import TestbedConfig

        config = TestbedConfig(backends=["all"])
        assert config.backends == ["all"]


class TestTestbedSettings:
    """Tests for TestbedSettings (env-based configuration)."""

    def test_from_env_defaults(self):
        from spine.deploy.config import TestbedSettings

        settings = TestbedSettings()
        assert settings.default_backends is not None

    @patch.dict(os.environ, {"SPINE_TESTBED_BACKENDS": "postgresql,mysql"})
    def test_from_env_custom(self):
        from spine.deploy.config import TestbedSettings

        settings = TestbedSettings()
        # Verify env var is available
        assert os.environ["SPINE_TESTBED_BACKENDS"] == "postgresql,mysql"


# ===========================================================================
# Results tests
# ===========================================================================


class TestOverallStatus:
    """Tests for OverallStatus enum."""

    def test_all_values(self):
        from spine.deploy.results import OverallStatus

        assert OverallStatus.PASSED.value == "PASSED"
        assert OverallStatus.FAILED.value == "FAILED"
        assert OverallStatus.PARTIAL.value == "PARTIAL"
        assert OverallStatus.ERROR.value == "ERROR"
        assert OverallStatus.SKIPPED.value == "SKIPPED"
        assert OverallStatus.RUNNING.value == "RUNNING"
        assert OverallStatus.PENDING.value == "PENDING"
        assert OverallStatus.CANCELLED.value == "CANCELLED"


class TestSchemaResult:
    """Tests for SchemaResult model."""

    def test_defaults(self):
        from spine.deploy.results import SchemaResult

        result = SchemaResult(backend="sqlite")
        assert result.backend == "sqlite"
        assert result.tables_created == 0
        assert result.tables_expected == 0
        assert result.tables_missing == []
        assert result.error is None

    def test_with_data(self):
        from spine.deploy.results import SchemaResult

        result = SchemaResult(
            backend="postgresql",
            tables_created=20,
            tables_expected=22,
            tables_missing=["tab_a", "tab_b"],
        )
        assert result.tables_created == 20
        assert len(result.tables_missing) == 2


class TestTestResult:
    """Tests for TestResult model."""

    def test_defaults(self):
        from spine.deploy.results import TestResult

        result = TestResult(backend="sqlite")
        assert result.total == 0
        assert result.passed == 0
        assert result.failed == 0
        assert result.errors == 0

    def test_with_data(self):
        from spine.deploy.results import TestResult

        result = TestResult(backend="pg", passed=95, failed=3, errors=2)
        assert result.total == 100
        assert result.passed == 95


class TestBackendResult:
    """Tests for BackendResult model."""

    def test_defaults(self):
        from spine.deploy.results import BackendResult, OverallStatus

        result = BackendResult(backend="sqlite")
        assert result.backend == "sqlite"
        assert result.overall_status == OverallStatus.PENDING

    def test_compute_status_all_pass(self):
        from spine.deploy.results import BackendResult, SchemaResult, TestResult

        result = BackendResult(
            backend="postgresql",
            image="postgres:16",
            schema_result=SchemaResult(backend="postgresql", tables_created=22, tables_expected=22, success=True),
            tests=TestResult(backend="postgresql", passed=100),
        )
        status = result.compute_status()
        assert status.value == "PASSED"

    def test_compute_status_with_failures(self):
        from spine.deploy.results import BackendResult, SchemaResult, TestResult

        result = BackendResult(
            backend="postgresql",
            image="postgres:16",
            schema_result=SchemaResult(backend="postgresql", tables_created=22, tables_expected=22, success=True),
            tests=TestResult(backend="postgresql", passed=90, failed=10),
        )
        status = result.compute_status()
        assert status.value in ("FAILED", "PARTIAL")

    def test_compute_status_with_error(self):
        from spine.deploy.results import BackendResult, OverallStatus

        result = BackendResult(backend="mysql", image="mysql:8", error="connection failed")
        status = result.compute_status()
        assert status == OverallStatus.ERROR


class TestTestbedRunResult:
    """Tests for TestbedRunResult model."""

    def test_defaults(self):
        from spine.deploy.results import TestbedRunResult, OverallStatus

        result = TestbedRunResult(run_id="test-default")
        assert result.backends == []
        assert result.overall_status == OverallStatus.PENDING

    def test_mark_complete(self):
        from spine.deploy.results import TestbedRunResult

        result = TestbedRunResult(run_id="test-complete")
        result.mark_complete()
        assert result.completed_at is not None
        assert result.summary != ""

    def test_serialization(self):
        from spine.deploy.results import TestbedRunResult

        result = TestbedRunResult(run_id="test-123")
        data = result.model_dump()
        assert data["run_id"] == "test-123"
        assert "backends" in data


class TestJobResult:
    """Tests for JobResult model."""

    def test_defaults(self):
        from spine.deploy.results import JobResult, OverallStatus

        result = JobResult(job_id="test-job", job_type="testbed")
        assert result.job_id == "test-job"
        assert result.overall_status == OverallStatus.PENDING


class TestServiceStatus:
    """Tests for ServiceStatus model."""

    def test_create(self):
        from spine.deploy.results import ServiceStatus

        svc = ServiceStatus(name="postgres", status="running")
        assert svc.name == "postgres"
        assert svc.status == "running"


class TestDeploymentResult:
    """Tests for DeploymentResult model."""

    def test_defaults(self):
        from spine.deploy.results import DeploymentResult

        result = DeploymentResult(run_id="test-deploy", mode="up")
        assert result.services == []
        assert result.error is None


# ===========================================================================
# Backends tests
# ===========================================================================


class TestBackendSpec:
    """Tests for BackendSpec and built-in backends."""

    def test_sqlite_backend(self):
        from spine.deploy.backends import get_backend

        backend = get_backend("sqlite")
        assert backend.name == "sqlite"
        assert backend.dialect == "sqlite"
        assert backend.image == ""
        assert backend.port == 0

    def test_postgresql_backend(self):
        from spine.deploy.backends import get_backend

        backend = get_backend("postgresql")
        assert backend.name == "postgresql"
        assert backend.dialect == "postgresql"
        assert "postgres" in backend.image
        assert backend.port == 5432

    def test_mysql_backend(self):
        from spine.deploy.backends import get_backend

        backend = get_backend("mysql")
        assert backend.dialect == "mysql"
        assert backend.port == 3306

    def test_all_backends_registered(self):
        from spine.deploy.backends import BACKENDS

        assert "sqlite" in BACKENDS
        assert "postgresql" in BACKENDS
        assert "mysql" in BACKENDS
        assert "db2" in BACKENDS
        assert "oracle" in BACKENDS
        assert "timescaledb" in BACKENDS

    def test_get_backend_unknown(self):
        from spine.deploy.backends import get_backend

        with pytest.raises(ValueError):
            get_backend("nonexistent")

    def test_connection_url_template(self):
        from spine.deploy.backends import get_backend

        pg = get_backend("postgresql")
        assert pg.connection_url_template is not None
        url = pg.connection_url()
        assert "postgresql" in url

    def test_container_backends_filter(self):
        from spine.deploy.backends import CONTAINER_BACKENDS

        for name, spec in CONTAINER_BACKENDS.items():
            assert spec.image  # non-empty image string
            assert name != "sqlite"

    def test_free_backends_filter(self):
        from spine.deploy.backends import FREE_BACKENDS

        for name, spec in FREE_BACKENDS.items():
            assert not spec.requires_license


class TestServiceSpec:
    """Tests for ServiceSpec and built-in services."""

    def test_all_services_registered(self):
        from spine.deploy.backends import SERVICES

        assert len(SERVICES) >= 5  # At least the core services

    def test_service_has_required_fields(self):
        from spine.deploy.backends import SERVICES

        for name, spec in SERVICES.items():
            assert spec.name
            assert spec.image
            assert spec.port > 0

    def test_get_services_by_profile(self):
        from spine.deploy.backends import get_services_by_profile

        app_services = get_services_by_profile("apps")
        assert isinstance(app_services, list)

    def test_app_and_infra_registries(self):
        from spine.deploy.backends import APP_SERVICES, INFRA_SERVICES

        assert isinstance(APP_SERVICES, dict)
        assert isinstance(INFRA_SERVICES, dict)


class TestGetBackends:
    """Tests for get_backends helper."""

    def test_get_specific_backends(self):
        from spine.deploy.backends import get_backends

        specs = get_backends(["sqlite", "postgresql"])
        assert len(specs) == 2
        names = [s.name for s in specs]
        assert "sqlite" in names
        assert "postgresql" in names

    def test_get_all_backends(self):
        from spine.deploy.backends import get_backends, BACKENDS

        specs = get_backends(["all"])
        assert len(specs) == len(BACKENDS)


# ===========================================================================
# Container tests (mocked)
# ===========================================================================


class TestContainerManager:
    """Tests for ContainerManager (all Docker calls mocked)."""

    def test_init(self):
        from spine.deploy.container import ContainerManager

        mgr = ContainerManager()
        assert mgr is not None

    @patch("subprocess.run")
    def test_is_docker_available_true(self, mock_run):
        from spine.deploy.container import ContainerManager

        mock_run.return_value = MagicMock(returncode=0, stdout="Docker version 24.0.0")
        assert ContainerManager.is_docker_available() is True

    @patch("subprocess.run")
    def test_is_docker_available_false(self, mock_run):
        from spine.deploy.container import ContainerManager

        mock_run.side_effect = FileNotFoundError()
        assert ContainerManager.is_docker_available() is False

    def test_container_info_dataclass(self):
        from spine.deploy.container import ContainerInfo

        info = ContainerInfo(
            container_id="abc123",
            container_name="test-pg",
            host="localhost",
            port=5432,
            internal_port=5432,
            network="test-net",
            image="postgres:16",
        )
        assert info.container_id == "abc123"
        assert info.port == 5432


# ===========================================================================
# Compose tests
# ===========================================================================


class TestComposeGeneration:
    """Tests for compose file generation."""

    def test_generate_testbed_compose(self):
        from spine.deploy.compose import generate_testbed_compose
        from spine.deploy.backends import get_backend

        specs = [get_backend("postgresql")]
        result = generate_testbed_compose(specs, run_id="test-run")
        assert isinstance(result, str)
        assert "services" in result
        assert "networks" in result

    def test_generate_deployment_compose(self):
        from spine.deploy.compose import generate_deployment_compose
        from spine.deploy.backends import get_service, SERVICES

        # Get first available service
        svc_name = next(iter(SERVICES))
        svc = get_service(svc_name)
        result = generate_deployment_compose([svc], run_id="test-deploy")
        assert isinstance(result, str)
        assert "services" in result

    def test_write_compose_file(self):
        from spine.deploy.compose import generate_testbed_compose, write_compose_file
        from spine.deploy.backends import get_backend

        specs = [get_backend("sqlite")]
        compose_yaml = generate_testbed_compose(specs, run_id="test-write")

        with tempfile.TemporaryDirectory() as tmpdir:
            path = str(Path(tmpdir) / "docker-compose.yml")
            written = write_compose_file(compose_yaml, output_path=path)
            assert Path(written).exists()
            content = Path(written).read_text()
            assert "services" in content


# ===========================================================================
# Results serialization tests
# ===========================================================================


class TestResultSerialization:
    """Ensure all result models serialize and deserialize cleanly."""

    def test_backend_result_roundtrip(self):
        from spine.deploy.results import BackendResult, SchemaResult, TestResult

        original = BackendResult(
            backend="postgresql",
            image="postgres:16",
            schema_result=SchemaResult(backend="postgresql", tables_created=20, tables_expected=22),
            tests=TestResult(backend="postgresql", passed=48, failed=2),
        )
        data = original.model_dump()
        restored = BackendResult.model_validate(data)
        assert restored.backend == "postgresql"
        assert restored.schema_result.tables_created == 20
        assert restored.tests.passed == 48

    def test_testbed_run_result_json(self):
        from spine.deploy.results import TestbedRunResult, BackendResult

        result = TestbedRunResult(
            run_id="test-123",
            backends=[
                BackendResult(backend="sqlite"),
            ],
        )
        json_str = result.model_dump_json()
        data = json.loads(json_str)
        assert data["run_id"] == "test-123"
        assert len(data["backends"]) == 1


# ===========================================================================
# Workflow tests
# ===========================================================================


class TestWorkflowFactory:
    """Tests for workflow creation factories."""

    def test_create_testbed_workflow(self):
        from spine.deploy.workflow import create_testbed_workflow

        wf = create_testbed_workflow(["sqlite"])
        assert wf.name == "deploy.testbed"
        assert wf.domain == "spine.deploy"
        assert len(wf.steps) == 2
        assert "deploy" in wf.tags

    def test_create_deployment_workflow(self):
        from spine.deploy.workflow import create_deployment_workflow

        wf = create_deployment_workflow(["postgres"], profile="infra")
        assert wf.name == "deploy.services"
        assert wf.domain == "spine.deploy"
        assert len(wf.steps) == 2
        assert "infra" in wf.tags

    def test_testbed_workflow_default_backends(self):
        from spine.deploy.workflow import create_testbed_workflow

        wf = create_testbed_workflow()
        assert wf.description
        assert "postgresql" in wf.description


# ===========================================================================
# Runner tests (mocked)
# ===========================================================================


class TestTestbedRunner:
    """Tests for TestbedRunner (Docker mocked)."""

    def test_init(self):
        from spine.deploy.config import TestbedConfig
        from spine.deploy.workflow import TestbedRunner

        config = TestbedConfig(backends=["sqlite"])
        runner = TestbedRunner(config)
        assert runner.config == config

    @patch("spine.deploy.container.ContainerManager.is_docker_available", return_value=False)
    def test_sqlite_only_no_docker(self, mock_docker):
        """SQLite backend should work without Docker."""
        from spine.deploy.config import TestbedConfig
        from spine.deploy.workflow import TestbedRunner

        config = TestbedConfig(
            backends=["sqlite"],
            run_schema=False,
            run_tests=False,
            run_examples=False,
        )
        runner = TestbedRunner(config)
        result = runner.run()
        assert result.run_id == config.run_id
        assert result.completed_at is not None

    @patch("spine.deploy.container.ContainerManager.is_docker_available", return_value=False)
    def test_docker_required_but_missing(self, mock_docker):
        """Should fail gracefully when Docker is needed but not available."""
        from spine.deploy.config import TestbedConfig
        from spine.deploy.workflow import TestbedRunner

        config = TestbedConfig(
            backends=["postgresql"],
            run_schema=False,
            run_tests=False,
        )
        runner = TestbedRunner(config)
        result = runner.run()
        assert result.error is not None
        assert "Docker" in result.error


class TestDeploymentRunner:
    """Tests for DeploymentRunner (Docker mocked)."""

    def test_init(self):
        from spine.deploy.config import DeploymentConfig
        from spine.deploy.workflow import DeploymentRunner

        config = DeploymentConfig()
        runner = DeploymentRunner(config)
        assert runner.config == config


# ===========================================================================
# __init__ exports tests
# ===========================================================================


class TestPackageExports:
    """Ensure the public API is accessible."""

    def test_core_config_exports(self):
        from spine.deploy import DeploymentConfig, TestbedConfig, TestbedSettings

        assert DeploymentConfig is not None
        assert TestbedConfig is not None
        assert TestbedSettings is not None

    def test_result_exports(self):
        from spine.deploy import (
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
        assert OverallStatus.PASSED.value == "PASSED"

    def test_runner_exports(self):
        from spine.deploy import (
            DeploymentRunner,
            TestbedRunner,
            create_deployment_workflow,
            create_testbed_workflow,
        )
        assert callable(create_testbed_workflow)
        assert callable(create_deployment_workflow)

    def test_backends_submodule(self):
        from spine.deploy.backends import (
            BACKENDS,
            SERVICES,
            get_backend,
            get_service,
            get_backends,
            get_services_by_profile,
        )
        assert len(BACKENDS) >= 6
        assert callable(get_backend)
