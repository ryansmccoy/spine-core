"""Tests for SpecValidator — pre-submit validation of container job specs."""

from __future__ import annotations

import pytest

from spine.execution.runtimes._types import (
    ContainerJobSpec,
    ErrorCategory,
    InitContainerSpec,
    JobError,
    ResourceRequirements,
    RuntimeCapabilities,
    RuntimeConstraints,
    SidecarSpec,
    VolumeMount,
)
from spine.execution.runtimes.validator import SpecValidator


# ── Helpers ──────────────────────────────────────────────────────────────


def _spec(**kwargs) -> ContainerJobSpec:
    defaults = {"name": "test-job", "image": "test:latest"}
    defaults.update(kwargs)
    return ContainerJobSpec(**defaults)


def _caps(**kwargs) -> RuntimeCapabilities:
    """All capabilities ON by default, override with kwargs."""
    defaults = {
        "supports_gpu": True,
        "supports_volumes": True,
        "supports_sidecars": True,
        "supports_init_containers": True,
    }
    defaults.update(kwargs)
    return RuntimeCapabilities(**defaults)


# ── Capability Checks ───────────────────────────────────────────────────


class TestCapabilityChecks:
    def test_no_violations_when_all_supported(self):
        validator = SpecValidator()
        spec = _spec(
            resources=ResourceRequirements(gpu=1),
            volumes=[VolumeMount(name="v1", mount_path="/data")],
            sidecars=[SidecarSpec(name="s1", image="sidecar:latest")],
            init_containers=[InitContainerSpec(name="i1", image="init:latest")],
        )
        errors = validator.validate(spec, _caps())
        assert errors == []

    def test_gpu_not_supported(self):
        validator = SpecValidator()
        spec = _spec(resources=ResourceRequirements(gpu=1))
        errors = validator.validate(spec, _caps(supports_gpu=False))
        assert any("GPU" in e for e in errors)

    def test_gpu_zero_is_ok(self):
        validator = SpecValidator()
        spec = _spec(resources=ResourceRequirements(gpu=0))
        errors = validator.validate(spec, _caps(supports_gpu=False))
        assert errors == []

    def test_volumes_not_supported(self):
        validator = SpecValidator()
        spec = _spec(volumes=[VolumeMount(name="v1", mount_path="/data")])
        errors = validator.validate(spec, _caps(supports_volumes=False))
        assert any("volume" in e.lower() for e in errors)

    def test_sidecars_not_supported(self):
        validator = SpecValidator()
        spec = _spec(sidecars=[SidecarSpec(name="s1", image="s:1")])
        errors = validator.validate(spec, _caps(supports_sidecars=False))
        assert any("sidecar" in e.lower() for e in errors)

    def test_init_containers_not_supported(self):
        validator = SpecValidator()
        spec = _spec(
            init_containers=[InitContainerSpec(name="i1", image="i:1")],
        )
        errors = validator.validate(
            spec, _caps(supports_init_containers=False),
        )
        assert any("init container" in e.lower() for e in errors)

    def test_no_resources_no_violations(self):
        validator = SpecValidator()
        spec = _spec()
        errors = validator.validate(spec, _caps(supports_gpu=False))
        assert errors == []


# ── Budget Gate ──────────────────────────────────────────────────────────


class TestBudgetGate:
    def test_negative_cost_rejected(self):
        validator = SpecValidator()
        spec = _spec(max_cost_usd=-1.0)
        errors = validator.validate(spec, _caps())
        assert any("max_cost_usd" in e for e in errors)

    def test_zero_cost_ok(self):
        validator = SpecValidator()
        spec = _spec(max_cost_usd=0.0)
        errors = validator.validate(spec, _caps())
        assert errors == []

    def test_positive_cost_ok(self):
        validator = SpecValidator()
        spec = _spec(max_cost_usd=100.0)
        errors = validator.validate(spec, _caps())
        assert errors == []

    def test_none_cost_ok(self):
        validator = SpecValidator()
        spec = _spec(max_cost_usd=None)
        errors = validator.validate(spec, _caps())
        assert errors == []


# ── Constraint Checks ───────────────────────────────────────────────────


class TestConstraintChecks:
    def test_constraint_validation_delegated(self):
        validator = SpecValidator()
        constraints = RuntimeConstraints(max_timeout_seconds=10)
        spec = _spec(timeout_seconds=20)
        errors = validator.validate(spec, _caps(), constraints)
        assert any("timeout" in e.lower() for e in errors)

    def test_no_constraints_ok(self):
        validator = SpecValidator()
        spec = _spec(timeout_seconds=99999)
        errors = validator.validate(spec, _caps(), constraints=None)
        assert errors == []


# ── Multiple Violations ─────────────────────────────────────────────────


class TestMultipleViolations:
    def test_collects_all_violations(self):
        """Validator should NOT fail-fast; all violations reported."""
        validator = SpecValidator()
        spec = _spec(
            resources=ResourceRequirements(gpu=1),
            volumes=[VolumeMount(name="v1", mount_path="/d")],
            max_cost_usd=-5.0,
        )
        caps = _caps(supports_gpu=False, supports_volumes=False)
        errors = validator.validate(spec, caps)
        assert len(errors) >= 3  # GPU + volumes + budget


# ── validate_or_raise ────────────────────────────────────────────────────


class TestValidateOrRaise:
    def test_valid_spec_no_error(self):
        from spine.execution.runtimes._base import StubRuntimeAdapter

        validator = SpecValidator()
        adapter = StubRuntimeAdapter()
        spec = _spec()
        validator.validate_or_raise(spec, adapter)  # should not raise

    def test_invalid_spec_raises_job_error(self):
        from spine.execution.runtimes._base import StubRuntimeAdapter

        validator = SpecValidator()
        adapter = StubRuntimeAdapter()
        spec = _spec(max_cost_usd=-1.0)
        # StubRuntimeAdapter has all capabilities, but budget is negative
        with pytest.raises(JobError) as exc_info:
            validator.validate_or_raise(spec, adapter)
        assert exc_info.value.category == ErrorCategory.VALIDATION
        assert exc_info.value.retryable is False
