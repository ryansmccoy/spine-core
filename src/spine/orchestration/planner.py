"""
Plan Resolver - Resolves PipelineGroup definitions into executable plans.

This is the core orchestration logic:
1. Validate all pipelines exist in registry
2. Validate dependency graph is a DAG (no cycles)
3. Topological sort steps by dependencies
4. Merge parameters (group.defaults < run_params < step.params)
5. Return ExecutionPlan ready for GroupRunner

Design Principles:
- Pure functions where possible (testable, deterministic)
- No database access (that's for persistence layer)
- No execution (that's for GroupRunner)
- Clear error messages for all failure modes
"""

from collections import defaultdict, deque

import structlog

from spine.core.execution import new_batch_id
from spine.framework.registry import get_pipeline
from spine.orchestration.exceptions import (
    CycleDetectedError,
    DependencyError,
    PlanResolutionError,
    StepNotFoundError,
)
from spine.orchestration.models import (
    ExecutionPlan,
    PipelineGroup,
    PipelineStep,
    PlannedStep,
)

logger = structlog.get_logger()


class PlanResolver:
    """
    Resolves a PipelineGroup into an ExecutionPlan.

    Thread-safe: No mutable state, each resolve() call is independent.

    Example:
        resolver = PlanResolver()
        plan = resolver.resolve(
            group=my_group,
            params={"tier": "NMS_TIER_1", "week_ending": "2026-01-03"},
        )
        # plan.steps is topologically sorted
        # plan.batch_id links all child executions
    """

    def __init__(self, validate_pipelines: bool = True):
        """
        Initialize resolver.

        Args:
            validate_pipelines: If True, verify all pipelines exist in registry.
                               Set to False for testing without pipeline registration.
        """
        self.validate_pipelines = validate_pipelines

    def resolve(
        self,
        group: PipelineGroup,
        params: dict | None = None,
        batch_id: str | None = None,
    ) -> ExecutionPlan:
        """
        Resolve a group definition into an executable plan.

        Args:
            group: The PipelineGroup to resolve
            params: Runtime parameters (merged with defaults and step params)
            batch_id: Optional batch ID (auto-generated if not provided)

        Returns:
            ExecutionPlan with topologically sorted steps

        Raises:
            StepNotFoundError: If a step references an unregistered pipeline
            CycleDetectedError: If dependencies contain a cycle
            DependencyError: If a step depends on an unknown step
            PlanResolutionError: For other resolution errors
        """
        params = params or {}
        batch_id = batch_id or new_batch_id(f"group_{group.name}")

        logger.debug(
            "plan_resolver.start",
            group=group.name,
            step_count=len(group.steps),
            param_keys=list(params.keys()),
        )

        # Step 1: Validate pipelines exist
        if self.validate_pipelines:
            self._validate_pipelines(group.steps)

        # Step 2: Validate dependencies reference existing steps
        self._validate_dependencies(group.steps)

        # Step 3: Validate no cycles in dependency graph
        self._validate_no_cycles(group.steps)

        # Step 4: Topological sort
        sorted_steps = self._topological_sort(group.steps)

        # Step 5: Build planned steps with merged parameters
        planned_steps = []
        for order, step in enumerate(sorted_steps):
            merged_params = self._merge_params(group.defaults, params, step.params)
            planned_steps.append(
                PlannedStep(
                    step_name=step.name,
                    pipeline_name=step.pipeline,
                    params=merged_params,
                    depends_on=step.depends_on,
                    sequence_order=order,
                )
            )

        plan = ExecutionPlan(
            group_name=group.name,
            group_version=group.version,
            batch_id=batch_id,
            steps=planned_steps,
            policy=group.policy,
            params=params,
        )

        logger.info(
            "plan_resolver.resolved",
            group=group.name,
            batch_id=batch_id,
            step_count=len(planned_steps),
            execution_mode=group.policy.mode.value,
        )

        return plan

    def _validate_pipelines(self, steps: list[PipelineStep]) -> None:
        """Validate all pipelines are registered."""
        for step in steps:
            try:
                get_pipeline(step.pipeline)
            except KeyError:
                raise StepNotFoundError(step.name, step.pipeline)

    def _validate_dependencies(self, steps: list[PipelineStep]) -> None:
        """Validate all dependencies reference existing steps."""
        step_names = {s.name for s in steps}

        for step in steps:
            missing = [dep for dep in step.depends_on if dep not in step_names]
            if missing:
                raise DependencyError(step.name, missing)

    def _validate_no_cycles(self, steps: list[PipelineStep]) -> None:
        """
        Validate the dependency graph is a DAG (no cycles).

        Uses depth-first search with three-color marking:
        - WHITE (0): Unvisited
        - GRAY (1): Currently visiting (on current path)
        - BLACK (2): Finished visiting

        If we encounter a GRAY node, we've found a cycle.
        """
        WHITE, GRAY, BLACK = 0, 1, 2

        # Build adjacency list
        graph = {s.name: list(s.depends_on) for s in steps}
        color = {s.name: WHITE for s in steps}
        path = []  # Track current path for cycle reporting

        def dfs(node: str) -> list[str] | None:
            """DFS visit. Returns cycle if found, None otherwise."""
            color[node] = GRAY
            path.append(node)

            for neighbor in graph.get(node, []):
                if color[neighbor] == GRAY:
                    # Found cycle - extract cycle from path
                    cycle_start = path.index(neighbor)
                    cycle = path[cycle_start:] + [neighbor]
                    return cycle
                elif color[neighbor] == WHITE:
                    result = dfs(neighbor)
                    if result:
                        return result

            color[node] = BLACK
            path.pop()
            return None

        for step in steps:
            if color[step.name] == WHITE:
                cycle = dfs(step.name)
                if cycle:
                    raise CycleDetectedError(cycle)

    def _topological_sort(self, steps: list[PipelineStep]) -> list[PipelineStep]:
        """
        Topological sort using Kahn's algorithm (O(n+m) complexity).

        Returns steps in execution order (dependencies first).
        Stable sort: preserves original order for steps with same dependencies.

        Args:
            steps: List of pipeline steps to sort

        Returns:
            Topologically sorted list of steps

        Raises:
            PlanResolutionError: If sort is incomplete (indicates undetected cycle)
        """
        # Build adjacency list and in-degree count
        graph: dict[str, list[str]] = defaultdict(list)
        in_degree: dict[str, int] = {s.name: 0 for s in steps}
        step_map = {s.name: s for s in steps}

        for step in steps:
            for dep in step.depends_on:
                graph[dep].append(step.name)
                in_degree[step.name] += 1

        # Initialize queue with nodes having no dependencies
        # Use deque for O(1) popleft (stable order preserved)
        queue = deque(s.name for s in steps if in_degree[s.name] == 0)
        result = []

        while queue:
            # Take first node (stable order, O(1) with deque)
            node = queue.popleft()
            result.append(step_map[node])

            # Process neighbors
            for neighbor in graph[node]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        # If not all nodes processed, there's a cycle (should be caught earlier)
        if len(result) != len(steps):
            remaining = [s.name for s in steps if s.name not in [r.name for r in result]]
            raise PlanResolutionError(
                f"Topological sort incomplete. Remaining: {remaining}",
                group_name=None,
            )

        return result

    def _merge_params(
        self,
        defaults: dict,
        run_params: dict,
        step_params: dict,
    ) -> dict:
        """
        Merge parameters with precedence: defaults < run_params < step_params.

        This means:
        - Group defaults are the base
        - Runtime params override defaults
        - Step-specific params override everything

        Does NOT do template substitution (that's a Phase 2 feature).
        """
        result = {}
        result.update(defaults)
        result.update(run_params)
        result.update(step_params)
        return result


