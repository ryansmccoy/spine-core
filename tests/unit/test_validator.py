"""Tests for SpecValidator — pre-submit validation gate.

Tests:
    - Capability checks (GPU, volumes, sidecars, init containers)
    - Constraint delegation to RuntimeConstraints.validate_spec()
    - Budget gate (max_cost_usd)
    - validate_or_raise() raises JobError on violations
    - Clean pass when spec matches capabilities
"""

import pytest

from spine.execution.runtimes._types import (
    ContainerJobSpec,
    ErrorCategory,
    JobError,
    ResourceRequirements,
    RuntimeCapabilities,
    RuntimeConstraints,
    SidecarSpec,
    InitContainerSpec,
    VolumeMount,
)
from spine.execution.runtimes._base import StubRuntimeAdapter
from spine.execution.runtimes.validator import SpecValidator


@pytest.fixture
def validator():
    return SpecValidator()


@pytest.fixture
def minimal_spec():
    return ContainerJobSpec(name="test-job", image="alpine:latest")


class TestCapabilityChecks:
    """Test boolean capability validation."""

    def test_gpu_required_but_unsupported(self, validator, minimal_spec):
        minimal_spec.resources = ResourceRequirements(gpu=1)
        caps = RuntimeCapabilities(supports_gpu=False)
        errors = validator.validate(minimal_spec, caps)
        assert len(errors) == 1
        assert "GPU" in errors[0]

    def test_gpu_required_and_supported(self, validator, minimal_spec):
        minimal_spec.resources = ResourceRequirements(gpu=2)
        caps = RuntimeCapabilities(supports_gpu=True)
        errors = validator.validate(minimal_spec, caps)
        assert len(errors) == 0

    def test_gpu_zero_does_not_trigger(self, validator, minimal_spec):
        minimal_spec.resources = ResourceRequirements(gpu=0)
        caps = RuntimeCapabilities(supports_gpu=False)
        errors = validator.validate(minimal_spec, caps)
        assert len(errors) == 0

    def test_gpu_none_does_not_trigger(self, validator, minimal_spec):
        # Default ResourceRequirements has gpu=None
        caps = RuntimeCapabilities(supports_gpu=False)
        errors = validator.validate(minimal_spec, caps)
        assert len(errors) == 0

    def test_volumes_required_but_unsupported(self, validator, minimal_spec):
        minimal_spec.volumes = [VolumeMount(name="data", mount_path="/data")]
        caps = RuntimeCapabilities(supports_volumes=False)
        errors = validator.validate(minimal_spec, caps)
        assert len(errors) == 1
        assert "volume" in errors[0].lower()

    def test_volumes_supported(self, validator, minimal_spec):
        minimal_spec.volumes = [VolumeMount(name="data", mount_path="/data")]
        caps = RuntimeCapabilities(supports_volumes=True)
        errors = validator.validate(minimal_spec, caps)
        assert len(errors) == 0

    def test_sidecars_required_but_unsupported(self, validator, minimal_spec):
        minimal_spec.sidecars = [SidecarSpec(name="proxy", image="envoy:latest")]
        caps = RuntimeCapabilities(supports_sidecars=False)
        errors = validator.validate(minimal_spec, caps)
        assert len(errors) == 1
        assert "sidecar" in errors[0].lower()

    def test_init_containers_required_but_unsupported(self, validator, minimal_spec):
        minimal_spec.init_containers = [
            InitContainerSpec(name="init", image="busybox"),
        ]
        caps = RuntimeCapabilities(supports_init_containers=False)
        errors = validator.validate(minimal_spec, caps)
        assert len(errors) == 1
        assert "init container" in errors[0].lower()

    def test_multiple_violations(self, validator, minimal_spec):
        """All capabilities violated at once."""
        minimal_spec.resources = ResourceRequirements(gpu=1)
        minimal_spec.volumes = [VolumeMount(name="v", mount_path="/v")]
        minimal_spec.sidecars = [SidecarSpec(name="s", image="s:1")]
        minimal_spec.init_containers = [InitContainerSpec(name="i", image="i:1")]
        caps = RuntimeCapabilities()  # All False
        errors = validator.validate(minimal_spec, caps)
        assert len(errors) == 4


