"""Tests for spine.deploy data models and container utilities.

Tests ContainerInfo, result models, DeploymentResult, JobResult,
and BackendResult.compute_status / mark_complete without Docker.
"""

from __future__ import annotations

import time

import pytest

from spine.deploy.container import ContainerInfo, ContainerStartError, DockerNotFoundError
from spine.deploy.results import (
    BackendResult,
    DeploymentResult,
    ExampleResult,
    ExampleRun,
    JobResult,
    OverallStatus,
    SchemaResult,
    ServiceStatus,
    SmokeResult,
)

# Alias classes that start with "Test" to prevent pytest collection conflicts
from spine.deploy.results import TestbedRunResult as _TestbedRunResult
from spine.deploy.results import TestFailure as _TestFailure
from spine.deploy.results import TestResult as _TestResult


# ------------------------------------------------------------------ #
# Container dataclass
# ------------------------------------------------------------------ #


class TestContainerInfo:
    def test_basic(self):
        info = ContainerInfo(
            container_id="abc123",
            container_name="test-pg",
            host="localhost",
            port=5432,
            internal_port=5432,
            network="testbed-net",
            image="postgres:16",
        )
        assert info.container_id == "abc123"
        assert info.host == "localhost"
        assert info.uptime_seconds == 0.0

    def test_uptime(self):
        info = ContainerInfo(
            container_id="abc",
            container_name="test",
            host="localhost",
            port=5432,
            internal_port=5432,
            network="net",
            image="postgres:16",
            started_at=time.time() - 60,
        )
        assert info.uptime_seconds >= 59.0

    def test_optional_fields(self):
        info = ContainerInfo(
            container_id="abc",
            container_name="test",
            host="localhost",
            port=5432,
            internal_port=5432,
            network="net",
            image="postgres:16",
            connection_url="postgresql://localhost:5432/test",
            image_digest="sha256:abc",
            labels={"spine.deploy.run": "test-run"},
        )
        assert info.connection_url is not None
        assert info.image_digest is not None
        assert info.labels["spine.deploy.run"] == "test-run"


class TestDockerExceptions:
    def test_docker_not_found(self):
        with pytest.raises(DockerNotFoundError):
            raise DockerNotFoundError("Docker CLI not found")

    def test_container_start_error(self):
        with pytest.raises(ContainerStartError):
            raise ContainerStartError("Container failed to start")


# ------------------------------------------------------------------ #
# OverallStatus enum
# ------------------------------------------------------------------ #


class TestOverallStatus:
    def test_enum_values(self):
        assert OverallStatus.PASSED.value == "PASSED"
        assert OverallStatus.FAILED.value == "FAILED"
        assert OverallStatus.ERROR.value == "ERROR"
        assert OverallStatus.SKIPPED.value == "SKIPPED"
        assert OverallStatus.RUNNING.value == "RUNNING"
        assert OverallStatus.PENDING.value == "PENDING"
        assert OverallStatus.CANCELLED.value == "CANCELLED"
        assert OverallStatus.PARTIAL.value == "PARTIAL"


# ------------------------------------------------------------------ #
# SchemaResult
# ------------------------------------------------------------------ #


class TestSchemaResult:
    def test_success(self):
        r = SchemaResult(backend="postgresql", success=True, tables_expected=27, tables_created=27)
        assert r.success is True
        assert r.tables_created == 27
        assert r.tables_missing == []

    def test_failure(self):
        r = SchemaResult(
            backend="mysql",
            success=False,
            tables_expected=27,
            tables_created=25,
            tables_missing=["core_workflow_runs", "core_rejects"],
            error="2 tables missing",
        )
        assert r.success is False
        assert len(r.tables_missing) == 2


# ------------------------------------------------------------------ #
# TestResult + TestFailure
# ------------------------------------------------------------------ #


class TestTestResultModel:
    def test_success(self):
        r = _TestResult(backend="postgresql", passed=98, failed=0, errors=0, skipped=2)
        assert r.total == 100
        assert r.success is True

    def test_failure(self):
        f = _TestFailure(name="test_connection", message="Connection refused")
        r = _TestResult(backend="postgresql", passed=9, failed=1, failures=[f])
        assert r.success is False
        assert r.total == 10
        assert r.failures[0].name == "test_connection"

    def test_error_flag(self):
        r = _TestResult(backend="pg", passed=10, failed=0, errors=0, error="timeout")
        assert r.success is False


# ------------------------------------------------------------------ #
# ExampleResult / ExampleRun
# ------------------------------------------------------------------ #


class TestExampleResult:
    def test_basic(self):
        run = ExampleRun(name="basic_query", status="passed", duration_ms=500.0)
        r = ExampleResult(backend="pg", total=1, passed=1, failed=0, results=[run])
        assert r.total == 1
        assert r.results[0].status == "passed"


