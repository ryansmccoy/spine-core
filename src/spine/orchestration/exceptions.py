"""Orchestration exceptions — structured error hierarchy.

All orchestration exceptions inherit from ``spine.core.errors.OrchestrationError``
so that callers can catch the entire family with a single ``except`` clause.

Hierarchy::

    OrchestrationError  (from spine.core.errors)
      └── GroupError                  ── base for all orchestration errors
            ├── GroupNotFoundError      ── pipeline group not registered
            ├── StepNotFoundError       ── step references unknown pipeline
            ├── CycleDetectedError      ── dependency graph has a cycle
            ├── PlanResolutionError     ── cannot resolve execution plan
            ├── InvalidGroupSpecError   ── YAML/dict spec is invalid
            └── DependencyError         ── step dependencies are invalid
"""

from spine.core.errors import OrchestrationError


class GroupError(OrchestrationError):
    """Base exception for all orchestration/group errors."""

    pass


class GroupNotFoundError(GroupError):
    """Raised when a requested pipeline group is not registered."""

    def __init__(self, group_name: str):
        self.group_name = group_name
        super().__init__(f"Pipeline group not found: {group_name}")


class StepNotFoundError(GroupError):
    """Raised when a step references a non-existent pipeline."""

    def __init__(self, step_name: str, pipeline_name: str):
        self.step_name = step_name
        self.pipeline_name = pipeline_name
        super().__init__(f"Step '{step_name}' references unknown pipeline: {pipeline_name}")


class CycleDetectedError(GroupError):
    """Raised when the dependency graph contains a cycle."""

    def __init__(self, cycle: list[str]):
        self.cycle = cycle
        cycle_str = " -> ".join(cycle)
        super().__init__(f"Cycle detected in dependency graph: {cycle_str}")


class PlanResolutionError(GroupError):
    """Raised when a group cannot be resolved into an execution plan."""

    def __init__(self, message: str, group_name: str | None = None):
        self.group_name = group_name
        super().__init__(message)


class InvalidGroupSpecError(GroupError):
    """Raised when a group specification is invalid."""

    def __init__(self, message: str, field: str | None = None):
        self.field = field
        super().__init__(message)


class DependencyError(GroupError):
    """Raised when step dependencies are invalid."""

    def __init__(self, step_name: str, missing_deps: list[str]):
        self.step_name = step_name
        self.missing_deps = missing_deps
        deps_str = ", ".join(missing_deps)
        super().__init__(f"Step '{step_name}' depends on unknown steps: {deps_str}")
