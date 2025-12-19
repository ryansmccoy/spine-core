#!/usr/bin/env python3
"""Workflow Registry & YAML Specs — discovery, lookup, and declarative definitions.

Demonstrates the spine-core workflow registry and YAML specification
system for managing collections of reusable workflows.  The registry
enables runtime discovery and domain-based filtering, while YAML specs
allow workflows to be defined declaratively and version-controlled.

Demonstrates:
    1. ``register_workflow()`` — direct and decorator-based registration
    2. ``list_workflows()`` — enumeration with domain filtering
    3. ``get_workflow()`` — lookup by name
    4. ``workflow_exists()`` — existence check
    5. ``get_workflow_registry_stats()`` — registry health
    6. ``WorkflowSpec.from_yaml()`` — parse YAML into validated spec
    7. ``to_workflow()`` — convert spec to executable Workflow
    8. ``validate_yaml_workflow()`` — one-step parse + build
    9. ``clear_workflow_registry()`` — teardown for testing
    10. Error handling — ``WorkflowNotFoundError``, YAML validation

Architecture:
    The registry is an in-memory dictionary keyed by workflow name.
    Workflows are registered eagerly via ``register_workflow()`` and
    looked up lazily via ``get_workflow()``.  Domain filtering lets
    teams partition workflows by subsystem (e.g. ``ingest``, ``sec``).

    The YAML spec system uses Pydantic v2 models for strict validation::

        WorkflowSpec   ← root (apiVersion, kind, metadata, spec)
        ├── WorkflowMetadataSpec  (name, domain, version, description, tags)
        └── WorkflowSpecSection   (steps, defaults, policy)
            ├── WorkflowStepSpec[]  (name, pipeline, depends_on, params)
            └── WorkflowPolicySpec  (execution, max_concurrency, failure)

Key Concepts:
    - **Registry**: Global mutable store; ``clear_workflow_registry()``
      resets it for test isolation.
    - **Decorator pattern**: ``@register_workflow`` on a factory function
      that returns a ``Workflow``.
    - **YAML specs**: Only ``pipeline`` steps are supported in YAML (lambda
      handlers cannot be serialized).
    - **Domain filtering**: Each workflow can declare a domain for
      team-based or subsystem partitioning.

See Also:
    - ``01_workflow_basics.py``  — lambda-step workflow
    - ``07_parallel_dag.py``     — parallel DAG with depends_on
    - :mod:`spine.orchestration.workflow_registry` — registry source
    - :mod:`spine.orchestration.workflow_yaml`     — YAML spec source

Run:
    python examples/04_orchestration/10_workflow_registry_yaml.py

Expected Output:
    Five sections: direct registration, decorator registration,
    domain filtering, YAML parsing, and error handling — each with
    assertion checks.
"""

from __future__ import annotations

from typing import Any