# =============================================================================
# Utility Functions
# =============================================================================


def validate_group(group: PipelineGroup, validate_pipelines: bool = True) -> list[str]:
    """
    Validate a group definition without resolving it.

    Returns list of error messages (empty if valid).
    Useful for YAML validation before registration.
    """
    errors = []

    # Check step name uniqueness (already done in PipelineGroup.__post_init__)
    step_names = [s.name for s in group.steps]
    if len(step_names) != len(set(step_names)):
        duplicates = [n for n in step_names if step_names.count(n) > 1]
        errors.append(f"Duplicate step names: {set(duplicates)}")

    # Check dependencies reference existing steps
    for step in group.steps:
        missing = [dep for dep in step.depends_on if dep not in step_names]
        if missing:
            errors.append(f"Step '{step.name}' depends on unknown steps: {missing}")

    # Check for cycles
    resolver = PlanResolver(validate_pipelines=False)
    try:
        resolver._validate_no_cycles(group.steps)
    except CycleDetectedError as e:
        errors.append(str(e))

    # Optionally check pipelines exist
    if validate_pipelines:
        for step in group.steps:
            try:
                get_pipeline(step.pipeline)
            except KeyError:
                errors.append(f"Step '{step.name}' references unknown pipeline: {step.pipeline}")

    return errors
