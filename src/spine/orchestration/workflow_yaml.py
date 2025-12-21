"""Pydantic models for Workflow YAML validation.

Mirrors the GroupSpec / yaml_models pattern for the v2 Workflow system.
Provides strong typing and validation for YAML-based workflow definitions.

Usage::

    from spine.orchestration.workflow_yaml import WorkflowSpec

    spec = WorkflowSpec.model_validate(yaml_data)
    workflow = spec.to_workflow()

    # Or from a YAML string / file
    spec = WorkflowSpec.from_yaml(yaml_content)
    spec = WorkflowSpec.from_yaml_file("workflows/ingest.yaml")

Example YAML::

    apiVersion: spine.io/v1
    kind: Workflow
    metadata:
      name: ingest.daily
      domain: ingest
      description: Daily ingest operation
    spec:
      steps:
        - name: fetch
          operation: ingest.fetch_data
        - name: normalize
          operation: ingest.normalize
          depends_on: [fetch]
        - name: store
          operation: ingest.store
          depends_on: [normalize]
      policy:
        execution: parallel
        max_concurrency: 4
        on_failure: stop

Manifesto:
    Workflow authors should be able to define pipelines in YAML
    without writing Python.  This module parses YAML definitions
    into the same Workflow model used by code-first authors,
    keeping both paths first-class.

Tags:
    spine-core, orchestration, yaml, declarative, config-driven

Doc-Types:
    api-reference
"""

from __future__ import annotations

from typing import Any, Literal

try:
    from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
except ImportError as _exc:
    raise ImportError(
        "spine.orchestration.workflow_yaml requires pydantic. "
        "Install it with: pip install spine-core[models]"
    ) from _exc

from spine.orchestration.step_types import Step, StepType
from spine.orchestration.workflow import (
    ExecutionMode,
    FailurePolicy,
    Workflow,
    WorkflowExecutionPolicy,
)


class WorkflowMetadataSpec(BaseModel):
    """Metadata section of a workflow spec."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, description="Unique workflow name")
    domain: str = Field(default="", description="Domain this workflow belongs to")
    version: int = Field(default=1, ge=1, description="Schema version")
    description: str = Field(default="", description="Human-readable description")
    tags: list[str] = Field(default_factory=list, description="Optional tags for filtering")


class WorkflowPolicySpec(BaseModel):
    """Execution policy section of a workflow spec."""

    model_config = ConfigDict(extra="forbid")

    execution: ExecutionMode = Field(
        default=ExecutionMode.SEQUENTIAL,
        description="Sequential or parallel execution",
    )
    max_concurrency: int = Field(default=4, ge=1, description="Max concurrent steps")
    on_failure: FailurePolicy = Field(
        default=FailurePolicy.STOP,
        description="Stop or continue on failure",
    )
    timeout_seconds: int | None = Field(
        default=None, ge=1, description="Global timeout for workflow execution"
    )

    def to_execution_policy(self) -> WorkflowExecutionPolicy:
        """Convert to WorkflowExecutionPolicy dataclass."""
        return WorkflowExecutionPolicy(
            mode=self.execution,
            max_concurrency=self.max_concurrency,
            timeout_seconds=self.timeout_seconds,
            on_failure=self.on_failure,
        )


class WorkflowStepSpec(BaseModel):
    """Workflow step specification (supports all step types).

    Operation steps require `operation`. Lambda steps use `handler_ref`.
    Choice steps use `condition_ref`, `then_step`, `else_step`.
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, description="Unique step name within workflow")
    type: str = Field(default="operation", description="Step type: operation, lambda, choice, wait, map")
    operation: str | None = Field(default=None, description="Registered operation name (for operation steps)")
    depends_on: list[str] = Field(default_factory=list, description="Step dependencies")
    params: dict[str, Any] = Field(default_factory=dict, description="Step-specific parameters (maps to config)")
    config: dict[str, Any] | None = Field(default=None, description="Step configuration (alternative to params)")

    # Lambda step fields
    handler_ref: str | None = Field(default=None, description="Handler reference for lambda steps (module:qualname)")

    # Choice step fields
    condition_ref: str | None = Field(default=None, description="Condition reference for choice steps")
    then_step: str | None = Field(default=None, description="Step to execute if condition is true")
    else_step: str | None = Field(default=None, description="Step to execute if condition is false")

    # Wait step fields
    duration_seconds: int | None = Field(default=None, description="Duration for wait steps")

    # Map step fields
    items_path: str | None = Field(default=None, description="JSONPath to items for map steps")
    iterator_workflow: str | None = Field(default=None, description="Workflow to run for each item")
    max_concurrency: int | None = Field(default=None, description="Max concurrent iterations for map")

    # Error handling
    on_error: str | None = Field(default=None, description="Error policy: stop or continue")

    def to_step(self) -> Step:
        """Convert to Step dataclass."""
        from spine.orchestration.step_types import resolve_callable_ref

        step_config = self.config or self.params or {}
        depends = tuple(self.depends_on) if self.depends_on else ()

        if self.type == "operation":
            return Step.operation(
                name=self.name,
                operation_name=self.operation or "",
                params=step_config or None,
                depends_on=depends,
            )
        elif self.type == "lambda":
            handler = None
            if self.handler_ref:
                try:
                    handler = resolve_callable_ref(self.handler_ref)
                except (ImportError, AttributeError, TypeError, ValueError):
                    handler = None
            return Step.lambda_(
                name=self.name,
                handler=handler or (lambda ctx, cfg: None),
                config=step_config or None,
                depends_on=list(depends),
            )
        elif self.type == "choice":
            condition = None
            if self.condition_ref:
                try:
                    condition = resolve_callable_ref(self.condition_ref)
                except (ImportError, AttributeError, TypeError, ValueError):
                    condition = None
            step = Step.choice(
                name=self.name,
                condition=condition or (lambda ctx: False),
                then_step=self.then_step or "",
                else_step=self.else_step,
            )
            step.depends_on = depends
            return step
        elif self.type == "wait":
            step = Step.wait(
                name=self.name,
                duration_seconds=self.duration_seconds or 0,
            )
            step.depends_on = depends
            return step
        elif self.type == "map":
            step = Step.map(
                name=self.name,
                items_path=self.items_path or "",
                iterator_workflow=self.iterator_workflow,
                max_concurrency=self.max_concurrency or 4,
            )
            step.depends_on = depends
            return step
        else:
            # Fallback: treat as operation
            return Step.operation(
                name=self.name,
                operation_name=self.operation or f"__unknown__{self.type}__",
                params=step_config or None,
                depends_on=depends,
            )


