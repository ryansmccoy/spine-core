"""
Orchestration models - Core dataclasses for pipeline groups.

These are pure data structures with no dependencies on database or execution.
They can be serialized to/from YAML or JSON.

Design Principles:
- Immutable where possible (frozen dataclasses)
- No business logic (that lives in planner/executor)
- Compatible with both YAML and Python DSL definitions
- Aligned with RFC-001 specification
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class FailurePolicy(str, Enum):
    """What to do when a step fails."""

    STOP = "stop"        # Stop execution immediately (default)
    CONTINUE = "continue"  # Continue with remaining steps that don't depend on failed step


class ExecutionMode(str, Enum):
    """How to execute steps."""

    SEQUENTIAL = "sequential"  # One at a time in topological order (default)
    PARALLEL = "parallel"      # Concurrent execution respecting dependencies


class GroupRunStatus(str, Enum):
    """Status of a group run (aggregated from child executions)."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class ExecutionPolicy:
    """
    Execution policy for a pipeline group.

    Attributes:
        mode: Sequential or parallel execution
        max_concurrency: Max concurrent steps (only for parallel mode)
        on_failure: Stop or continue on step failure
        timeout_minutes: Optional timeout for entire group run
    """

    mode: ExecutionMode = ExecutionMode.SEQUENTIAL
    max_concurrency: int = 4
    on_failure: FailurePolicy = FailurePolicy.STOP
    timeout_minutes: int | None = None

    def __post_init__(self):
        if self.max_concurrency < 1:
            raise ValueError("max_concurrency must be at least 1")

    @classmethod
    def sequential(cls, on_failure: FailurePolicy = FailurePolicy.STOP) -> "ExecutionPolicy":
        """Factory for sequential execution policy."""
        return cls(mode=ExecutionMode.SEQUENTIAL, on_failure=on_failure)

    @classmethod
    def parallel(
        cls,
        max_concurrency: int = 4,
        on_failure: FailurePolicy = FailurePolicy.STOP,
    ) -> "ExecutionPolicy":
        """Factory for parallel execution policy."""
        return cls(
            mode=ExecutionMode.PARALLEL,
            max_concurrency=max_concurrency,
            on_failure=on_failure,
        )


