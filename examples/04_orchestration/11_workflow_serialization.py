#!/usr/bin/env python3
"""Workflow Serialization — to_dict, from_dict, to_yaml round-trips.

Demonstrates the spine-core workflow serialization system for persisting
and restoring workflows.  This enables workflow definitions to be stored
in databases, sent over APIs, or version-controlled as YAML files.

Demonstrates:
    1. ``Step.to_dict()`` — serialize any step type to dict
    2. ``Workflow.to_dict()`` — serialize complete workflow
    3. ``Workflow.from_dict()`` — deserialize from dict
    4. ``Workflow.to_yaml()`` — export as WorkflowSpec YAML
    5. ``WorkflowSpec.from_workflow()`` — convert runtime Workflow to spec
    6. ``handler_ref`` — serialize named handlers as ``module:qualname``
    7. ``resolve_callable_ref()`` — dynamically import handler refs
    8. Round-trip verification — ensure data survives serialization

Architecture:
    Serialization flows in two directions::

        Runtime                    Serialized
        ──────────────────────────────────────────────
        Workflow.to_dict()    →    dict (JSON-safe)
        Workflow.from_dict()  ←    dict
        Workflow.to_yaml()    →    str (YAML document)
        WorkflowSpec.from_yaml() ← str

    Lambda steps with named handlers serialize their ``handler_ref`` as
    ``"module:qualname"`` for later import.  Inline lambdas serialize
    without a ref — they must be rewired after deserialization.

Key Concepts:
    - **handler_ref**: ``"spine.orchestration:StepResult"`` format for
      importable callables.  Lambdas return ``None`` (not importable).
    - **Round-trip safety**: Pipeline steps round-trip losslessly. Lambda
      and choice steps preserve refs if named handlers are used.
    - **WorkflowSpec envelope**: ``to_yaml()`` wraps in standard YAML
      with ``apiVersion: spine.io/v1`` and ``kind: Workflow``.

See Also:
    - ``10_workflow_registry_yaml.py`` — YAML registry integration
    - ``01_workflow_basics.py``        — workflow basics
    - :mod:`spine.orchestration.workflow` — Workflow.to_dict/from_dict
    - :mod:`spine.orchestration.workflow_yaml` — WorkflowSpec

Run:
    python examples/04_orchestration/11_workflow_serialization.py

Expected Output:
    Six sections: step serialization, workflow serialization, YAML export,
    handler ref resolution, round-trip tests, and JSON storage example.
"""

from __future__ import annotations

import json
import yaml

from spine.orchestration import (
    Workflow,
    Step,
    StepType,
    StepResult,
)
from spine.orchestration.workflow import (
    ExecutionMode,
    FailurePolicy,
    WorkflowExecutionPolicy,
)
from spine.orchestration.workflow_yaml import WorkflowSpec
from spine.orchestration.step_types import _callable_ref, resolve_callable_ref


# =============================================================================
# Named handlers (can be serialized via handler_ref)
# =============================================================================


def validate_record(ctx, config) -> StepResult:
    """Named handler that can be serialized and imported."""
    return StepResult.ok(output={"validated": True})


def route_by_size(ctx) -> bool:
    """Named condition for choice steps."""
    return ctx.get_param("size", 0) > 1000


# =============================================================================
# Section 1: Step Serialization
# =============================================================================

print("=" * 70)
print("SECTION 1: Step.to_dict() — Serialize Individual Steps")
print("=" * 70)

# Pipeline step
pipeline_step = Step.pipeline("fetch_data", "sec.fetch", params={"limit": 100})
pipeline_dict = pipeline_step.to_dict()
print(f"\n1a. Pipeline step as dict:")
print(f"    {json.dumps(pipeline_dict, indent=4)}")
assert pipeline_dict["name"] == "fetch_data"
assert pipeline_dict["type"] == "pipeline"
assert pipeline_dict["pipeline"] == "sec.fetch"
print("    ✓ Pipeline step serialized correctly")

# Lambda step with named handler
lambda_step = Step.lambda_("validate", validate_record)
lambda_dict = lambda_step.to_dict()
print(f"\n1b. Lambda step (named handler) as dict:")
print(f"    {json.dumps(lambda_dict, indent=4)}")
assert lambda_dict["handler_ref"] == f"{__name__}:validate_record"
print(f"    ✓ handler_ref = '{lambda_dict['handler_ref']}'")

# Lambda step with inline lambda (no handler_ref)
inline_step = Step.lambda_("inline", lambda ctx, cfg: StepResult.ok())
inline_dict = inline_step.to_dict()
print(f"\n1c. Lambda step (inline lambda) as dict:")
print(f"    {json.dumps(inline_dict, indent=4)}")
assert "handler_ref" not in inline_dict
print("    ✓ Inline lambdas have no handler_ref (expected)")

