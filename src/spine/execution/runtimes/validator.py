"""Spec validation for container job submissions.

Validates a ``ContainerJobSpec`` against a runtime adapter's capabilities
and constraints before submission. Catches mismatches early with clear,
actionable error messages.

Architecture:

    .. code-block:: text

        SpecValidator — Pre-Submit Gate
        ┌───────────────────────────────────────────────────────┐
        │                                                       │
        │  validate(spec, capabilities, constraints)            │
        │    ├── capability checks (boolean flags)              │
        │    │   ├── GPU required but not supported?            │
        │    │   ├── Volumes required but not supported?        │
        │    │   ├── Sidecars required but not supported?       │
        │    │   └── Init containers required but unsupported?  │
        │    ├── constraint checks (numeric limits)             │
        │    │   ├── delegates to constraints.validate_spec()   │
        │    │   └── timeout, env count, env bytes              │
        │    └── budget gate                                    │
        │        └── max_cost_usd checked against estimate      │
        │                                                       │
        │  validate_or_raise(spec, adapter)                     │
        │    ├── calls validate(spec, caps, constraints)        │
        │    └── raises JobError(VALIDATION) on any violation   │
        │                                                       │
        └───────────────────────────────────────────────────────┘

    .. mermaid::

        flowchart TD
            SPEC[ContainerJobSpec] --> V{SpecValidator}
            V -->|capability checks| CAP[RuntimeCapabilities]
            V -->|numeric checks| CON[RuntimeConstraints]
            V -->|budget gate| BG[max_cost_usd]
            CAP --> R[violations list]
            CON --> R
            BG --> R
            R -->|empty| OK[✓ Submit allowed]
            R -->|non-empty| ERR[✗ JobError VALIDATION]

Example:
    >>> from spine.execution.runtimes.validator import SpecValidator
    >>> from spine.execution.runtimes import ContainerJobSpec, RuntimeCapabilities
    >>>
    >>> validator = SpecValidator()
    >>> spec = ContainerJobSpec(
    ...     name="gpu-job", image="nvidia/cuda:12",
    ...     resources=ResourceRequirements(gpu=1),
    ... )
    >>> caps = RuntimeCapabilities(supports_gpu=False)
    >>> errors = validator.validate(spec, caps)
    >>> errors
    ['Spec requires GPU but runtime does not support it']
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from spine.execution.runtimes._types import (
    ErrorCategory,
    JobError,
    RuntimeCapabilities,
    RuntimeConstraints,
)

if TYPE_CHECKING:
    from spine.execution.runtimes._types import ContainerJobSpec, RuntimeAdapter

logger = logging.getLogger(__name__)


class SpecValidator:
    """Validates a ContainerJobSpec against runtime capabilities and constraints.

    The validator performs three layers of checks:

    1. **Capability checks** — boolean feature flags (GPU, volumes, etc.)
    2. **Constraint checks** — numeric limits (timeout, env count, etc.)
       Delegates to ``RuntimeConstraints.validate_spec()`` for reuse.
    3. **Budget gate** — estimated cost vs ``max_cost_usd``

    All violations are collected (not fail-fast) so users see every problem
    at once.

    Thread-safe and stateless — can be shared across the application.
    """

    def validate(
        self,
        spec: ContainerJobSpec,
        capabilities: RuntimeCapabilities,
        constraints: RuntimeConstraints | None = None,
    ) -> list[str]:
        """Validate spec against capabilities and constraints.

        Args:
            spec: The container job specification to validate.
            capabilities: Boolean feature flags from the adapter.
            constraints: Numeric limits from the adapter (optional).

        Returns:
            List of violation messages. Empty list = spec is valid.

        Example:
            >>> validator = SpecValidator()
            >>> errors = validator.validate(spec, adapter.capabilities, adapter.constraints)
            >>> if errors:
            ...     print("Validation failed:", errors)
        """
        violations: list[str] = []

        # --- Capability checks ---
        violations.extend(self._check_capabilities(spec, capabilities))

        # --- Constraint checks (delegate to RuntimeConstraints) ---
        if constraints is not None:
            violations.extend(constraints.validate_spec(spec))

        # --- Budget gate ---
        violations.extend(self._check_budget(spec))

        return violations

    def validate_or_raise(
        self,
        spec: ContainerJobSpec,
        adapter: RuntimeAdapter,
    ) -> None:
        """Validate spec against an adapter, raising on failure.

        Convenience method that extracts capabilities/constraints from
        the adapter and validates in one call. Raises ``JobError`` with
        category ``VALIDATION`` if any violations are found.

        Args:
            spec: The container job specification.
            adapter: The runtime adapter to validate against.

        Raises:
            JobError: With ``category=VALIDATION`` if validation fails.
                The ``message`` contains all violations joined by ``'; '``.
        """
        violations = self.validate(
            spec,
            adapter.capabilities,
            adapter.constraints,
        )
        if violations:
            msg = "; ".join(violations)
            logger.warning(
                "Spec validation failed for '%s' on %s: %s",
                spec.name,
                adapter.runtime_name,
                msg,
            )
            raise JobError(
                category=ErrorCategory.VALIDATION,
                message=msg,
                retryable=False,
                runtime=adapter.runtime_name,
            )

    # ------------------------------------------------------------------
    # Internal checks
    # ------------------------------------------------------------------

    def _check_capabilities(
        self,
        spec: ContainerJobSpec,
        caps: RuntimeCapabilities,
    ) -> list[str]:
        """Check boolean capability requirements."""
        violations: list[str] = []

        # GPU
        if spec.resources.gpu and spec.resources.gpu > 0 and not caps.supports_gpu:
            violations.append(
                "Spec requires GPU but runtime does not support it"
            )

        # Volumes
        if spec.volumes and not caps.supports_volumes:
            violations.append(
                f"Spec requires {len(spec.volumes)} volume(s) but runtime "
                "does not support volumes"
            )

        # Sidecars
        if spec.sidecars and not caps.supports_sidecars:
            violations.append(
                f"Spec requires {len(spec.sidecars)} sidecar(s) but runtime "
                "does not support sidecars"
            )

        # Init containers
        if spec.init_containers and not caps.supports_init_containers:
            violations.append(
                f"Spec requires {len(spec.init_containers)} init container(s) "
                "but runtime does not support init containers"
            )

        return violations

    def _check_budget(self, spec: ContainerJobSpec) -> list[str]:
        """Check budget constraints.

        For MVP-1, this only validates that max_cost_usd is non-negative
        when set. Real cost estimation will be added in MVP-3 when cloud
        adapters and pricing APIs exist.
        """
        violations: list[str] = []

        if spec.max_cost_usd is not None and spec.max_cost_usd < 0:
            violations.append(
                f"max_cost_usd must be non-negative, got {spec.max_cost_usd}"
            )

        return violations
