#!/usr/bin/env python3
"""SpecValidator — pre-flight validation for ContainerJobSpec submissions.

================================================================================
WHY SpecValidator?
================================================================================

Submitting a GPU-heavy spec to a runtime that only supports CPU wastes time
and money.  ``SpecValidator`` catches mismatches **before** the job reaches
the adapter, returning all violations at once (not fail-fast).

Three layers of checks:

::

    ┌─────────────────────────────────────────────────────────┐
    │                   SpecValidator                          │
    ├─────────────────────────────────────────────────────────┤
    │  1. Capability checks (boolean flags)                   │
    │     ├── GPU required but not supported?                 │
    │     ├── Volumes required but not supported?             │
    │     ├── Sidecars required but not supported?            │
    │     └── Init containers required but not supported?     │
    │                                                         │
    │  2. Constraint checks (delegated to RuntimeConstraints) │
    │     └── timeout, resource limits, env count             │
    │                                                         │
    │  3. Budget gate                                         │
    │     └── max_cost_usd validation                         │
    └─────────────────────────────────────────────────────────┘


================================================================================
WHAT THIS EXAMPLE DEMONSTRATES
================================================================================

::

    1  Valid spec — passes all checks
    2  GPU capability mismatch
    3  Volume capability mismatch
    4  Multiple violations at once
    5  Budget gate — negative max_cost_usd
    6  validate_or_raise() — exception-based API
    7  Real adapter validation — check against LocalProcessAdapter


================================================================================
RUN IT
================================================================================

::

    python examples/02_execution/22_spec_validator.py

See Also:
    - ``19_local_process_adapter.py`` — Adapter capabilities
    - ``20_job_engine_lifecycle.py`` — Engine calls validator internally
    - ``src/spine/execution/runtimes/validator.py`` — Implementation
"""

from spine.execution.runtimes import (
    ContainerJobSpec,
    ErrorCategory,
    JobError,
    LocalProcessAdapter,
    RuntimeCapabilities,
    SpecValidator,
    StubRuntimeAdapter,
)
from spine.execution.runtimes._types import ResourceRequirements, VolumeMount


# ── Section 1: Valid spec passes validation ───────────────────────────────

def demo_valid_spec():
    """A simple spec passes validation against default capabilities."""
    print("=" * 70)
    print("SECTION 1 — Valid Spec (All Checks Pass)")
    print("=" * 70)

    validator = SpecValidator()

    spec = ContainerJobSpec(
        name="simple-job",
        image="python:3.12-slim",
        command=["python", "-c", "print('hello')"],
        timeout_seconds=60,
    )

    # Validate against capabilities that support everything
    caps = RuntimeCapabilities(
        supports_gpu=False,
        supports_volumes=False,
        supports_sidecars=False,
        supports_init_containers=False,
    )

    errors = validator.validate(spec, caps)
    print(f"  Violations: {errors}")
    assert len(errors) == 0
    print("  ✓ Spec is valid\n")


# ── Section 2: GPU mismatch ──────────────────────────────────────────────

def demo_gpu_mismatch():
    """Spec requires GPU but runtime doesn't support it."""
    print("=" * 70)
    print("SECTION 2 — GPU Capability Mismatch")
    print("=" * 70)

    validator = SpecValidator()

    spec = ContainerJobSpec(
        name="ml-training",
        image="nvidia/cuda:12.0",
        command=["python", "train.py"],
        resources=ResourceRequirements(gpu=1),
    )

    # Runtime without GPU support
    caps = RuntimeCapabilities(supports_gpu=False)

    errors = validator.validate(spec, caps)
    for e in errors:
        print(f"  VIOLATION: {e}")
    assert len(errors) == 1
    assert "GPU" in errors[0]
    print("  ✓ GPU mismatch detected\n")


# ── Section 3: Volume mismatch ────────────────────────────────────────────

def demo_volume_mismatch():
    """Spec requires volumes but runtime doesn't support them."""
    print("=" * 70)
    print("SECTION 3 — Volume Capability Mismatch")
    print("=" * 70)

    validator = SpecValidator()

    spec = ContainerJobSpec(
        name="data-loader",
        image="python:3.12",
        command=["python", "load.py"],
        volumes=[VolumeMount(name="data", mount_path="/data", host_path="/mnt/data")],
    )

    caps = RuntimeCapabilities(supports_volumes=False)

    errors = validator.validate(spec, caps)
    for e in errors:
        print(f"  VIOLATION: {e}")
    assert any("volume" in e.lower() for e in errors)
    print("  ✓ Volume mismatch detected\n")


