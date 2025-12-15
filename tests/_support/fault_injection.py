"""
Fault injection system for deterministic test failures.

When ``SPINE_FAULT_INJECTION=1`` is set, specific pipeline steps can be
made to fail with controlled error types.  This is activated from
scenario fixtures — never in production.

Usage in test code::

    from tests._support.fault_injection import install_fault, clear_faults

    install_fault("transform", error_type="TIMEOUT", message="Step timed out")
    # ... run the workflow ...
    clear_faults()

The orchestration layer checks ``should_fault(step_name)`` before executing
each step.  If a fault is installed, it raises the appropriate error instead
of running the real step.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass

_FAULTS: dict[str, "FaultSpec"] = {}


@dataclass
class FaultSpec:
    """A fault to inject into a specific step."""

    step: str
    error_type: str = "INTERNAL"
    message: str = "Injected test fault"
    delay_ms: int = 0


def is_fault_injection_enabled() -> bool:
    """Check if fault injection is enabled via environment variable."""
    return os.environ.get("SPINE_FAULT_INJECTION", "0") == "1"


def install_fault(
    step: str,
    *,
    error_type: str = "INTERNAL",
    message: str = "Injected test fault",
    delay_ms: int = 0,
) -> None:
    """Install a fault for a specific step name."""
    _FAULTS[step] = FaultSpec(
        step=step,
        error_type=error_type,
        message=message,
        delay_ms=delay_ms,
    )


def clear_faults() -> None:
    """Remove all installed faults."""
    _FAULTS.clear()


def should_fault(step_name: str) -> FaultSpec | None:
    """Check if a fault is installed for this step.

    Returns the FaultSpec if a fault should fire, None otherwise.
    Called by the orchestration runner before executing each step.
    """
    if not is_fault_injection_enabled():
        return None
    return _FAULTS.get(step_name)


def apply_fault(step_name: str) -> None:
    """Apply the fault — raise or delay as configured.

    Call this from the step executor when ``should_fault()`` returns a spec.
    """
    spec = should_fault(step_name)
    if spec is None:
        return

    if spec.delay_ms > 0:
        time.sleep(spec.delay_ms / 1000.0)

    raise FaultInjectedError(
        step=spec.step,
        error_type=spec.error_type,
        message=spec.message,
    )


class FaultInjectedError(Exception):
    """Raised when a fault is injected into a step."""

    def __init__(self, step: str, error_type: str, message: str):
        self.step = step
        self.error_type = error_type
        super().__init__(f"[FAULT:{error_type}] Step '{step}': {message}")
