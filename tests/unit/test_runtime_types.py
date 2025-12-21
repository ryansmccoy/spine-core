"""Tests for Job Engine runtime types and protocols.

Tests:
    - ContainerJobSpec creation, serialization, hashing
    - Spec redaction (sensitive env vars, secrets)
    - JobError taxonomy
    - RuntimeCapabilities and RuntimeConstraints validation
    - StubRuntimeAdapter lifecycle
    - Deterministic naming
"""

import pytest

from spine.execution.runtimes._types import (
    ContainerJobSpec,
    ErrorCategory,
    JobArtifact,
    JobError,
    JobStatus,
    ResourceRequirements,
    RuntimeCapabilities,
    RuntimeConstraints,
    RuntimeHealth,
    VolumeMount,
    container_job_spec,
    job_external_name,
    quick_docker_spec,
    redact_spec,
)
from spine.execution.runtimes._base import StubRuntimeAdapter


# ---------------------------------------------------------------------------
# ContainerJobSpec
# ---------------------------------------------------------------------------

class TestContainerJobSpec:
    """Tests for ContainerJobSpec creation and serialization."""

    def test_minimal_spec(self):
        spec = ContainerJobSpec(name="test", image="alpine")
        assert spec.name == "test"
        assert spec.image == "alpine"
        assert spec.timeout_seconds == 3600
        assert spec.max_retries == 3

    def test_full_spec(self):
        spec = ContainerJobSpec(
            name="finra-otc-ingest",
            image="spine-worker:latest",
            command=["python", "-m", "spine.operations.finra_otc"],
            env={"LOG_LEVEL": "debug", "DB_HOST": "localhost"},
            resources=ResourceRequirements(cpu="2.0", memory="4Gi", gpu=1),
            volumes=[VolumeMount(name="data", mount_path="/data", host_path="/mnt/data")],
            timeout_seconds=1800,
            runtime="docker",
            namespace="production",
            labels={"team": "data-eng"},
        )
        assert spec.resources.cpu == "2.0"
        assert spec.resources.gpu == 1
        assert len(spec.volumes) == 1
        assert spec.labels["team"] == "data-eng"

    def test_to_dict_minimal(self):
        spec = ContainerJobSpec(name="test", image="alpine")
        d = spec.to_dict()
        assert d["name"] == "test"
        assert d["image"] == "alpine"
        assert d["trigger_source"] == "api"
        assert "env" not in d  # empty dict omitted

    def test_to_dict_full(self):
        spec = ContainerJobSpec(
            name="test",
            image="alpine",
            command=["echo", "hi"],
            env={"KEY": "val"},
            runtime="docker",
            timeout_seconds=300,
            priority="high",
            lane="gpu",
        )
        d = spec.to_dict()
        assert d["command"] == ["echo", "hi"]
        assert d["env"] == {"KEY": "val"}
        assert d["runtime"] == "docker"
        assert d["timeout_seconds"] == 300
        assert d["priority"] == "high"
        assert d["lane"] == "gpu"

    def test_spec_hash_deterministic(self):
        spec = ContainerJobSpec(name="test", image="alpine", env={"A": "1"})
        h1 = spec.spec_hash()
        h2 = spec.spec_hash()
        assert h1 == h2
        assert len(h1) == 64  # SHA-256

    def test_spec_hash_differs_for_different_specs(self):
        spec1 = ContainerJobSpec(name="test", image="alpine")
        spec2 = ContainerJobSpec(name="test", image="ubuntu")
        assert spec1.spec_hash() != spec2.spec_hash()

    def test_convenience_constructors(self):
        spec = container_job_spec("my-job", "python:3.12", ["python", "app.py"])
        assert spec.name == "my-job"
        assert spec.image == "python:3.12"
        assert spec.command == ["python", "app.py"]

    def test_quick_docker_spec(self):
        spec = quick_docker_spec("test", "alpine", ["echo", "hello"], timeout_seconds=60)
        assert spec.runtime == "docker"
        assert spec.timeout_seconds == 60


# ---------------------------------------------------------------------------
# Spec redaction
# ---------------------------------------------------------------------------