from spine.orchestration import (
    ExecutionMode,
    FailurePolicy,
    Step,
    StepResult,
    Workflow,
    WorkflowContext,
    WorkflowExecutionPolicy,
    WorkflowStatus,
)
from spine.orchestration.workflow_registry import (
    WorkflowNotFoundError,
    clear_workflow_registry,
    get_workflow,
    get_workflow_registry_stats,
    list_workflows,
    register_workflow,
    workflow_exists,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _noop_handler(ctx: WorkflowContext, config: dict[str, Any]) -> StepResult:
    """No-op lambda step handler."""
    return StepResult.ok(output={"handler": "noop"})


def _build_pipeline_workflow(
    name: str,
    *,
    domain: str | None = None,
    n_steps: int = 3,
    description: str | None = None,
) -> Workflow:
    """Build a simple pipeline-step workflow for registration tests."""
    steps = [
        Step.pipeline(
            name=f"step_{i}",
            pipeline_name=f"{name}.pipeline_{i}",
        )
        for i in range(n_steps)
    ]
    return Workflow(
        name=name,
        steps=steps,
        domain=domain,
        description=description or f"Workflow {name}",
    )


def _build_lambda_workflow(
    name: str,
    *,
    domain: str | None = None,
    n_steps: int = 2,
) -> Workflow:
    """Build a simple lambda-step workflow for registration tests."""
    steps = [
        Step.lambda_(f"step_{i}", _noop_handler)
        for i in range(n_steps)
    ]
    return Workflow(name=name, steps=steps, domain=domain)


# ---------------------------------------------------------------------------
# Section 1 — Direct registration
# ---------------------------------------------------------------------------

def demo_direct_registration() -> None:
    """Register workflows directly and look them up."""
    print("\n--- Section 1: Direct Registration ---\n")

    clear_workflow_registry()

    # Register three workflows in two domains
    wf_ingest = _build_pipeline_workflow(
        "ingest.daily", domain="ingest",
        description="Daily data ingest pipeline",
    )
    wf_enrich = _build_pipeline_workflow(
        "ingest.enrich", domain="ingest",
        description="Entity enrichment pipeline",
    )
    wf_sec = _build_lambda_workflow(
        "sec.fetch_index", domain="sec",
    )

    register_workflow(wf_ingest)
    register_workflow(wf_enrich)
    register_workflow(wf_sec)

    # Verify existence
    assert workflow_exists("ingest.daily"), "ingest.daily should exist"
    assert workflow_exists("ingest.enrich"), "ingest.enrich should exist"
    assert workflow_exists("sec.fetch_index"), "sec.fetch_index should exist"
    assert not workflow_exists("nonexistent.workflow"), "should not exist"
    print("  [OK] 3 workflows registered")

    # Lookup
    fetched = get_workflow("ingest.daily")
    assert fetched.name == "ingest.daily"
    assert fetched.domain == "ingest"
    assert len(fetched.steps) == 3
    print(f"  [OK] get_workflow('ingest.daily') → {fetched.name} "
          f"({len(fetched.steps)} steps, domain={fetched.domain})")

    # List all
    all_names = list_workflows()
    assert len(all_names) == 3
    print(f"  [OK] list_workflows() → {all_names}")

    # Registry stats
    stats = get_workflow_registry_stats()
    assert stats["total_workflows"] == 3
    assert stats["workflows_by_domain"]["ingest"] == 2
    assert stats["workflows_by_domain"]["sec"] == 1
    print(f"  [OK] Registry stats: {stats}")


# ---------------------------------------------------------------------------
# Section 2 — Decorator-based registration
# ---------------------------------------------------------------------------

def demo_decorator_registration() -> None:
    """Register workflows via the decorator pattern."""
    print("\n--- Section 2: Decorator Registration ---\n")

    clear_workflow_registry()

    # Using @register_workflow as a decorator on a factory function
    @register_workflow
    def build_sec_etl():
        return Workflow(
            name="sec.etl_pipeline",
            domain="sec",
            description="SEC filing ETL workflow",
            steps=[
                Step.pipeline("fetch", "sec.fetch_filing"),
                Step.pipeline("parse", "sec.parse_xbrl", depends_on=("fetch",)),
                Step.pipeline("store", "sec.store_results", depends_on=("parse",)),
            ],
            execution_policy=WorkflowExecutionPolicy(
                mode=ExecutionMode.SEQUENTIAL,
                on_failure=FailurePolicy.STOP,
            ),
        )

    # The decorator should have returned the Workflow and registered it
    assert isinstance(build_sec_etl, Workflow), "Decorator should return Workflow"
    assert workflow_exists("sec.etl_pipeline"), "Should be registered"
    print(f"  [OK] @register_workflow → {build_sec_etl.name}")

    # Register another via decorator
    @register_workflow
    def build_quality_check():
        return Workflow(
            name="sec.quality_check",
            domain="sec",
            steps=[
                Step.lambda_("validate", _noop_handler),
                Step.lambda_("score", _noop_handler),
            ],
        )

    assert workflow_exists("sec.quality_check")
    all_names = list_workflows()
    assert len(all_names) == 2
    print(f"  [OK] 2 workflows via decorators: {all_names}")


# ---------------------------------------------------------------------------
# Section 3 — Domain filtering
# ---------------------------------------------------------------------------

def demo_domain_filtering() -> None:
    """Filter workflows by domain."""
    print("\n--- Section 3: Domain Filtering ---\n")

    clear_workflow_registry()

    # Register workflows in multiple domains
    domains_map = {
        "ingest": ["ingest.rss", "ingest.api", "ingest.scrape"],
        "sec": ["sec.fetch", "sec.parse"],
        "analytics": ["analytics.score"],
    }

    for domain, names in domains_map.items():
        for name in names:
            register_workflow(_build_pipeline_workflow(
                name, domain=domain, n_steps=2,
            ))

    # No filter — all 6
    all_names = list_workflows()
    assert len(all_names) == 6
    print(f"  [OK] All workflows: {all_names}")

    # Filter by domain
    ingest = list_workflows(domain="ingest")
    assert ingest == ["ingest.api", "ingest.rss", "ingest.scrape"]
    print(f"  [OK] domain='ingest': {ingest}")

    sec = list_workflows(domain="sec")
    assert sec == ["sec.fetch", "sec.parse"]
    print(f"  [OK] domain='sec':    {sec}")

    analytics = list_workflows(domain="analytics")
    assert analytics == ["analytics.score"]
    print(f"  [OK] domain='analytics': {analytics}")

    # Non-existent domain returns empty
    empty = list_workflows(domain="nonexistent")
    assert empty == []
    print(f"  [OK] domain='nonexistent': {empty}")

    # Stats show domain distribution
    stats = get_workflow_registry_stats()
    print(f"  [OK] Stats: {stats['workflows_by_domain']}")


# ---------------------------------------------------------------------------
# Section 4 — YAML workflow specs
# ---------------------------------------------------------------------------

SEC_ETL_YAML = """\
apiVersion: spine.io/v1
kind: Workflow
metadata:
  name: sec.yaml_etl
  domain: sec
  version: 2
  description: SEC filing ETL defined in YAML
  tags:
    - sec
    - etl
    - production
spec:
  defaults:
    timeout: 300
    retries: 2
  steps:
    - name: fetch_index
      pipeline: sec.fetch_recent_filings
      params:
        form_type: "10-K"
        limit: 50
    - name: download
      pipeline: sec.download_filing
      depends_on: [fetch_index]
    - name: extract_text
      pipeline: sec.extract_text
      depends_on: [download]
    - name: extract_xbrl
      pipeline: sec.extract_xbrl_facts
      depends_on: [download]
    - name: enrich
      pipeline: sec.entity_enrichment
      depends_on: [extract_text, extract_xbrl]
    - name: store
      pipeline: sec.store_results
      depends_on: [enrich]
  policy:
    execution: parallel
    max_concurrency: 4
    on_failure: stop
"""

MINIMAL_YAML = """\
apiVersion: spine.io/v1
kind: Workflow
metadata:
  name: minimal.pipeline
spec:
  steps:
    - name: only_step
      pipeline: do.something
"""


def demo_yaml_specs() -> None:
    """Parse YAML workflow specs and convert to executable Workflows."""
    print("\n--- Section 4: YAML Workflow Specs ---\n")

    try:
        import yaml  # noqa: F401
    except ImportError:
        print("  [SKIP] PyYAML not installed — skipping YAML demos")
        print("         Install with: pip install pyyaml")
        return

    from spine.orchestration.workflow_yaml import WorkflowSpec, validate_yaml_workflow

    clear_workflow_registry()

    # --- Parse full YAML spec ---
    spec = WorkflowSpec.from_yaml(SEC_ETL_YAML)

    print(f"  Parsed spec: {spec.metadata.name}")
    print(f"    domain  : {spec.metadata.domain}")
    print(f"    version : {spec.metadata.version}")
    print(f"    tags    : {spec.metadata.tags}")
    print(f"    steps   : {len(spec.spec.steps)}")
    print(f"    policy  : {spec.spec.policy.execution}, "
          f"concurrency={spec.spec.policy.max_concurrency}")
    print(f"    defaults: {spec.spec.defaults}")

    assert spec.metadata.name == "sec.yaml_etl"
    assert spec.metadata.domain == "sec"
    assert spec.metadata.version == 2
    assert len(spec.metadata.tags) == 3
    assert len(spec.spec.steps) == 6
    print("  [OK] WorkflowSpec parsed and validated")

    # --- Convert to Workflow ---
    workflow = spec.to_workflow()

    assert workflow.name == "sec.yaml_etl"
    assert workflow.domain == "sec"
    assert len(workflow.steps) == 6
    assert workflow.execution_policy.mode == ExecutionMode.PARALLEL
    assert workflow.execution_policy.max_concurrency == 4
    assert workflow.execution_policy.on_failure == FailurePolicy.STOP
    print(f"  [OK] to_workflow() → {workflow.name}, "
          f"{len(workflow.steps)} steps, mode={workflow.execution_policy.mode}")

    # Verify dependency graph (maps step → dependents, not dependencies)
    dep_graph = workflow.dependency_graph()
    assert "fetch_index" in dep_graph
    assert "download" in dep_graph
    # extract_text and extract_xbrl should list "enrich" as a dependent
    assert "enrich" in dep_graph.get("extract_text", [])
    assert "enrich" in dep_graph.get("extract_xbrl", [])
    print(f"  [OK] Dependency graph verified: {dep_graph}")

    # Verify step config from YAML (pipeline params stored in step.config)
    fetch_step = workflow.steps[0]
    assert fetch_step.name == "fetch_index"
    assert fetch_step.config == {"form_type": "10-K", "limit": 50}
    print(f"  [OK] Step config preserved: {fetch_step.config}")

    # --- Register the YAML-defined workflow ---
    register_workflow(workflow)
    assert workflow_exists("sec.yaml_etl")
    print("  [OK] YAML workflow registered in global registry")

    # --- Minimal YAML ---
    minimal = WorkflowSpec.from_yaml(MINIMAL_YAML)
    min_wf = minimal.to_workflow()
    assert min_wf.name == "minimal.pipeline"
    assert len(min_wf.steps) == 1
    assert min_wf.domain == ""  # defaults to empty string when omitted
    print(f"  [OK] Minimal YAML → {min_wf.name} ({len(min_wf.steps)} step)")

    # --- validate_yaml_workflow() one-liner ---
    import yaml as pyyaml
    data = pyyaml.safe_load(SEC_ETL_YAML)
    wf2 = validate_yaml_workflow(data)
    assert wf2.name == "sec.yaml_etl"
    assert len(wf2.steps) == 6
    print(f"  [OK] validate_yaml_workflow() → {wf2.name}")


# ---------------------------------------------------------------------------
# Section 5 — Error handling
# ---------------------------------------------------------------------------

def demo_error_handling() -> None:
    """Demonstrate error cases."""
    print("\n--- Section 5: Error Handling ---\n")

    clear_workflow_registry()

    # --- Duplicate registration ---
    wf = _build_pipeline_workflow("dup.test", domain="test")
    register_workflow(wf)

    try:
        register_workflow(_build_pipeline_workflow("dup.test", domain="test"))
        assert False, "Should have raised ValueError"
    except ValueError as e:
        print(f"  [OK] Duplicate registration: {e}")

    # --- Lookup nonexistent ---
    try:
        get_workflow("does.not.exist")
        assert False, "Should have raised WorkflowNotFoundError"
    except WorkflowNotFoundError as e:
        print(f"  [OK] Missing workflow: {e}")

    # --- Invalid YAML (if PyYAML available) ---
    try:
        import yaml  # noqa: F401
        from spine.orchestration.workflow_yaml import WorkflowSpec

        # Wrong apiVersion
        try:
            WorkflowSpec.from_yaml("""\
apiVersion: spine.io/v99
kind: Workflow
metadata:
  name: bad
spec:
  steps:
    - name: s1
      pipeline: p1
""")
            assert False, "Should have failed validation"
        except Exception as e:
            print(f"  [OK] Bad apiVersion: {type(e).__name__}")

        # Duplicate step names
        try:
            WorkflowSpec.from_yaml("""\
apiVersion: spine.io/v1
kind: Workflow
metadata:
  name: bad
spec:
  steps:
    - name: s1
      pipeline: p1
    - name: s1
      pipeline: p2
""")
            assert False, "Should have caught duplicate names"
        except Exception as e:
            print(f"  [OK] Duplicate step names: {type(e).__name__}")

        # Circular dependency reference
        try:
            WorkflowSpec.from_yaml("""\
apiVersion: spine.io/v1
kind: Workflow
metadata:
  name: bad
spec:
  steps:
    - name: s1
      pipeline: p1
      depends_on: [s2]
    - name: s2
      pipeline: p2
      depends_on: [s1]
""")
            # Circular deps are valid at the spec level (validated at runtime)
            print("  [OK] Circular depends_on: parsed (detected at runtime)")
        except Exception as e:
            print(f"  [OK] Circular depends_on: {type(e).__name__}")

    except ImportError:
        print("  [SKIP] PyYAML not installed — skipping YAML error tests")

    # --- Register non-Workflow ---
    try:
        register_workflow("not a workflow")  # type: ignore[arg-type]
        assert False, "Should have raised TypeError"
    except TypeError as e:
        print(f"  [OK] Wrong type: {e}")


# ---------------------------------------------------------------------------
# Section 6 — Clear and verify cleanup
# ---------------------------------------------------------------------------

def demo_cleanup() -> None:
    """Verify clean teardown."""
    print("\n--- Section 6: Registry Cleanup ---\n")

    clear_workflow_registry()

    # Register some workflows
    for i in range(5):
        register_workflow(_build_pipeline_workflow(f"cleanup.test_{i}"))

    assert len(list_workflows()) == 5
    print(f"  [OK] Registered 5 workflows")

    stats = get_workflow_registry_stats()
    assert stats["total_workflows"] == 5
    print(f"  [OK] Stats before clear: {stats}")

    # Clear
    clear_workflow_registry()
    assert len(list_workflows()) == 0
    assert not workflow_exists("cleanup.test_0")
    print(f"  [OK] Registry cleared: {list_workflows()}")

    stats = get_workflow_registry_stats()
    assert stats["total_workflows"] == 0
    print(f"  [OK] Stats after clear: {stats}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    """Run all registry and YAML demonstrations."""

    print("=" * 60)
    print("Workflow Registry & YAML Specs")
    print("=" * 60)

    try:
        demo_direct_registration()
        demo_decorator_registration()
        demo_domain_filtering()
        demo_yaml_specs()
        demo_error_handling()
        demo_cleanup()
    finally:
        # Always clean up the global registry
        clear_workflow_registry()

    print("\n" + "=" * 60)
    print("[OK] All registry & YAML demonstrations passed")
    print("=" * 60)


if __name__ == "__main__":
    main()
