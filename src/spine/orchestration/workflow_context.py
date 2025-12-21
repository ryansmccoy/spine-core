"""
Workflow Context - Immutable context passed step-to-step.

This is the central primitive for Orchestration v2. Every step receives
a WorkflowContext and returns updates that are merged into a NEW context
for the next step. The original context is never mutated.

Tier: Basic (spine-core)

Design Principles:
- Immutable: Steps return updates, runner creates new context
- Thread-safe: No shared mutable state
- Serializable: Can checkpoint to database or JSON
- Composable: Integrates with ExecutionContext for lineage

Example:
    from spine.orchestration import WorkflowContext, StepResult

    def my_step(ctx: WorkflowContext, config: dict) -> StepResult:
        # Read from context
        tier = ctx.params.get("tier")
        prior_count = ctx.get_output("ingest", "record_count", 0)

        # Do work...

        # Return updates (runner merges into new context)
        return StepResult.ok(
            output={"processed": 100},
            context_updates={"last_step": "my_step"},
        )

Manifesto:
    Steps need to share state without coupling to each other.
    WorkflowContext provides a controlled, immutable-snapshot
    namespace so each step reads a consistent view and writes
    are batched between steps.

Tags:
    spine-core, orchestration, context, shared-state, immutable-snapshot

Doc-Types:
    api-reference
"""

from __future__ import annotations

import copy
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from spine.core import ExecutionContext, new_context


@dataclass
class WorkflowContext:
    """
    Immutable context that flows through workflow steps.

    Attributes:
        run_id: Unique identifier for this workflow run
        workflow_name: Name of the workflow being executed
        params: Input parameters and accumulated state
        outputs: Step outputs keyed by step name
        partition: Optional partition key for tracking (e.g., {"tier": "NMS_TIER_1"})
        execution: ExecutionContext for lineage tracking
        started_at: When this workflow run began
        metadata: Additional metadata (e.g., caller info, dry_run flag)
    """

    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    workflow_name: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    outputs: dict[str, dict[str, Any]] = field(default_factory=dict)
    partition: dict[str, Any] = field(default_factory=dict)
    execution: ExecutionContext = field(default_factory=new_context)
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = field(default_factory=dict)

    # =========================================================================
    # Factories
    # =========================================================================

    @classmethod
    def create(
        cls,
        workflow_name: str,
        params: dict[str, Any] | None = None,
        partition: dict[str, Any] | None = None,
        batch_id: str | None = None,
        run_id: str | None = None,
        dry_run: bool = False,
    ) -> WorkflowContext:
        """
        Create a new workflow context.

        Args:
            workflow_name: Name of the workflow
            params: Input parameters
            partition: Partition key for tracking
            batch_id: Optional batch ID for lineage
            run_id: Optional run ID (generated if not provided)
            dry_run: Whether this is a dry run (no side effects)
        """
        execution = new_context(batch_id=batch_id)
        metadata = {"dry_run": dry_run}

        return cls(
            run_id=run_id or str(uuid.uuid4()),
            workflow_name=workflow_name,
            params=params or {},
            partition=partition or {},
            execution=execution,
            metadata=metadata,
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkflowContext:
        """Deserialize from dictionary (for checkpoint resume)."""
        execution_data = data.get("execution", {})
        execution = ExecutionContext(
            execution_id=execution_data.get("execution_id", str(uuid.uuid4())),
            batch_id=execution_data.get("batch_id"),
            parent_execution_id=execution_data.get("parent_execution_id"),
        )

        started_at = data.get("started_at")
        if isinstance(started_at, str):
            started_at = datetime.fromisoformat(started_at)

        return cls(
            run_id=data.get("run_id", str(uuid.uuid4())),
            workflow_name=data.get("workflow_name", ""),
            params=data.get("params", {}),
            outputs=data.get("outputs", {}),
            partition=data.get("partition", {}),
            execution=execution,
            started_at=started_at or datetime.now(UTC),
            metadata=data.get("metadata", {}),
        )

    # =========================================================================
    # Accessors (read-only)
    # =========================================================================

    def get_param(self, key: str, default: Any = None) -> Any:
        """Get a parameter value."""
        return self.params.get(key, default)

    def get_output(
        self,
        step_name: str,
        key: str | None = None,
        default: Any = None,
    ) -> Any:
        """
        Get output from a prior step.

        Args:
            step_name: Name of the step
            key: Optional key within the step's output
            default: Default value if not found

        Returns:
            The output value, or default if not found
        """
        step_output = self.outputs.get(step_name, {})
        if key is None:
            return step_output if step_output else default
        return step_output.get(key, default)

    def has_output(self, step_name: str) -> bool:
        """Check if a step has produced output."""
        return step_name in self.outputs

    @property
    def is_dry_run(self) -> bool:
        """Check if this is a dry run."""
        return self.metadata.get("dry_run", False)

    @property
    def execution_id(self) -> str:
        """Get execution ID for lineage."""
        return self.execution.execution_id

    @property
    def batch_id(self) -> str | None:
        """Get batch ID for lineage."""
        return self.execution.batch_id

    # =========================================================================
    # Mutation (returns new context)
    # =========================================================================

    def with_output(self, step_name: str, output: dict[str, Any]) -> WorkflowContext:
        """
        Create new context with step output added.

        This is called by the runner after each step completes.
        """
        new_outputs = copy.deepcopy(self.outputs)
        new_outputs[step_name] = output
        return self._copy_with(outputs=new_outputs)

    def with_params(self, updates: dict[str, Any]) -> WorkflowContext:
        """
        Create new context with params merged.

        This is called by the runner when a step returns context_updates.
        """
        new_params = {**self.params, **updates}
        return self._copy_with(params=new_params)

    def with_metadata(self, updates: dict[str, Any]) -> WorkflowContext:
        """Create new context with metadata merged."""
        new_metadata = {**self.metadata, **updates}
        return self._copy_with(metadata=new_metadata)

    def _copy_with(self, **overrides: Any) -> WorkflowContext:
        """Create a copy with specific fields overridden."""
        return WorkflowContext(
            run_id=overrides.get("run_id", self.run_id),
            workflow_name=overrides.get("workflow_name", self.workflow_name),
            params=overrides.get("params", copy.deepcopy(self.params)),
            outputs=overrides.get("outputs", copy.deepcopy(self.outputs)),
            partition=overrides.get("partition", copy.deepcopy(self.partition)),
            execution=overrides.get("execution", self.execution),
            started_at=overrides.get("started_at", self.started_at),
            metadata=overrides.get("metadata", copy.deepcopy(self.metadata)),
        )

    # =========================================================================
    # Serialization
    # =========================================================================

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary (for checkpointing)."""
        return {
            "run_id": self.run_id,
            "workflow_name": self.workflow_name,
            "params": self.params,
            "outputs": self.outputs,
            "partition": self.partition,
            "execution": {
                "execution_id": self.execution.execution_id,
                "batch_id": self.execution.batch_id,
                "parent_execution_id": self.execution.parent_execution_id,
            },
            "started_at": self.started_at.isoformat(),
            "metadata": self.metadata,
        }

    def __repr__(self) -> str:
        return (
            f"WorkflowContext(run_id={self.run_id!r}, "
            f"workflow={self.workflow_name!r}, "
            f"steps={list(self.outputs.keys())})"
        )