class TestSpecRedaction:
    """Tests for spec redaction of sensitive values."""

    def test_redacts_password_env(self):
        spec = ContainerJobSpec(
            name="test", image="alpine",
            env={"DB_PASSWORD": "hunter2", "LOG_LEVEL": "debug"},
        )
        redacted = redact_spec(spec)
        assert redacted["env"]["DB_PASSWORD"] == "***REDACTED***"
        assert redacted["env"]["LOG_LEVEL"] == "debug"

    def test_redacts_multiple_sensitive_patterns(self):
        spec = ContainerJobSpec(
            name="test", image="alpine",
            env={
                "API_KEY": "abc123",
                "SECRET_TOKEN": "xyz",
                "AUTH_HEADER": "Bearer ...",
                "NORMAL_VAR": "safe",
            },
        )
        redacted = redact_spec(spec)
        assert redacted["env"]["API_KEY"] == "***REDACTED***"
        assert redacted["env"]["SECRET_TOKEN"] == "***REDACTED***"
        assert redacted["env"]["AUTH_HEADER"] == "***REDACTED***"
        assert redacted["env"]["NORMAL_VAR"] == "safe"

    def test_redacts_image_pull_secret(self):
        spec = ContainerJobSpec(
            name="test", image="alpine",
            image_pull_secret="my-registry-creds",
        )
        redacted = redact_spec(spec)
        assert "image_pull_secret" not in redacted

    def test_redacts_secret_refs(self):
        spec = ContainerJobSpec(
            name="test", image="alpine",
            secret_refs=["vault:secret/db", "ssm:/prod/api-key"],
        )
        redacted = redact_spec(spec)
        assert redacted["secret_refs"] == ["***REDACTED***", "***REDACTED***"]

    def test_original_spec_unchanged(self):
        spec = ContainerJobSpec(
            name="test", image="alpine",
            env={"DB_PASSWORD": "hunter2"},
        )
        redact_spec(spec)
        assert spec.env["DB_PASSWORD"] == "hunter2"


# ---------------------------------------------------------------------------
# Deterministic naming
# ---------------------------------------------------------------------------

class TestDeterministicNaming:
    """Tests for job_external_name()."""

    def test_basic_naming(self):
        name = job_external_name("a1b2c3d4-5678-abcd-ef01", "finra-otc-ingest")
        assert name == "spine-a1b2c3d4-finra-otc-ingest"

    def test_slugifies_special_chars(self):
        name = job_external_name("abcd1234-xxxx", "My Operation!!!")
        assert "!" not in name
        assert name.startswith("spine-abcd1234-")

    def test_max_length_63(self):
        name = job_external_name("abcd1234", "a" * 100)
        assert len(name) <= 63

    def test_short_execution_id(self):
        name = job_external_name("abc", "test")
        assert name.startswith("spine-abc-")

    def test_empty_work_name_fallback(self):
        name = job_external_name("abcd1234", "!!!")
        assert "job" in name  # Falls back to "job" when slug is empty


# ---------------------------------------------------------------------------
# JobError
# ---------------------------------------------------------------------------

class TestJobError:
    """Tests for structured error taxonomy."""

    def test_creation(self):
        err = JobError(
            category=ErrorCategory.OOM,
            message="Container killed: OOM",
            retryable=False,
            exit_code=137,
            runtime="docker",
        )
        assert err.category == ErrorCategory.OOM
        assert not err.retryable
        assert err.exit_code == 137

    def test_serialization(self):
        err = JobError(
            category=ErrorCategory.AUTH,
            message="Token expired",
            retryable=True,
            provider_code="ExpiredTokenException",
        )
        d = err.to_dict()
        assert d["category"] == "auth"
        assert d["retryable"] is True

    def test_round_trip(self):
        err = JobError(
            category=ErrorCategory.IMAGE_PULL,
            message="Image not found",
            retryable=False,
            provider_code="ErrImagePull",
            exit_code=None,
            runtime="k8s",
        )
        d = err.to_dict()
        err2 = JobError.from_dict(d)
        assert err == err2

    def test_unknown_factory(self):
        err = JobError.unknown("Something went wrong", runtime="docker")
        assert err.category == ErrorCategory.UNKNOWN
        assert err.retryable is True

    def test_is_exception(self):
        err = JobError(category=ErrorCategory.TIMEOUT, message="timed out", retryable=True)
        assert isinstance(err, Exception)
        # Can be raised and caught
        with pytest.raises(JobError):
            raise err


# ---------------------------------------------------------------------------
# RuntimeConstraints
# ---------------------------------------------------------------------------