class WorkflowSpecSection(BaseModel):
    """The 'spec' section containing steps, defaults, and policy."""

    model_config = ConfigDict(extra="forbid")

    defaults: dict[str, Any] = Field(
        default_factory=dict,
        description="Default parameters applied to all steps",
    )
    steps: list[WorkflowStepSpec] = Field(
        ...,
        min_length=1,
        description="Workflow steps",
    )
    policy: WorkflowPolicySpec = Field(
        default_factory=WorkflowPolicySpec,
        description="Execution policy",
    )

    @field_validator("steps")
    @classmethod
    def validate_unique_names(cls, v: list[WorkflowStepSpec]) -> list[WorkflowStepSpec]:
        """Ensure step names are unique."""
        names = [step.name for step in v]
        if len(names) != len(set(names)):
            duplicates = [n for n in names if names.count(n) > 1]
            raise ValueError(f"Duplicate step names: {set(duplicates)}")
        return v

    @model_validator(mode="after")
    def validate_dependencies(self) -> WorkflowSpecSection:
        """Ensure depends_on references valid step names."""
        step_names = {step.name for step in self.steps}
        for step in self.steps:
            invalid = set(step.depends_on) - step_names
            if invalid:
                raise ValueError(
                    f"Step '{step.name}' depends on unknown steps: {invalid}"
                )
            if step.name in step.depends_on:
                raise ValueError(f"Step '{step.name}' cannot depend on itself")
        return self