# Choice step
choice_step = Step.choice("route", route_by_size, "large_handler", "small_handler")
choice_dict = choice_step.to_dict()
print(f"\n1d. Choice step as dict:")
print(f"    {json.dumps(choice_dict, indent=4)}")
assert choice_dict["condition_ref"] == f"{__name__}:route_by_size"
print("    ✓ Choice step with condition_ref serialized")

# Step with dependencies
dep_step = Step.pipeline("process", "processor", depends_on=["fetch_data", "validate"])
dep_dict = dep_step.to_dict()
print(f"\n1e. Step with depends_on:")
print(f"    {json.dumps(dep_dict, indent=4)}")
assert dep_dict["depends_on"] == ["fetch_data", "validate"]
print("    ✓ Dependencies preserved")


# =============================================================================
# Section 2: Workflow.to_dict() / from_dict()
# =============================================================================

print("\n" + "=" * 70)
print("SECTION 2: Workflow.to_dict() / from_dict() — Full Workflow")
print("=" * 70)

# Create a workflow with metadata and execution policy
workflow = Workflow(
    name="sec.daily_etl",
    domain="sec.filings",
    version=3,
    description="Daily SEC filing ETL workflow",
    steps=[
        Step.pipeline("fetch", "sec.fetch_filings"),
        Step.lambda_("validate", validate_record),
        Step.pipeline("transform", "sec.transform", depends_on=["fetch", "validate"]),
        Step.pipeline("load", "sec.load_warehouse", depends_on=["transform"]),
    ],
    defaults={"environment": "production", "batch_size": 500},
    tags=["production", "daily", "etl"],
    execution_policy=WorkflowExecutionPolicy(
        mode=ExecutionMode.PARALLEL,
        max_concurrency=8,
        timeout_seconds=3600,
        on_failure=FailurePolicy.CONTINUE,
    ),
)

# Serialize to dict
workflow_dict = workflow.to_dict()
print(f"\n2a. Workflow '{workflow.name}' as dict:")
print(f"    Name: {workflow_dict['name']}")
print(f"    Domain: {workflow_dict.get('domain', 'N/A')}")
print(f"    Version: {workflow_dict['version']}")
print(f"    Steps: {len(workflow_dict['steps'])}")
print(f"    Tags: {workflow_dict.get('tags', [])}")
if "execution_policy" in workflow_dict:
    print(f"    Policy: {workflow_dict['execution_policy']}")

# Verify JSON-serializable
json_str = json.dumps(workflow_dict, indent=2)
print(f"\n2b. JSON-serializable? {len(json_str)} bytes")
assert json_str  # No exceptions
print("    ✓ Workflow dict is JSON-serializable")

# Deserialize from dict
restored = Workflow.from_dict(workflow_dict)
print(f"\n2c. Restored workflow:")
print(f"    Name: {restored.name}")
print(f"    Steps: {len(restored.steps)}")
print(f"    Policy mode: {restored.execution_policy.mode.value}")

assert restored.name == workflow.name
assert len(restored.steps) == len(workflow.steps)
assert restored.execution_policy.mode == ExecutionMode.PARALLEL
# The lambda step handler was resolved via handler_ref
assert restored.steps[1].handler is validate_record
print("    ✓ Workflow round-tripped through dict successfully")
print("    ✓ Lambda handler resolved from handler_ref")


# =============================================================================
# Section 3: Workflow.to_yaml()
# =============================================================================

print("\n" + "=" * 70)
print("SECTION 3: Workflow.to_yaml() — YAML Export")
print("=" * 70)

yaml_str = workflow.to_yaml()
print(f"\n3a. Workflow as YAML ({len(yaml_str)} chars):")
print("-" * 50)
# Print first 30 lines
lines = yaml_str.strip().split("\n")
for line in lines[:30]:
    print(f"    {line}")
if len(lines) > 30:
    print(f"    ... ({len(lines) - 30} more lines)")
print("-" * 50)

# Parse back and verify
parsed = yaml.safe_load(yaml_str)
assert parsed["apiVersion"] == "spine.io/v1"
assert parsed["kind"] == "Workflow"
assert parsed["metadata"]["name"] == "sec.daily_etl"
print("\n3b. YAML envelope verified:")
print(f"    apiVersion: {parsed['apiVersion']}")
print(f"    kind: {parsed['kind']}")
print("    ✓ Valid WorkflowSpec YAML format")

# Round-trip through WorkflowSpec
spec = WorkflowSpec.from_yaml(yaml_str)
yaml_restored = spec.to_workflow()
assert yaml_restored.name == workflow.name
assert len(yaml_restored.steps) == 4
print("\n3c. Round-trip via WorkflowSpec.from_yaml() + to_workflow()")
print("    ✓ YAML → WorkflowSpec → Workflow succeeded")


# =============================================================================
# Section 4: WorkflowSpec.from_workflow()
# =============================================================================

print("\n" + "=" * 70)
print("SECTION 4: WorkflowSpec.from_workflow() — Pydantic Model")
print("=" * 70)