# ------------------------------------------------------------------ #
# SmokeResult
# ------------------------------------------------------------------ #


class TestSmokeResult:
    def test_success(self):
        r = SmokeResult(backend="pg", api_url="http://localhost:12000", passed=5, failed=0)
        assert r.success is True

    def test_failure(self):
        r = SmokeResult(backend="pg", passed=3, failed=2)
        assert r.success is False


# ------------------------------------------------------------------ #
# BackendResult + compute_status
# ------------------------------------------------------------------ #


class TestBackendResult:
    def test_all_pass(self):
        r = BackendResult(
            backend="postgresql",
            schema_result=SchemaResult(backend="pg", success=True),
            tests=_TestResult(backend="pg", passed=100, failed=0),
        )
        assert r.compute_status() == OverallStatus.PASSED

    def test_partial(self):
        r = BackendResult(
            backend="postgresql",
            schema_result=SchemaResult(backend="pg", success=True),
            tests=_TestResult(backend="pg", passed=90, failed=10),
        )
        assert r.compute_status() == OverallStatus.PARTIAL

    def test_all_fail(self):
        r = BackendResult(
            backend="postgresql",
            schema_result=SchemaResult(backend="pg", success=False),
            tests=_TestResult(backend="pg", passed=0, failed=100),
        )
        assert r.compute_status() == OverallStatus.FAILED

    def test_error(self):
        r = BackendResult(backend="pg", error="connection refused")
        assert r.compute_status() == OverallStatus.ERROR

    def test_skipped(self):
        r = BackendResult(backend="pg")
        assert r.compute_status() == OverallStatus.SKIPPED


# ------------------------------------------------------------------ #
# TestbedRunResult + mark_complete
# ------------------------------------------------------------------ #


class TestTestbedRunResultModel:
    def test_empty(self):
        r = _TestbedRunResult(run_id="run-1")
        assert r.overall_status == OverallStatus.PENDING

    def test_mark_complete_passed(self):
        r = _TestbedRunResult(
            run_id="run-1",
            backends=[
                BackendResult(
                    backend="pg",
                    schema_result=SchemaResult(backend="pg", success=True),
                    tests=_TestResult(backend="pg", passed=50, failed=0),
                ),
            ],
        )
        r.mark_complete()
        assert r.overall_status == OverallStatus.PASSED
        assert r.completed_at is not None
        assert "1/1" in r.summary

    def test_mark_complete_no_backends(self):
        r = _TestbedRunResult(run_id="run-2")
        r.mark_complete()
        assert r.overall_status == OverallStatus.SKIPPED

    def test_mark_complete_with_error(self):
        r = _TestbedRunResult(run_id="run-3", error="network failure")
        r.mark_complete()
        assert r.overall_status == OverallStatus.ERROR


# ------------------------------------------------------------------ #
# DeploymentResult + mark_complete
# ------------------------------------------------------------------ #


class TestDeploymentResult:
    def test_mark_complete_no_services(self):
        r = DeploymentResult(run_id="deploy-1", mode="up")
        r.mark_complete()
        assert r.overall_status == OverallStatus.PASSED
        assert r.completed_at is not None

    def test_mark_complete_all_healthy(self):
        r = DeploymentResult(
            run_id="deploy-2",
            mode="up",
            services=[
                ServiceStatus(name="api", status="healthy"),
                ServiceStatus(name="db", status="running"),
            ],
        )
        r.mark_complete()
        assert r.overall_status == OverallStatus.PASSED
        assert "2/2" in r.summary

    def test_mark_complete_partial(self):
        r = DeploymentResult(
            run_id="deploy-3",
            mode="up",
            services=[
                ServiceStatus(name="api", status="healthy"),
                ServiceStatus(name="db", status="exited"),
            ],
        )
        r.mark_complete()
        assert r.overall_status == OverallStatus.PARTIAL

    def test_mark_complete_explicit_status(self):
        r = DeploymentResult(run_id="deploy-4", mode="down")
        r.mark_complete(status=OverallStatus.CANCELLED)
        assert r.overall_status == OverallStatus.CANCELLED


# ------------------------------------------------------------------ #
# JobResult + mark_complete
# ------------------------------------------------------------------ #


class TestJobResult:
    def test_mark_complete_success(self):
        j = JobResult(job_id="job-1", job_type="testbed")
        j.mark_complete(exit_code=0)
        assert j.overall_status == OverallStatus.PASSED
        assert j.exit_code == 0

    def test_mark_complete_failure(self):
        j = JobResult(job_id="job-2", job_type="migration")
        j.mark_complete(exit_code=1)
        assert j.overall_status == OverallStatus.FAILED

    def test_mark_complete_with_error(self):
        j = JobResult(job_id="job-3", job_type="script", error="OOM")
        j.mark_complete(exit_code=0)
        assert j.overall_status == OverallStatus.FAILED