class WorkflowSpec(BaseModel):
    """Complete YAML workflow specification.

    This is the root model for parsing YAML workflow definitions.

    Example YAML::

        apiVersion: spine.io/v1
        kind: Workflow
        metadata:
          name: ingest.daily
          domain: ingest
        spec:
          steps:
            - name: fetch
              operation: ingest.fetch_data
            - name: normalize
              operation: ingest.normalize
              depends_on: [fetch]
          policy:
            execution: parallel
            max_concurrency: 4
    """

    model_config = ConfigDict(extra="forbid")

    apiVersion: Literal["spine.io/v1"] = Field(
        default="spine.io/v1",
        description="API version, must be spine.io/v1",
    )
    kind: Literal["Workflow"] = Field(
        default="Workflow",
        description="Resource kind, must be Workflow",
    )
    metadata: WorkflowMetadataSpec = Field(..., description="Workflow metadata")
    spec: WorkflowSpecSection = Field(..., description="Workflow specification")

    def to_workflow(self) -> Workflow:
        """Convert validated spec to Workflow dataclass.

        Returns
        -------
        Workflow
            The validated and converted workflow.
        """
        steps = [step.to_step() for step in self.spec.steps]
        policy = self.spec.policy.to_execution_policy()

        return Workflow(
            name=self.metadata.name,
            steps=steps,
            domain=self.metadata.domain,
            description=self.metadata.description,
            version=self.metadata.version,
            defaults=self.spec.defaults,
            tags=self.metadata.tags,
            execution_policy=policy,
        )

    @classmethod
    def from_yaml(cls, yaml_content: str) -> WorkflowSpec:
        """Parse and validate YAML content.

        Parameters
        ----------
        yaml_content
            Raw YAML string.

        Returns
        -------
        WorkflowSpec
            Validated workflow specification.

        Raises
        ------
        ValueError
            If YAML is invalid or doesn't match schema.
        """
        try:
            import yaml
        except ImportError:
            raise ImportError(
                "PyYAML is required for YAML parsing. Install with: pip install pyyaml"
            ) from None

        try:
            data = yaml.safe_load(yaml_content)
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML: {e}") from e

        return cls.model_validate(data)

    @classmethod
    def from_yaml_file(cls, path: str) -> WorkflowSpec:
        """Load and validate from a YAML file.

        Parameters
        ----------
        path
            Path to YAML file.

        Returns
        -------
        WorkflowSpec
            Validated workflow specification.
        """
        from pathlib import Path

        content = Path(path).read_text(encoding="utf-8")
        return cls.from_yaml(content)

    @classmethod
    def from_workflow(cls, workflow: Workflow) -> WorkflowSpec:
        """Build a ``WorkflowSpec`` from a runtime ``Workflow`` instance.

        All step types are now supported. Lambda and choice steps include
        their handler/condition refs if available.

        Parameters
        ----------
        workflow
            The workflow to convert.

        Returns
        -------
        WorkflowSpec
            A validated Pydantic model ready for ``to_workflow()`` or
            YAML serialisation.
        """
        from spine.orchestration.step_types import _callable_ref

        metadata = WorkflowMetadataSpec(
            name=workflow.name,
            domain=workflow.domain,
            version=workflow.version,
            description=workflow.description,
            tags=list(workflow.tags) if workflow.tags else [],
        )

        step_specs: list[WorkflowStepSpec] = []
        for step in workflow.steps:
            depends = list(step.depends_on) if step.depends_on else []
            config = step.config or {}

            if step.step_type == StepType.OPERATION:
                step_specs.append(
                    WorkflowStepSpec(
                        name=step.name,
                        type="operation",
                        operation=step.operation_name or "",
                        depends_on=depends,
                        config=config if config else None,
                    )
                )
            elif step.step_type == StepType.LAMBDA:
                step_specs.append(
                    WorkflowStepSpec(
                        name=step.name,
                        type="lambda",
                        handler_ref=_callable_ref(step.handler),
                        depends_on=depends,
                        config=config if config else None,
                    )
                )
            elif step.step_type == StepType.CHOICE:
                step_specs.append(
                    WorkflowStepSpec(
                        name=step.name,
                        type="choice",
                        condition_ref=_callable_ref(step.condition),
                        then_step=step.then_step,
                        else_step=step.else_step,
                        depends_on=depends,
                    )
                )
            elif step.step_type == StepType.WAIT:
                step_specs.append(
                    WorkflowStepSpec(
                        name=step.name,
                        type="wait",
                        duration_seconds=step.duration_seconds,
                        depends_on=depends,
                    )
                )
            elif step.step_type == StepType.MAP:
                step_specs.append(
                    WorkflowStepSpec(
                        name=step.name,
                        type="map",
                        items_path=step.items_path,
                        iterator_workflow=str(step.iterator_workflow) if step.iterator_workflow else None,
                        max_concurrency=step.max_concurrency,
                        depends_on=depends,
                    )
                )

        ep = workflow.execution_policy
        policy_spec = WorkflowPolicySpec(
            execution=ep.mode.value,
            max_concurrency=ep.max_concurrency,
            on_failure=ep.on_failure.value,
            timeout_seconds=ep.timeout_seconds,
        )

        section = WorkflowSpecSection(
            defaults=dict(workflow.defaults) if workflow.defaults else {},
            steps=step_specs,
            policy=policy_spec,
        )

        return cls(
            metadata=metadata,
            spec=section,
        )


def validate_yaml_workflow(data: dict[str, Any]) -> Workflow:
    """Validate a dict as a workflow spec and return Workflow.

    Convenience function for integrating typed validation
    into existing loaders.

    Parameters
    ----------
    data
        Dictionary from YAML parse.

    Returns
    -------
    Workflow
        Validated workflow.

    Raises
    ------
    pydantic.ValidationError
        If validation fails.
    """
    spec = WorkflowSpec.model_validate(data)
    return spec.to_workflow()