spec_from_wf = WorkflowSpec.from_workflow(workflow)
print(f"\n4a. Created WorkflowSpec from runtime Workflow:")
print(f"    Metadata name: {spec_from_wf.metadata.name}")
print(f"    Metadata domain: {spec_from_wf.metadata.domain}")
print(f"    Spec steps: {len(spec_from_wf.spec.steps)}")
print(f"    Policy execution: {spec_from_wf.spec.policy.execution}")

# Convert back to Workflow
wf_from_spec = spec_from_wf.to_workflow()
assert wf_from_spec.name == workflow.name
assert wf_from_spec.domain == workflow.domain
print("\n4b. to_workflow() conversion:")
print("    ✓ WorkflowSpec.from_workflow() + to_workflow() round-trip works")

# Note about lambda steps
print("\n4c. Non-pipeline step handling:")
print(f"    Lambda step '{workflow.steps[1].name}' → type='lambda'")
print(f"    Spec step type: '{spec_from_wf.spec.steps[1].type}'")
print(f"    Spec handler_ref: '{spec_from_wf.spec.steps[1].handler_ref}'")
print("    (All step types now fully supported)")


# =============================================================================
# Section 5: Handler Ref Utilities
# =============================================================================

print("\n" + "=" * 70)
print("SECTION 5: handler_ref Utilities")
print("=" * 70)

# _callable_ref for named function
ref = _callable_ref(validate_record)
print(f"\n5a. _callable_ref(validate_record):")
print(f"    Result: '{ref}'")
assert ref == f"{__name__}:validate_record"
print("    ✓ Named function returns module:qualname")

# _callable_ref for lambda
lambda_ref = _callable_ref(lambda x: x)
print(f"\n5b. _callable_ref(lambda x: x):")
print(f"    Result: {lambda_ref}")
assert lambda_ref is None
print("    ✓ Lambdas return None (not importable)")

# _callable_ref for builtin
builtin_ref = _callable_ref(len)
print(f"\n5c. _callable_ref(len):")
print(f"    Result: {builtin_ref}")
# Built-ins may return a ref like 'builtins:len' depending on Python version
print(f"    ✓ Built-in returns: {builtin_ref or 'None'}")

# resolve_callable_ref
resolved = resolve_callable_ref(f"{__name__}:validate_record")
print(f"\n5d. resolve_callable_ref('{__name__}:validate_record'):")
print(f"    Result: {resolved}")
assert resolved is validate_record
print("    ✓ Resolved to original function")

# resolve from spine module
spine_ref = "spine.orchestration:StepResult"
spine_resolved = resolve_callable_ref(spine_ref)
print(f"\n5e. resolve_callable_ref('{spine_ref}'):")
print(f"    Result: {spine_resolved}")
assert spine_resolved is StepResult
print("    ✓ Cross-module resolution works")


# =============================================================================
# Section 6: Practical Example — JSON Storage
# =============================================================================

print("\n" + "=" * 70)
print("SECTION 6: Practical Example — Store Workflow in JSON")
print("=" * 70)

# Simulate storing workflow in a database or sending via API
workflow_json = json.dumps(workflow.to_dict(), indent=2)
print(f"\n6a. Serialized for storage ({len(workflow_json)} bytes)")

# Simulate loading from storage
loaded_dict = json.loads(workflow_json)
restored_workflow = Workflow.from_dict(loaded_dict)
print(f"\n6b. Restored from JSON:")
print(f"    Name: {restored_workflow.name}")
print(f"    Steps: {[s.name for s in restored_workflow.steps]}")

# Can execute immediately (lambda handlers resolved)
print(f"\n6c. Handler resolution:")
print(f"    Step 'validate' handler: {restored_workflow.steps[1].handler}")
assert restored_workflow.steps[1].handler is validate_record
print("    ✓ Handler dynamically imported from handler_ref")


# =============================================================================
# Summary
# =============================================================================

print("\n" + "=" * 70)
print("SUMMARY: Workflow Serialization Complete")
print("=" * 70)
print("""
Serialization capabilities demonstrated:

  Step Serialization:
    • Step.to_dict() — all step types (pipeline, lambda, choice, wait, map)
    • handler_ref for named callables (lambdas excluded)
    • depends_on preserves DAG edges

  Workflow Serialization:
    • Workflow.to_dict() — JSON-serializable representation
    • Workflow.from_dict() — restores with handler resolution
    • Workflow.to_yaml() — WorkflowSpec YAML envelope
    • Round-trip verified: dict, YAML, Pydantic model

  Handler Resolution:
    • _callable_ref() — extract 'module:qualname' from callable
    • resolve_callable_ref() — dynamic import from ref string
    • Invalid refs create placeholder handlers (graceful degradation)

Use Cases:
    • Store workflows in databases or config management
    • Version control via YAML files
    • API payloads for remote workflow submission
    • Workflow templates with parameterization
""")

print("✓ All serialization examples completed successfully")