class TestRuntimeConstraints:
    """Tests for numeric constraint validation."""

    def test_timeout_violation(self):
        constraints = RuntimeConstraints(max_timeout_seconds=900)
        spec = ContainerJobSpec(name="test", image="x", timeout_seconds=3600)
        violations = constraints.validate_spec(spec)
        assert len(violations) == 1
        assert "3600s" in violations[0]
        assert "900s" in violations[0]

    def test_timeout_passes(self):
        constraints = RuntimeConstraints(max_timeout_seconds=3600)
        spec = ContainerJobSpec(name="test", image="x", timeout_seconds=300)
        violations = constraints.validate_spec(spec)
        assert len(violations) == 0

    def test_env_count_violation(self):
        constraints = RuntimeConstraints(max_env_count=2)
        spec = ContainerJobSpec(
            name="test", image="x",
            env={"A": "1", "B": "2", "C": "3"},
        )
        violations = constraints.validate_spec(spec)
        assert len(violations) == 1
        assert "3" in violations[0]

    def test_env_bytes_violation(self):
        constraints = RuntimeConstraints(max_env_bytes=10)
        spec = ContainerJobSpec(
            name="test", image="x",
            env={"LONG_KEY": "long_value_here"},
        )
        violations = constraints.validate_spec(spec)
        assert len(violations) == 1
        assert "bytes" in violations[0]

    def test_no_constraints_no_violations(self):
        constraints = RuntimeConstraints()  # All None
        spec = ContainerJobSpec(name="test", image="x", timeout_seconds=999999)
        violations = constraints.validate_spec(spec)
        assert len(violations) == 0

    def test_multiple_violations(self):
        constraints = RuntimeConstraints(max_timeout_seconds=60, max_env_count=1)
        spec = ContainerJobSpec(
            name="test", image="x",
            timeout_seconds=3600,
            env={"A": "1", "B": "2"},
        )
        violations = constraints.validate_spec(spec)
        assert len(violations) == 2


# ---------------------------------------------------------------------------
# RuntimeCapabilities
# ---------------------------------------------------------------------------

class TestRuntimeCapabilities:
    """Tests for boolean capability flags."""

    def test_defaults_all_false(self):
        caps = RuntimeCapabilities()
        assert not caps.supports_gpu
        assert not caps.supports_sidecars
        assert caps.supports_artifacts  # This one defaults True

    def test_to_dict(self):
        caps = RuntimeCapabilities(supports_gpu=True, supports_volumes=True)
        d = caps.to_dict()
        assert d["supports_gpu"] is True
        assert d["supports_sidecars"] is False


# ---------------------------------------------------------------------------
# JobStatus
# ---------------------------------------------------------------------------

class TestJobStatus:
    """Tests for runtime-observed job status."""

    def test_terminal_states(self):
        assert JobStatus(state="succeeded").is_terminal
        assert JobStatus(state="failed").is_terminal
        assert JobStatus(state="cancelled").is_terminal

    def test_non_terminal_states(self):
        assert not JobStatus(state="pending").is_terminal
        assert not JobStatus(state="running").is_terminal
        assert not JobStatus(state="pulling").is_terminal

    def test_to_dict(self):
        status = JobStatus(state="running", node="worker-1")
        d = status.to_dict()
        assert d["state"] == "running"
        assert d["node"] == "worker-1"


# ---------------------------------------------------------------------------
# StubRuntimeAdapter
# ---------------------------------------------------------------------------

