"""Result models for deploy-spine.

Pydantic v2 models that capture structured outcomes from deployments,
testbed runs, job executions, and service health checks. The models
form a composition hierarchy: individual results (schema, test, example)
roll up into per-backend results, which roll up into overall run results.

Why This Matters — Financial Data Operations:
    After a nightly testbed run against PostgreSQL, MySQL, and TimescaleDB,
    every stakeholder needs a different view: CI wants exit code 0/1,
    the team wants an HTML dashboard, ops wants a JSON artifact for
    Elasticsearch ingestion. These models support all three via
    ``mark_complete()`` + ``model_dump_json()`` + ``LogCollector.write_html_report()``.

Why This Matters — General Operations:
    Structured results enable programmatic decision-making. A CI operation
    can check ``result.overall_status == OverallStatus.PASSED`` rather
    than parsing log output. The ``compute_status()`` method on
    ``BackendResult`` derives PASSED/FAILED/PARTIAL from sub-results
    automatically.

Key Concepts:
    OverallStatus: Enum with 8 states — PASSED, FAILED, PARTIAL, ERROR,
        SKIPPED, RUNNING, PENDING, CANCELLED.
    BackendResult: Aggregates SchemaResult + TestResult + ExampleResult +
        SmokeResult for a single database backend.
    TestbedRunResult: Aggregates BackendResults across all backends.
        ``mark_complete()`` finalises timestamps, duration, and summary.
    DeploymentResult: Tracks service health after a deploy operation.
    JobResult: Generic container job (migration, script, testbed).

Architecture Decisions:
    - Pydantic v2 BaseModel: Enables ``model_dump_json(indent=2)`` for
      persistence and ``model_validate()`` for restoration.
    - ``mark_complete()`` pattern: Caller invokes when done — computes
      duration from ISO timestamps and derives overall status.
    - ``compute_status()`` on BackendResult: Pure function that reads
      sub-results to determine PASSED/FAILED/PARTIAL/ERROR/SKIPPED.
    - ``schema_result`` field name (not ``schema``): Avoids shadowing
      Pydantic's ``BaseModel.model_json_schema()``.

Related Modules:
    - :mod:`spine.deploy.workflow` — Produces these results
    - :mod:`spine.deploy.log_collector` — Serialises and renders them
    - :mod:`spine.deploy.executor` — Produces SchemaResult, TestResult, etc.

Tags:
    results, models, pydantic, testbed, deployment, status, reporting
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any, Literal

try:
    from pydantic import BaseModel, Field
except ImportError as _exc:
    raise ImportError(
        "spine.deploy.results requires pydantic. "
        "Install it with: pip install spine-core[models]"
    ) from _exc

# ---------------------------------------------------------------------------
# Shared enums
# ---------------------------------------------------------------------------


class OverallStatus(str, Enum):
    """Overall status of a run or deployment."""

    PASSED = "PASSED"
    FAILED = "FAILED"
    PARTIAL = "PARTIAL"
    ERROR = "ERROR"
    SKIPPED = "SKIPPED"
    RUNNING = "RUNNING"
    PENDING = "PENDING"
    CANCELLED = "CANCELLED"


# ---------------------------------------------------------------------------
# Service / Deployment results
# ---------------------------------------------------------------------------


class ServiceStatus(BaseModel):
    """Health/status of a single deployed service."""

    name: str
    container_id: str | None = None
    container_name: str | None = None
    image: str | None = None
    status: Literal["running", "healthy", "unhealthy", "exited", "starting", "not_found"] = "not_found"
    ports: dict[str, int] = Field(default_factory=dict)
    health_url: str | None = None
    health_response: dict[str, Any] | None = None
    started_at: str | None = None
    uptime_seconds: float | None = None
    error: str | None = None


class DeploymentResult(BaseModel):
    """Result of a deployment operation (up/down/restart/status)."""

    run_id: str
    mode: str  # up, down, restart, status
    started_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    completed_at: str | None = None
    duration_seconds: float = 0.0
    services: list[ServiceStatus] = Field(default_factory=list)
    overall_status: OverallStatus = OverallStatus.PENDING
    compose_files: list[str] = Field(default_factory=list)
    profile: str | None = None
    network: str | None = None
    error: str | None = None
    summary: str = ""

    def mark_complete(self, status: OverallStatus | None = None) -> None:
        """Mark deployment as complete, compute duration and status."""
        self.completed_at = datetime.now(UTC).isoformat()
        if self.started_at and self.completed_at:
            start = datetime.fromisoformat(self.started_at)
            end = datetime.fromisoformat(self.completed_at)
            self.duration_seconds = (end - start).total_seconds()
        if status:
            self.overall_status = status
        elif not self.services:
            self.overall_status = OverallStatus.PASSED
        elif all(s.status in ("running", "healthy") for s in self.services):
            self.overall_status = OverallStatus.PASSED
        elif any(s.status in ("running", "healthy") for s in self.services):
            self.overall_status = OverallStatus.PARTIAL
        else:
            self.overall_status = OverallStatus.FAILED
        healthy = sum(1 for s in self.services if s.status in ("running", "healthy"))
        total = len(self.services)
        self.summary = f"{healthy}/{total} services healthy"


# ---------------------------------------------------------------------------
# Testbed-specific results
# ---------------------------------------------------------------------------


class TestFailure(BaseModel):
    """A single test failure."""

    name: str
    message: str = ""
    traceback: str = ""


class SchemaResult(BaseModel):
    """Result of schema verification against a single backend."""

    backend: str
    tables_expected: int = 0
    tables_created: int = 0
    tables_missing: list[str] = Field(default_factory=list)
    tables_extra: list[str] = Field(default_factory=list)
    duration_ms: float = 0.0
    success: bool = False
    error: str | None = None


class TestResult(BaseModel):
    """Result of running pytest against a single backend."""

    backend: str
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    errors: int = 0
    duration_seconds: float = 0.0
    failures: list[TestFailure] = Field(default_factory=list)
    junit_xml_path: str | None = None
    error: str | None = None

    @property
    def success(self) -> bool:
        return self.failed == 0 and self.errors == 0 and self.error is None

    @property
    def total(self) -> int:
        return self.passed + self.failed + self.skipped + self.errors


class ExampleRun(BaseModel):
    """Result of running a single example script."""

    name: str
    status: Literal["passed", "failed", "error", "skipped"] = "skipped"
    output: str = ""
    duration_ms: float = 0.0
    error: str | None = None


class ExampleResult(BaseModel):
    """Result of running example scripts against a single backend."""

    backend: str
    total: int = 0
    passed: int = 0
    failed: int = 0
    results: list[ExampleRun] = Field(default_factory=list)
    error: str | None = None


class SmokeResult(BaseModel):
    """Result of running smoke tests against a live API."""

    backend: str
    api_url: str = ""
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    duration_seconds: float = 0.0
    error: str | None = None

    @property
    def success(self) -> bool:
        return self.failed == 0 and self.error is None


class BackendResult(BaseModel):
    """Aggregated result for a single database backend."""

    backend: str
    image: str = ""
    image_digest: str | None = None
    container_id: str | None = None
    container_name: str | None = None
    startup_ms: float = 0.0
    connection_url: str | None = None
    schema_result: SchemaResult | None = None
    tests: TestResult | None = None
    examples: ExampleResult | None = None
    smoke: SmokeResult | None = None
    overall_status: OverallStatus = OverallStatus.PENDING
    error: str | None = None

    def compute_status(self) -> OverallStatus:
        """Compute overall status from sub-results."""
        if self.error:
            return OverallStatus.ERROR
        results_present = []
        if self.schema_result:
            results_present.append(self.schema_result.success)
        if self.tests:
            results_present.append(self.tests.success)
        if self.smoke:
            results_present.append(self.smoke.success)
        if self.examples:
            results_present.append(self.examples.failed == 0)
        if not results_present:
            return OverallStatus.SKIPPED
        if all(results_present):
            return OverallStatus.PASSED
        if any(results_present):
            return OverallStatus.PARTIAL
        return OverallStatus.FAILED


class TestbedRunResult(BaseModel):
    """Result of a full testbed run across multiple backends."""

    run_id: str
    started_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    completed_at: str | None = None
    duration_seconds: float = 0.0
    backends: list[BackendResult] = Field(default_factory=list)
    overall_status: OverallStatus = OverallStatus.PENDING
    summary: str = ""
    error: str | None = None

    def mark_complete(self) -> None:
        """Finalize run: compute durations, statuses, summary."""
        self.completed_at = datetime.now(UTC).isoformat()
        if self.started_at and self.completed_at:
            start = datetime.fromisoformat(self.started_at)
            end = datetime.fromisoformat(self.completed_at)
            self.duration_seconds = (end - start).total_seconds()

        # Compute per-backend statuses
        for br in self.backends:
            br.overall_status = br.compute_status()

        # Compute overall
        if self.error:
            self.overall_status = OverallStatus.ERROR
        elif not self.backends:
            self.overall_status = OverallStatus.SKIPPED
        elif all(b.overall_status == OverallStatus.PASSED for b in self.backends):
            self.overall_status = OverallStatus.PASSED
        elif all(b.overall_status in (OverallStatus.FAILED, OverallStatus.ERROR) for b in self.backends):
            self.overall_status = OverallStatus.FAILED
        else:
            self.overall_status = OverallStatus.PARTIAL

        # Build summary
        passed_count = sum(1 for b in self.backends if b.overall_status == OverallStatus.PASSED)
        total_count = len(self.backends)
        backend_details = []
        for b in self.backends:
            detail = b.backend
            if b.tests:
                detail += f": {b.tests.passed} passed"
            backend_details.append(detail)
        details_str = ", ".join(backend_details)
        self.summary = (
            f"{passed_count}/{total_count} backends {self.overall_status.value} "
            f"({details_str}) in {self.duration_seconds:.1f}s"
        )


# ---------------------------------------------------------------------------
# Job / Task results (general-purpose)
# ---------------------------------------------------------------------------


class JobResult(BaseModel):
    """Result of a containerized job execution."""

    job_id: str
    job_type: str  # "testbed", "workflow", "migration", "script", "service"
    started_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    completed_at: str | None = None
    duration_seconds: float = 0.0
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    artifacts: list[str] = Field(default_factory=list)
    overall_status: OverallStatus = OverallStatus.PENDING
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    def mark_complete(self, exit_code: int = 0) -> None:
        """Mark job as complete."""
        self.completed_at = datetime.now(UTC).isoformat()
        self.exit_code = exit_code
        if self.started_at and self.completed_at:
            start = datetime.fromisoformat(self.started_at)
            end = datetime.fromisoformat(self.completed_at)
            self.duration_seconds = (end - start).total_seconds()
        if exit_code == 0 and not self.error:
            self.overall_status = OverallStatus.PASSED
        else:
            self.overall_status = OverallStatus.FAILED