class TestConstraintDelegation:
    """Test that constraint checks delegate to RuntimeConstraints."""

    def test_timeout_exceeded(self, validator, minimal_spec):
        minimal_spec.timeout_seconds = 7200
        caps = RuntimeCapabilities()
        constraints = RuntimeConstraints(max_timeout_seconds=3600)
        errors = validator.validate(minimal_spec, caps, constraints)
        assert len(errors) == 1
        assert "Timeout" in errors[0]
        assert "7200" in errors[0]

    def test_timeout_within_limit(self, validator, minimal_spec):
        minimal_spec.timeout_seconds = 300
        caps = RuntimeCapabilities()
        constraints = RuntimeConstraints(max_timeout_seconds=3600)
        errors = validator.validate(minimal_spec, caps, constraints)
        assert len(errors) == 0

    def test_env_count_exceeded(self, validator, minimal_spec):
        minimal_spec.env = {f"VAR_{i}": f"val_{i}" for i in range(20)}
        caps = RuntimeCapabilities()
        constraints = RuntimeConstraints(max_env_count=10)
        errors = validator.validate(minimal_spec, caps, constraints)
        assert len(errors) == 1
        assert "Env var count" in errors[0]

    def test_no_constraints_skips_checks(self, validator, minimal_spec):
        minimal_spec.timeout_seconds = 99999
        caps = RuntimeCapabilities()
        errors = validator.validate(minimal_spec, caps, None)
        assert len(errors) == 0


class TestBudgetGate:
    """Test budget validation."""

    def test_negative_cost_rejected(self, validator, minimal_spec):
        minimal_spec.max_cost_usd = -1.0
        caps = RuntimeCapabilities()
        errors = validator.validate(minimal_spec, caps)
        assert len(errors) == 1
        assert "max_cost_usd" in errors[0]

    def test_zero_cost_allowed(self, validator, minimal_spec):
        minimal_spec.max_cost_usd = 0.0
        caps = RuntimeCapabilities()
        errors = validator.validate(minimal_spec, caps)
        assert len(errors) == 0

    def test_positive_cost_allowed(self, validator, minimal_spec):
        minimal_spec.max_cost_usd = 10.0
        caps = RuntimeCapabilities()
        errors = validator.validate(minimal_spec, caps)
        assert len(errors) == 0

    def test_none_cost_allowed(self, validator, minimal_spec):
        assert minimal_spec.max_cost_usd is None
        caps = RuntimeCapabilities()
        errors = validator.validate(minimal_spec, caps)
        assert len(errors) == 0


class TestValidateOrRaise:
    """Test validate_or_raise convenience method."""

    def test_raises_on_violation(self, validator, minimal_spec):
        minimal_spec.resources = ResourceRequirements(gpu=1)
        adapter = StubRuntimeAdapter()
        # Override stub capabilities to NOT support GPU
        adapter._no_gpu_caps = RuntimeCapabilities(supports_gpu=False)
        # We need to monkey-patch — use a custom adapter instead
        class NoGpuAdapter(StubRuntimeAdapter):
            @property
            def capabilities(self):
                return RuntimeCapabilities(supports_gpu=False)

        adapter = NoGpuAdapter()
        with pytest.raises(JobError) as exc_info:
            validator.validate_or_raise(minimal_spec, adapter)
        assert exc_info.value.category == ErrorCategory.VALIDATION
        assert not exc_info.value.retryable
        assert "GPU" in exc_info.value.message

    def test_passes_when_valid(self, validator, minimal_spec):
        adapter = StubRuntimeAdapter()
        # StubRuntimeAdapter supports everything — should pass
        validator.validate_or_raise(minimal_spec, adapter)

    def test_combined_capability_and_constraint_errors(self, validator, minimal_spec):
        """Both capability AND constraint violations in one raise."""
        minimal_spec.resources = ResourceRequirements(gpu=1)
        minimal_spec.timeout_seconds = 9999

        class LimitedAdapter(StubRuntimeAdapter):
            @property
            def capabilities(self):
                return RuntimeCapabilities(supports_gpu=False)
            @property
            def constraints(self):
                return RuntimeConstraints(max_timeout_seconds=900)

        adapter = LimitedAdapter()
        with pytest.raises(JobError) as exc_info:
            validator.validate_or_raise(minimal_spec, adapter)
        # Both violations should be in the message
        assert "GPU" in exc_info.value.message
        assert "Timeout" in exc_info.value.message


class TestCleanPass:
    """Test that a well-formed spec passes validation."""

    def test_minimal_spec_passes(self, validator, minimal_spec):
        caps = RuntimeCapabilities()
        errors = validator.validate(minimal_spec, caps)
        assert errors == []

    def test_full_spec_passes_with_full_caps(self, validator):
        spec = ContainerJobSpec(
            name="full-job",
            image="myapp:v2",
            command=["python", "run.py"],
            resources=ResourceRequirements(cpu="2.0", memory="4Gi", gpu=1),
            volumes=[VolumeMount(name="data", mount_path="/data")],
            sidecars=[SidecarSpec(name="proxy", image="envoy:latest")],
            init_containers=[InitContainerSpec(name="init", image="busybox")],
            timeout_seconds=1800,
            max_cost_usd=5.0,
        )
        caps = RuntimeCapabilities(
            supports_gpu=True,
            supports_volumes=True,
            supports_sidecars=True,
            supports_init_containers=True,
        )
        constraints = RuntimeConstraints(max_timeout_seconds=3600)
        errors = validator.validate(spec, caps, constraints)
        assert errors == []