class TestStubRuntimeAdapter:
    """Tests for the in-memory stub adapter."""

    @pytest.mark.asyncio
    async def test_submit_and_status(self):
        adapter = StubRuntimeAdapter()
        spec = ContainerJobSpec(name="test", image="alpine")
        ref = await adapter.submit(spec)
        assert ref.startswith("stub-")
        status = await adapter.status(ref)
        assert status.state == "succeeded"
        assert status.exit_code == 0

    @pytest.mark.asyncio
    async def test_submit_failure(self):
        adapter = StubRuntimeAdapter(auto_succeed=False, auto_exit_code=1)
        spec = ContainerJobSpec(name="test", image="alpine")
        ref = await adapter.submit(spec)
        status = await adapter.status(ref)
        assert status.state == "failed"
        assert status.exit_code == 1

    @pytest.mark.asyncio
    async def test_cancel(self):
        adapter = StubRuntimeAdapter()
        spec = ContainerJobSpec(name="test", image="alpine")
        ref = await adapter.submit(spec)
        result = await adapter.cancel(ref)
        assert result is True
        assert adapter.cancel_count == 1

    @pytest.mark.asyncio
    async def test_logs(self):
        adapter = StubRuntimeAdapter(auto_logs=["line1", "line2", "line3"])
        spec = ContainerJobSpec(name="test", image="alpine")
        ref = await adapter.submit(spec)
        lines = []
        async for line in adapter.logs(ref):
            lines.append(line)
        assert lines == ["line1", "line2", "line3"]

    @pytest.mark.asyncio
    async def test_logs_tail(self):
        adapter = StubRuntimeAdapter(auto_logs=["a", "b", "c", "d"])
        spec = ContainerJobSpec(name="test", image="alpine")
        ref = await adapter.submit(spec)
        lines = []
        async for line in adapter.logs(ref, tail=2):
            lines.append(line)
        assert lines == ["c", "d"]

    @pytest.mark.asyncio
    async def test_artifacts(self):
        artifact = JobArtifact(name="report.csv", path="/artifacts/report.csv", size_bytes=1024)
        adapter = StubRuntimeAdapter(auto_artifacts=[artifact])
        spec = ContainerJobSpec(name="test", image="alpine")
        ref = await adapter.submit(spec)
        arts = await adapter.artifacts(ref)
        assert len(arts) == 1
        assert arts[0].name == "report.csv"

    @pytest.mark.asyncio
    async def test_cleanup(self):
        adapter = StubRuntimeAdapter()
        spec = ContainerJobSpec(name="test", image="alpine")
        ref = await adapter.submit(spec)
        await adapter.cleanup(ref)
        assert adapter.cleanup_count == 1
        assert adapter.jobs[ref].cleaned_up is True

    @pytest.mark.asyncio
    async def test_health(self):
        adapter = StubRuntimeAdapter()
        health = await adapter.health()
        assert health.healthy is True
        assert health.runtime == "stub"
        assert health.latency_ms is not None

    @pytest.mark.asyncio
    async def test_health_failure(self):
        adapter = StubRuntimeAdapter()
        adapter.fail_health = True
        health = await adapter.health()
        assert health.healthy is False

    @pytest.mark.asyncio
    async def test_submit_fails_on_inject(self):
        adapter = StubRuntimeAdapter()
        adapter.fail_submit = True
        spec = ContainerJobSpec(name="test", image="alpine")
        with pytest.raises(JobError) as exc_info:
            await adapter.submit(spec)
        assert exc_info.value.category == ErrorCategory.RUNTIME_UNAVAILABLE

    @pytest.mark.asyncio
    async def test_runtime_name(self):
        adapter = StubRuntimeAdapter()
        assert adapter.runtime_name == "stub"

    @pytest.mark.asyncio
    async def test_capabilities(self):
        adapter = StubRuntimeAdapter()
        caps = adapter.capabilities
        assert caps.supports_gpu is True  # Stub supports everything

    @pytest.mark.asyncio
    async def test_status_unknown_ref(self):
        adapter = StubRuntimeAdapter()
        status = await adapter.status("nonexistent")
        assert status.state == "unknown"

    @pytest.mark.asyncio
    async def test_submit_count(self):
        adapter = StubRuntimeAdapter()
        spec = ContainerJobSpec(name="test", image="alpine")
        await adapter.submit(spec)
        await adapter.submit(spec)
        assert adapter.submit_count == 2


# ---------------------------------------------------------------------------
# EventType extensions
# ---------------------------------------------------------------------------

class TestJobEngineEventTypes:
    """Verify job engine event types were added to the enum."""

    def test_job_engine_events_exist(self):
        from spine.execution.models import EventType

        assert EventType.IMAGE_PULLING == "image_pulling"
        assert EventType.IMAGE_PULLED == "image_pulled"
        assert EventType.CONTAINER_CREATING == "container_creating"
        assert EventType.CONTAINER_CREATED == "container_created"
        assert EventType.ARTIFACT_READY == "artifact_ready"
        assert EventType.COST_RECORDED == "cost_recorded"
        assert EventType.CLEANUP_STARTED == "cleanup_started"
        assert EventType.CLEANUP_COMPLETED == "cleanup_completed"
        assert EventType.RECONCILED == "reconciled"
        assert EventType.ORPHAN_DETECTED == "orphan_detected"