# ── Section 4: Multiple violations ────────────────────────────────────────

def demo_multiple_violations():
    """Spec has multiple capability mismatches — all reported at once."""
    print("=" * 70)
    print("SECTION 4 — Multiple Violations (Non-Fail-Fast)")
    print("=" * 70)

    validator = SpecValidator()

    spec = ContainerJobSpec(
        name="complex-job",
        image="nvidia/cuda:12.0",
        command=["python", "run.py"],
        resources=ResourceRequirements(gpu=2),
        volumes=[VolumeMount(name="data", mount_path="/data", host_path="/mnt/data")],
        max_cost_usd=-5.0,  # Invalid!
    )

    # Runtime that supports nothing
    caps = RuntimeCapabilities(
        supports_gpu=False,
        supports_volumes=False,
        supports_sidecars=False,
        supports_init_containers=False,
    )

    errors = validator.validate(spec, caps)
    print(f"  Total violations: {len(errors)}")
    for i, e in enumerate(errors, 1):
        print(f"  {i}. {e}")
    assert len(errors) >= 3  # GPU + volumes + budget
    print("  ✓ All violations reported at once\n")


# ── Section 5: Budget gate ────────────────────────────────────────────────

def demo_budget_gate():
    """Negative max_cost_usd is rejected."""
    print("=" * 70)
    print("SECTION 5 — Budget Gate")
    print("=" * 70)

    validator = SpecValidator()

    spec = ContainerJobSpec(
        name="budget-test",
        image="python:3.12",
        command=["echo", "test"],
        max_cost_usd=-1.0,
    )

    caps = RuntimeCapabilities()  # Default = supports nothing exotic

    errors = validator.validate(spec, caps)
    for e in errors:
        print(f"  VIOLATION: {e}")
    assert any("max_cost_usd" in e for e in errors)
    print("  ✓ Negative budget correctly rejected\n")


# ── Section 6: validate_or_raise ──────────────────────────────────────────

def demo_validate_or_raise():
    """Exception-based API for pipeline integration."""
    print("=" * 70)
    print("SECTION 6 — validate_or_raise() Exception API")
    print("=" * 70)

    validator = SpecValidator()

    spec = ContainerJobSpec(
        name="gpu-job",
        image="nvidia/cuda:12.0",
        command=["python", "train.py"],
        resources=ResourceRequirements(gpu=1),
    )

    # StubRuntimeAdapter has no GPU support
    adapter = StubRuntimeAdapter(auto_succeed=True)

    try:
        validator.validate_or_raise(spec, adapter)
        print("  ERROR: Should have raised!")
    except JobError as err:
        print(f"  Category:  {err.category}")
        print(f"  Message:   {err.message}")
        print(f"  Retryable: {err.retryable}")
        print(f"  Runtime:   {err.runtime}")
        assert err.category == ErrorCategory.VALIDATION
        assert err.retryable is False
        print("  ✓ JobError(VALIDATION) raised correctly\n")


# ── Section 7: Real adapter validation ────────────────────────────────────

def demo_real_adapter_validation():
    """Validate against the LocalProcessAdapter's actual capabilities."""
    print("=" * 70)
    print("SECTION 7 — Real Adapter Validation (LocalProcessAdapter)")
    print("=" * 70)

    validator = SpecValidator()
    adapter = LocalProcessAdapter()

    # Simple spec — should pass
    simple_spec = ContainerJobSpec(
        name="simple",
        image="python:3.12",
        command=["echo", "ok"],
    )
    errors = validator.validate(simple_spec, adapter.capabilities, adapter.constraints)
    print(f"  Simple spec violations: {errors}")
    assert len(errors) == 0

    # GPU spec — should fail (local has no GPU support)
    gpu_spec = ContainerJobSpec(
        name="gpu-job",
        image="nvidia/cuda:12.0",
        command=["python", "train.py"],
        resources=ResourceRequirements(gpu=1),
    )
    errors = validator.validate(gpu_spec, adapter.capabilities, adapter.constraints)
    print(f"  GPU spec violations:    {errors}")
    assert len(errors) >= 1

    print("  ✓ Real adapter validation works correctly\n")


# ── Main ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    demo_valid_spec()
    demo_gpu_mismatch()
    demo_volume_mismatch()
    demo_multiple_violations()
    demo_budget_gate()
    demo_validate_or_raise()
    demo_real_adapter_validation()
    print("=" * 70)
    print("ALL SECTIONS PASSED ✓")
    print("=" * 70)
