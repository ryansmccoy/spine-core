"""
Workflow - Named collection of steps with context passing.

A Workflow is similar to a PipelineGroup but supports:
- Lambda steps (inline functions) in addition to pipeline steps
- Context passing between steps (outputs flow to next step)
- Quality gates (steps can fail on data quality)

Think of it as PipelineGroup v2 with Step Functions-style semantics.

Tier: Basic (spine-core)

Relationship to PipelineGroup:
- PipelineGroup: Static DAG of registered pipelines, no data passing
- Workflow: Context-aware sequence of steps with data passing

Both can coexist. PipelineGroups are simpler for pure orchestration.
Workflows add data flow when you need validation, routing, or lambdas.

Example:
    from spine.orchestration import Workflow, Step, StepResult

    def validate_fn(ctx, config):
        count = ctx.get_output("ingest", "record_count", 0)
        if count < 100:
            return StepResult.fail("Too few records")
        return StepResult.ok(output={"validated": True})

    workflow = Workflow(
        name="finra.weekly_refresh",
        domain="finra.otc_transparency",
        steps=[
            Step.pipeline("ingest", "finra.otc_transparency.ingest_week"),
            Step.lambda_("validate", validate_fn),
            Step.pipeline("normalize", "finra.otc_transparency.normalize_week"),
        ],
    )
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from spine.orchestration.step_types import Step, StepType


@dataclass
class Workflow:
    """
    A named workflow with ordered steps.

    Attributes:
        name: Unique workflow name (e.g., "finra.weekly_refresh")
        steps: Ordered list of steps to execute
        domain: Domain this workflow belongs to (optional)
        description: Human-readable description
        version: Schema version for migrations
        defaults: Default parameters applied to all steps
        tags: Optional tags for filtering/organization
    """

    name: str
    steps: list[Step]
    domain: str = ""
    description: str = ""
    version: int = 1
    defaults: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)

    def __post_init__(self):
        """Validate workflow structure."""
        self._validate_steps()

    def _validate_steps(self) -> None:
        """Validate step names are unique and references are valid."""
        step_names = set()

        for step in self.steps:
            # Check uniqueness
            if step.name in step_names:
                raise ValueError(f"Duplicate step name: {step.name}")
            step_names.add(step.name)

        # Validate choice step references
        for step in self.steps:
            if step.step_type == StepType.CHOICE:
                if step.then_step and step.then_step not in step_names:
                    raise ValueError(
                        f"Choice step '{step.name}' references unknown then_step: {step.then_step}"
                    )
                if step.else_step and step.else_step not in step_names:
                    raise ValueError(
                        f"Choice step '{step.name}' references unknown else_step: {step.else_step}"
                    )

    # =========================================================================
    # Accessors
    # =========================================================================

    def get_step(self, name: str) -> Step | None:
        """Get step by name."""
        for step in self.steps:
            if step.name == name:
                return step
        return None

    def step_names(self) -> list[str]:
        """Get ordered list of step names."""
        return [s.name for s in self.steps]

    def step_index(self, name: str) -> int:
        """Get index of step by name, or -1 if not found."""
        for i, step in enumerate(self.steps):
            if step.name == name:
                return i
        return -1

    # =========================================================================
    # Tier Analysis
    # =========================================================================

    def required_tier(self) -> str:
        """
        Determine minimum tier required to run this workflow.

        Returns:
            "basic", "intermediate", or "advanced"
        """
        for step in self.steps:
            if step.is_advanced_tier():
                return "advanced"

        for step in self.steps:
            if step.is_intermediate_tier():
                return "intermediate"

        return "basic"

    def has_choice_steps(self) -> bool:
        """Check if workflow uses conditional branching."""
        return any(s.step_type == StepType.CHOICE for s in self.steps)

    def has_lambda_steps(self) -> bool:
        """Check if workflow uses inline lambda functions."""
        return any(s.step_type == StepType.LAMBDA for s in self.steps)

    def has_pipeline_steps(self) -> bool:
        """Check if workflow uses registered pipelines."""
        return any(s.step_type == StepType.PIPELINE for s in self.steps)

    def pipeline_names(self) -> list[str]:
        """Get list of all pipeline names referenced by pipeline steps."""
        return [
            s.pipeline_name
            for s in self.steps
            if s.step_type == StepType.PIPELINE and s.pipeline_name
        ]

    # =========================================================================
    # Serialization
    # =========================================================================

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary for YAML/JSON."""
        result: dict[str, Any] = {
            "name": self.name,
            "version": self.version,
            "steps": [s.to_dict() for s in self.steps],
        }

        if self.domain:
            result["domain"] = self.domain
        if self.description:
            result["description"] = self.description
        if self.defaults:
            result["defaults"] = self.defaults
        if self.tags:
            result["tags"] = self.tags

        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Workflow":
        """
        Deserialize from dictionary.

        Note: Lambda steps cannot be loaded from YAML (no handler).
        Only pipeline and choice steps are supported for YAML loading.
        """
        steps = []
        for step_data in data.get("steps", []):
            step_type = step_data.get("type", "pipeline")

            if step_type == "pipeline":
                steps.append(Step.pipeline(
                    name=step_data["name"],
                    pipeline_name=step_data["pipeline"],
                    params=step_data.get("config"),
                ))
            elif step_type == "choice":
                # Choice steps from YAML need a condition expression (future)
                raise ValueError(
                    "Choice steps cannot be loaded from YAML yet (condition is a function)"
                )
            else:
                raise ValueError(f"Unknown step type in YAML: {step_type}")

        return cls(
            name=data["name"],
            steps=steps,
            domain=data.get("domain", ""),
            description=data.get("description", ""),
            version=data.get("version", 1),
            defaults=data.get("defaults", {}),
            tags=data.get("tags", []),
        )

    def __repr__(self) -> str:
        return f"Workflow({self.name!r}, steps={len(self.steps)}, tier={self.required_tier()})"