@dataclass(frozen=True)
class PipelineStep:
    """
    A single step within a pipeline group.

    Attributes:
        name: Unique name within the group (e.g., "ingest", "normalize")
        pipeline: Registered pipeline name (e.g., "finra.otc_transparency.ingest_week")
        depends_on: List of step names this step depends on
        params: Step-specific parameter overrides

    Invariants:
        - name must be unique within group
        - pipeline must exist in registry (validated at plan resolution)
        - depends_on must reference other steps in same group
    """

    name: str
    pipeline: str
    depends_on: tuple[str, ...] = field(default_factory=tuple)
    params: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        # Normalize depends_on to tuple for immutability
        if isinstance(self.depends_on, list):
            object.__setattr__(self, "depends_on", tuple(self.depends_on))

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PipelineStep":
        """Create from dictionary (YAML/JSON deserialization)."""
        depends_on = data.get("depends_on", [])
        if isinstance(depends_on, str):
            depends_on = [depends_on]
        return cls(
            name=data["name"],
            pipeline=data["pipeline"],
            depends_on=tuple(depends_on),
            params=data.get("params", {}),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        result = {
            "name": self.name,
            "pipeline": self.pipeline,
        }
        if self.depends_on:
            result["depends_on"] = list(self.depends_on)
        if self.params:
            result["params"] = self.params
        return result


@dataclass
class PipelineGroup:
    """
    A named collection of related pipelines with dependency edges.

    Attributes:
        name: Unique group name (e.g., "finra.weekly_refresh")
        domain: Domain this group belongs to (e.g., "finra.otc_transparency")
        steps: Ordered list of pipeline steps
        description: Human-readable description
        version: Schema version for migrations
        defaults: Default parameters applied to all steps
        policy: Execution policy (sequential/parallel, failure handling)
        tags: Optional tags for filtering

    Invariants:
        - name must be globally unique
        - step names must be unique within group
        - dependencies must form a DAG (no cycles)
    """

    name: str
    steps: list[PipelineStep]
    domain: str = ""
    description: str = ""
    version: int = 1
    defaults: dict[str, Any] = field(default_factory=dict)
    policy: ExecutionPolicy = field(default_factory=ExecutionPolicy)
    tags: list[str] = field(default_factory=list)

    def __post_init__(self):
        # Validate step name uniqueness
        step_names = [s.name for s in self.steps]
        if len(step_names) != len(set(step_names)):
            duplicates = [n for n in step_names if step_names.count(n) > 1]
            raise ValueError(f"Duplicate step names: {set(duplicates)}")

    @property
    def step_names(self) -> list[str]:
        """Get list of step names in definition order."""
        return [s.name for s in self.steps]

    def get_step(self, name: str) -> PipelineStep | None:
        """Get step by name, or None if not found."""
        for step in self.steps:
            if step.name == name:
                return step
        return None

    @classmethod
    def from_steps(
        cls,
        name: str,
        steps: list[PipelineStep],
        **kwargs,
    ) -> "PipelineGroup":
        """Factory method for creating a group from a list of steps."""
        return cls(name=name, steps=steps, **kwargs)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PipelineGroup":
        """Create from dictionary (YAML/JSON deserialization)."""
        # Handle nested metadata/spec structure (YAML format)
        if "metadata" in data:
            metadata = data["metadata"]
            spec = data.get("spec", {})
            name = metadata["name"]
            domain = metadata.get("domain", "")
            description = metadata.get("description", "")
            version = metadata.get("version", 1)
            tags = metadata.get("tags", [])
            defaults = spec.get("defaults", {})
            steps_data = spec.get("pipelines", [])
            policy_data = spec.get("policy", {})
        else:
            # Flat structure
            name = data["name"]
            domain = data.get("domain", "")
            description = data.get("description", "")
            version = data.get("version", 1)
            tags = data.get("tags", [])
            defaults = data.get("defaults", {})
            steps_data = data.get("steps", data.get("pipelines", []))
            policy_data = data.get("policy", {})

        # Parse steps
        steps = [PipelineStep.from_dict(s) for s in steps_data]

        # Parse policy
        policy = ExecutionPolicy(
            mode=ExecutionMode(policy_data.get("execution", "sequential")),
            max_concurrency=policy_data.get("max_concurrency", 4),
            on_failure=FailurePolicy(policy_data.get("on_failure", "stop")),
            timeout_minutes=policy_data.get("timeout_minutes"),
        )

        return cls(
            name=name,
            domain=domain,
            description=description,
            version=version,
            tags=tags,
            defaults=defaults,
            steps=steps,
            policy=policy,
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization (flat format)."""
        return {
            "name": self.name,
            "domain": self.domain,
            "description": self.description,
            "version": self.version,
            "tags": self.tags,
            "defaults": self.defaults,
            "steps": [s.to_dict() for s in self.steps],
            "policy": {
                "execution": self.policy.mode.value,
                "max_concurrency": self.policy.max_concurrency,
                "on_failure": self.policy.on_failure.value,
                "timeout_minutes": self.policy.timeout_minutes,
            },
        }


# =============================================================================
# Execution Plan Models (output of PlanResolver)
# =============================================================================


@dataclass(frozen=True)
class PlannedStep:
    """
    A single step in a resolved execution plan.

    This is the "compiled" form of a PipelineStep with:
    - Merged parameters (defaults + run params + step params)
    - Resolved topological order
    """

    step_name: str
    pipeline_name: str
    params: dict[str, Any]
    depends_on: tuple[str, ...]
    sequence_order: int

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "step_name": self.step_name,
            "pipeline_name": self.pipeline_name,
            "params": self.params,
            "depends_on": list(self.depends_on),
            "sequence_order": self.sequence_order,
        }


@dataclass
class ExecutionPlan:
    """
    Resolved execution plan for a pipeline group.

    Created by PlanResolver.resolve() - this is what the GroupExecutor runs.

    Attributes:
        group_name: Name of the source group
        group_version: Version of the group at resolution time
        batch_id: Unique batch ID for this run (links child executions)
        steps: Topologically sorted list of steps to execute
        policy: Execution policy from the group
        params: Runtime parameters passed to resolve()
        resolved_at: When this plan was created
    """

    group_name: str
    group_version: int
    batch_id: str
    steps: list[PlannedStep]
    policy: ExecutionPolicy
    params: dict[str, Any] = field(default_factory=dict)
    resolved_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def step_count(self) -> int:
        """Number of steps in the plan."""
        return len(self.steps)

    def get_step(self, name: str) -> PlannedStep | None:
        """Get planned step by name."""
        for step in self.steps:
            if step.step_name == name:
                return step
        return None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "group_name": self.group_name,
            "group_version": self.group_version,
            "batch_id": self.batch_id,
            "steps": [s.to_dict() for s in self.steps],
            "policy": {
                "execution": self.policy.mode.value,
                "max_concurrency": self.policy.max_concurrency,
                "on_failure": self.policy.on_failure.value,
            },
            "params": self.params,
            "resolved_at": self.resolved_at.isoformat(),
        }
