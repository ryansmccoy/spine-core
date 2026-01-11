"""
Orchestration components.

This module provides:
1. Backend protocols for async execution (LocalBackend, future CeleryBackend)
2. Compatibility layer for spine-core orchestration

Spine-Core Re-exports:
- PipelineGroup, PipelineStep: Define groups of related pipelines
- PlanResolver: Resolve groups into executable plans
- GroupRunner: Execute resolved plans
- ExecutionPolicy: Configure execution behavior

Intermediate-specific:
- OrchestratorBackend: Protocol for async backends
- LocalBackend: Synchronous local execution
- adapt_pipeline: Adapt intermediate pipelines to spine-core interface
"""

# Intermediate-specific backends
from market_spine.orchestration.backends.protocol import OrchestratorBackend
from market_spine.orchestration.backends.local import LocalBackend

# Spine-core orchestration (re-export for convenience)
from spine.orchestration import (
    PipelineGroup,
    PipelineStep,
    ExecutionPolicy,
    ExecutionMode,
    FailurePolicy,
    PlanResolver,
    GroupRunner,
    GroupExecutionStatus,
    StepStatus,
    register_group,
    get_group,
    list_groups,
)

# Compatibility layer
from market_spine.orchestration.compat import (
    adapt_pipeline,
    register_adapted_pipelines,
)

__all__ = [
    # Backends
    "OrchestratorBackend",
    "LocalBackend",
    # Spine-core orchestration
    "PipelineGroup",
    "PipelineStep",
    "ExecutionPolicy",
    "ExecutionMode",
    "FailurePolicy",
    "PlanResolver",
    "GroupRunner",
    "GroupExecutionStatus",
    "StepStatus",
    "register_group",
    "get_group",
    "list_groups",
    # Compatibility
    "adapt_pipeline",
    "register_adapted_pipelines",
]
