"""Workflow — named collection of steps with dependency graph.

Manifesto:
    Operations do one thing well; Workflows compose multiple operations (and
lambda/choice/wait steps) into a reliable, observable multi-step process.
The Workflow dataclass is the ‘‘blueprint’’ — it declares **what** to run and
in what order, but never **how** to run it (that’s WorkflowRunner’s job).

ARCHITECTURE
────────────
::

    Workflow           ── defines steps, dependencies, defaults, policy
      ├── steps[]        ── ordered list of Step objects
      ├── execution_policy ─ sequential vs parallel, concurrency, timeout
      ├── defaults{}     ── default params merged into context
      └── domain         ── logical grouping (e.g. "finra.otc")

    WorkflowRunner.execute(workflow, params)   → WorkflowResult
    TrackedWorkflowRunner.execute(...)         → WorkflowResult + DB record

KEY CLASSES
───────────
- ``Workflow``          — the step graph (this module)
- ``ExecutionMode``     — SEQUENTIAL or PARALLEL
- ``FailurePolicy``     — STOP or CONTINUE on step failure
- ``WorkflowExecutionPolicy`` — groups mode + concurrency + timeout

Related modules:
    step_types.py          — Step definitions (lambda, operation, choice)
    workflow_runner.py     — executes the workflow
    workflow_context.py    — immutable context passed between steps

Example::

    from spine.orchestration import Workflow, Step, StepResult

    workflow = Workflow(
        name="finra.weekly_refresh",
        domain="finra.otc_transparency",
        steps=[
            Step.operation("ingest", "finra.otc_transparency.ingest_week"),
            Step.lambda_("validate", validate_fn),
            Step.operation("normalize", "finra.otc_transparency.normalize_week"),
        ],
    )

Tags:
    spine-core, orchestration, workflow, DAG, steps, conditions

Doc-Types:
    api-reference
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from spine.orchestration.step_types import Step, StepType


class ExecutionMode(str, Enum):
    """Workflow execution mode."""

    SEQUENTIAL = "sequential"  # Default: step-by-step
    PARALLEL = "parallel"  # DAG-based parallel execution


class FailurePolicy(str, Enum):
    """What to do when a step fails during parallel execution."""

    STOP = "stop"  # Cancel pending steps, wait for running
    CONTINUE = "continue"  # Continue with independent branches


@dataclass(frozen=True)
class WorkflowExecutionPolicy:
    """
    Controls how a workflow is executed.

    Attributes:
        mode: Sequential (default) or parallel (DAG-based)
        max_concurrency: Max parallel steps (parallel mode only)
        timeout_seconds: Overall workflow timeout
        on_failure: What to do when a step fails
    """

    mode: ExecutionMode = ExecutionMode.SEQUENTIAL
    max_concurrency: int = 4
    timeout_seconds: int | None = None
    on_failure: FailurePolicy = FailurePolicy.STOP


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
        execution_policy: Controls sequential/parallel execution
    """

    name: str
    steps: list[Step]
    domain: str = ""
    description: str = ""
    version: int = 1
    defaults: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    execution_policy: WorkflowExecutionPolicy = field(default_factory=WorkflowExecutionPolicy)

    def __post_init__(self):
        """Validate workflow structure."""
        self._validate_steps()
        self._validate_dependencies()
        self._validate_no_cycles()

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
                    raise ValueError(f"Choice step '{step.name}' references unknown then_step: {step.then_step}")
                if step.else_step and step.else_step not in step_names:
                    raise ValueError(f"Choice step '{step.name}' references unknown else_step: {step.else_step}")

    def _validate_dependencies(self) -> None:
        """Validate that all depends_on references point to existing steps."""
        step_names = {s.name for s in self.steps}
        for step in self.steps:
            for dep in step.depends_on:
                if dep == step.name:
                    raise ValueError(f"Step '{step.name}' depends on itself")
                if dep not in step_names:
                    raise ValueError(f"Step '{step.name}' depends on unknown step: '{dep}'")

    def _validate_no_cycles(self) -> None:
        """Validate the dependency graph has no cycles (Kahn's algorithm)."""
        if not any(step.depends_on for step in self.steps):
            return  # No deps — sequential by default, no cycles possible

        # Build adjacency list and in-degree map
        adjacency: dict[str, list[str]] = defaultdict(list)
        in_degree: dict[str, int] = {s.name: 0 for s in self.steps}

        for step in self.steps:
            for dep in step.depends_on:
                adjacency[dep].append(step.name)
                in_degree[step.name] += 1

        # Kahn's algorithm
        queue: deque[str] = deque(name for name, deg in in_degree.items() if deg == 0)
        visited = 0

        while queue:
            node = queue.popleft()
            visited += 1
            for neighbor in adjacency[node]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if visited != len(self.steps):
            # Find the cycle for a helpful error message
            cycle_nodes = [name for name, deg in in_degree.items() if deg > 0]
            raise ValueError(f"Dependency cycle detected among steps: {cycle_nodes}")

    def has_dependencies(self) -> bool:
        """Check if any steps have dependency edges."""
        return any(step.depends_on for step in self.steps)

    def dependency_graph(self) -> dict[str, list[str]]:
        """Return adjacency list of step dependencies (dep -> dependents)."""
        graph: dict[str, list[str]] = defaultdict(list)
        for step in self.steps:
            for dep in step.depends_on:
                graph[dep].append(step.name)
        return dict(graph)

    def topological_order(self) -> list[str]:
        """Return steps in topological order (respecting depends_on).

        Steps with no dependencies come first. If no depends_on edges exist,
        returns list-order.
        """
        if not self.has_dependencies():
            return [s.name for s in self.steps]

        in_degree: dict[str, int] = {s.name: 0 for s in self.steps}
        adjacency: dict[str, list[str]] = defaultdict(list)

        for step in self.steps:
            for dep in step.depends_on:
                adjacency[dep].append(step.name)
                in_degree[step.name] += 1

        queue: deque[str] = deque(
            name for name, deg in in_degree.items() if deg == 0
        )
        result: list[str] = []

        while queue:
            node = queue.popleft()
            result.append(node)
            for neighbor in adjacency[node]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        return result

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

    def has_operation_steps(self) -> bool:
        """Check if workflow uses registered operations."""
        return any(s.step_type == StepType.OPERATION for s in self.steps)

    def operation_names(self) -> list[str]:
        """Get list of all operation names referenced by operation steps."""
        return [s.operation_name for s in self.steps if s.step_type == StepType.OPERATION and s.operation_name]

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

        # Include execution_policy if non-default
        ep = self.execution_policy
        if ep.mode != ExecutionMode.SEQUENTIAL or ep.max_concurrency != 4 or ep.timeout_seconds or ep.on_failure != FailurePolicy.STOP:
            policy: dict[str, Any] = {"mode": ep.mode.value}
            if ep.max_concurrency != 4:
                policy["max_concurrency"] = ep.max_concurrency
            if ep.timeout_seconds:
                policy["timeout_seconds"] = ep.timeout_seconds
            if ep.on_failure != FailurePolicy.STOP:
                policy["on_failure"] = ep.on_failure.value
            result["execution_policy"] = policy

        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Workflow:
        """Deserialize from dictionary.

        Supports all step types.  Lambda and choice steps require a
        ``handler_ref`` / ``condition_ref`` field (``'module:qualname'``) so
        the callable can be resolved at load time.  Steps without a resolvable
        ref are created with ``handler=None`` / ``condition=None`` — the caller
        must wire them before execution.
        """
        from spine.orchestration.step_types import resolve_callable_ref

        steps: list[Step] = []
        for sd in data.get("steps", []):
            step_type = sd.get("type", "operation")
            depends_on = tuple(sd.get("depends_on", []))

            if step_type == "operation":
                steps.append(
                    Step.operation(
                        name=sd["name"],
                        operation_name=sd["operation"],
                        params=sd.get("config"),
                        depends_on=depends_on,
                    )
                )
            elif step_type == "lambda":
                handler = None
                ref = sd.get("handler_ref")
                if ref:
                    try:
                        handler = resolve_callable_ref(ref)
                    except (ImportError, AttributeError, TypeError, ValueError):
                        handler = None
                steps.append(
                    Step.lambda_(
                        name=sd["name"],
                        handler=handler or (lambda ctx, cfg: None),
                        config=sd.get("config"),
                        depends_on=depends_on,
                    )
                )
            elif step_type == "choice":
                condition = None
                cref = sd.get("condition_ref")
                if cref:
                    try:
                        condition = resolve_callable_ref(cref)
                    except (ImportError, AttributeError, TypeError, ValueError):
                        condition = None
                step = Step.choice(
                    name=sd["name"],
                    condition=condition or (lambda ctx: False),
                    then_step=sd.get("then_step", ""),
                    else_step=sd.get("else_step"),
                )
                # Set depends_on directly since choice() doesn't accept it
                step.depends_on = depends_on
                steps.append(step)
            elif step_type == "wait":
                step = Step.wait(
                    name=sd["name"],
                    duration_seconds=sd.get("duration_seconds", 0),
                )
                step.depends_on = depends_on
                steps.append(step)
            elif step_type == "map":
                step = Step.map(
                    name=sd["name"],
                    items_path=sd["items_path"],
                    iterator_workflow=sd.get("iterator_workflow", ""),
                    max_concurrency=sd.get("max_concurrency", 4),
                )
                step.depends_on = depends_on
                steps.append(step)
            else:
                raise ValueError(f"Unknown step type: {step_type}")

        # Parse execution policy
        policy_data = data.get("execution_policy", {})
        execution_policy = WorkflowExecutionPolicy(
            mode=ExecutionMode(policy_data.get("mode", "sequential")),
            max_concurrency=policy_data.get("max_concurrency", 4),
            timeout_seconds=policy_data.get("timeout_seconds"),
            on_failure=FailurePolicy(policy_data.get("on_failure", "stop")),
        )

        return cls(
            name=data["name"],
            steps=steps,
            domain=data.get("domain", ""),
            description=data.get("description", ""),
            version=data.get("version", 1),
            defaults=data.get("defaults", {}),
            tags=data.get("tags", []),
            execution_policy=execution_policy,
        )

    # =========================================================================
    # YAML helpers
    # =========================================================================

    def to_yaml(self) -> str:
        """Serialize this workflow to a YAML string.

        Produces a ``WorkflowSpec``-compatible document with
        ``apiVersion: spine.io/v1`` and ``kind: Workflow``.
        """
        import yaml

        doc: dict[str, Any] = {
            "apiVersion": "spine.io/v1",
            "kind": "Workflow",
            "metadata": {"name": self.name},
        }
        if self.domain:
            doc["metadata"]["domain"] = self.domain
        if self.version != 1:
            doc["metadata"]["version"] = self.version
        if self.description:
            doc["metadata"]["description"] = self.description
        if self.tags:
            doc["metadata"]["tags"] = list(self.tags)

        spec: dict[str, Any] = {}
        if self.defaults:
            spec["defaults"] = dict(self.defaults)

        spec["steps"] = [s.to_dict() for s in self.steps]

        ep = self.execution_policy
        if ep.mode != ExecutionMode.SEQUENTIAL or ep.max_concurrency != 4 or ep.timeout_seconds or ep.on_failure != FailurePolicy.STOP:
            policy: dict[str, Any] = {"execution": ep.mode.value}
            if ep.max_concurrency != 4:
                policy["max_concurrency"] = ep.max_concurrency
            if ep.timeout_seconds:
                policy["timeout_seconds"] = ep.timeout_seconds
            if ep.on_failure != FailurePolicy.STOP:
                policy["on_failure"] = ep.on_failure.value
            spec["policy"] = policy

        doc["spec"] = spec
        return yaml.dump(doc, default_flow_style=False, sort_keys=False)

    def __repr__(self) -> str:
        return f"Workflow({self.name!r}, steps={len(self.steps)}, tier={self.required_tier()})"
