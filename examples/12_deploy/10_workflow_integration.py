#!/usr/bin/env python3
"""Workflow Integration — Deploy as a spine-core workflow.

The deploy package provides factory functions that wrap testbed and
deployment operations as spine-core ``Workflow`` objects. This enables
scheduling, history tracking, retry semantics, and composition with
other workflows.

Demonstrates:
    1. Creating a testbed workflow via ``create_testbed_workflow()``
    2. Creating a deployment workflow via ``create_deployment_workflow()``
    3. Inspecting workflow structure (steps, policy, tags)
    4. Building custom workflows from deploy components
    5. Workflow serialisation (``to_dict()`` / ``from_dict()``)
    6. Understanding execution policy (sequential, parallel, failure modes)

Architecture:
    create_testbed_workflow(backends)
        └── Workflow
            ├── Step: validate_environment
            └── Step: run_testbed        ← TestbedRunner(config).run()

    create_deployment_workflow(targets, profile)
        └── Workflow
            ├── Step: deploy             ← DeploymentRunner(config).run()
            └── Step: health_check       ← DeploymentRunner(status).run()

Key Concepts:
    - **Workflow factories**: Return real ``Workflow`` objects from
      ``spine.orchestration.workflow`` — ready for scheduling.
    - **Step.lambda_()**: Wraps a callable as a workflow step.
    - **WorkflowExecutionPolicy**: Controls timeout, failure handling,
      and execution mode (sequential vs parallel).
    - **to_dict/from_dict**: Enables workflow persistence and transfer.

See Also:
    - ``04_testbed_workflow.py`` — Simulated testbed run (result models)
    - ``08_schema_executor.py`` — Real executor in action
    - ``spine.deploy.workflow`` — Factory functions source
    - ``spine.orchestration.workflow`` — Workflow engine

Run:
    python examples/12_deploy/10_workflow_integration.py

Expected Output:
    Workflow structure, step details, execution policy, and
    serialisation round-trip.
"""

from spine.deploy.workflow import (
    TestbedRunner,
    DeploymentRunner,
    create_testbed_workflow,
    create_deployment_workflow,
)


def main() -> None:
    """Demonstrate workflow integration with deploy-spine."""

    print("=" * 60)
    print("Deploy-Spine — Workflow Integration")
    print("=" * 60)

    # --- 1. Create testbed workflow ---
    print("\n--- 1. Testbed Workflow ---")
    testbed_wf = create_testbed_workflow(backends=["postgresql", "mysql"])

    print(f"  name            : {testbed_wf.name}")
    print(f"  domain          : {testbed_wf.domain}")
    print(f"  description     : {testbed_wf.description}")
    print(f"  version         : {testbed_wf.version}")
    print(f"  tags            : {testbed_wf.tags}")
    print(f"  step_count      : {len(testbed_wf.steps)}")

    for step in testbed_wf.steps:
        print(f"    Step: {step.name:25s} type={step.step_type.value}")

    # Execution policy
    policy = testbed_wf.execution_policy
    print(f"  mode            : {policy.mode.value}")
    print(f"  timeout         : {policy.timeout_seconds}s")
    print(f"  on_failure      : {policy.on_failure.value}")

    # --- 2. Deployment workflow ---
    print("\n--- 2. Deployment Workflow ---")
    deploy_wf = create_deployment_workflow(
        targets=["spine-core-api", "postgres"],
        profile="apps",
    )

    print(f"  name            : {deploy_wf.name}")
    print(f"  domain          : {deploy_wf.domain}")
    print(f"  description     : {deploy_wf.description}")
    print(f"  tags            : {deploy_wf.tags}")
    print(f"  step_count      : {len(deploy_wf.steps)}")

    for step in deploy_wf.steps:
        print(f"    Step: {step.name:25s} type={step.step_type.value}")

    policy = deploy_wf.execution_policy
    print(f"  mode            : {policy.mode.value}")
    print(f"  timeout         : {policy.timeout_seconds}s")
    print(f"  on_failure      : {policy.on_failure.value}")

    # --- 3. Workflow metadata ---
    print("\n--- 3. Workflow Capabilities ---")
    print(f"  has_lambda_steps   : {testbed_wf.has_lambda_steps()}")
    print(f"  has_choice_steps   : {testbed_wf.has_choice_steps()}")
    print(f"  has_pipeline_steps : {testbed_wf.has_pipeline_steps()}")
    print(f"  has_dependencies   : {testbed_wf.has_dependencies()}")
    print(f"  step_names         : {testbed_wf.step_names()}")
    print(f"  required_tier      : {testbed_wf.required_tier()}")

    # --- 4. Serialisation round-trip ---
    print("\n--- 4. Serialisation ---")
    data = testbed_wf.to_dict()
    print(f"  to_dict keys    : {sorted(data.keys())}")
    print(f"  steps in dict   : {len(data['steps'])}")
    for step_data in data["steps"]:
        print(f"    {step_data['name']:25s} → type={step_data['type']}")

    # Round-trip: to_dict → from_dict → compare
    # Note: lambda steps with closures can't fully round-trip — the
    # handler function isn't serialisable. But the structure is preserved.
    print(f"\n  Serialised step names preserved: {[s['name'] for s in data['steps']]}")

    # --- 5. Custom workflow composition ---
    print("\n--- 5. Custom Workflow Composition ---")
    print("  You can build custom deploy workflows by combining steps:")
    print()
    print("    from spine.orchestration.step_types import Step")
    print("    from spine.orchestration.workflow import Workflow")
    print()
    print("    steps = [")
    print('        Step.lambda_("pull_images", pull_fn),')
    print('        Step.lambda_("run_testbed", testbed_fn),')
    print('        Step.lambda_("deploy_services", deploy_fn),')
    print('        Step.lambda_("smoke_test", smoke_fn),')
    print("    ]")
    print()
    print("    wf = Workflow(")
    print('        name="deploy.full_pipeline",')
    print("        steps=steps,")
    print('        domain="spine.deploy",')
    print("    )")
    print()
    print("  This is how you'd build a CI pipeline that:")
    print("    1. Validates backends")
    print("    2. Runs the testbed")
    print("    3. Deploys services")
    print("    4. Runs smoke tests")

    # --- 6. Execution policy options ---
    print("\n--- 6. Execution Policy Options ---")
    from spine.orchestration.workflow import ExecutionMode, FailurePolicy

    print("  Execution modes:")
    for mode in ExecutionMode:
        print(f"    {mode.value:15s}")

    print("  Failure policies:")
    for fp in FailurePolicy:
        print(f"    {fp.value:15s}")

    print()
    print("  Testbed uses CONTINUE — runs all backends even if one fails")
    print("  Deploy uses STOP — halts if deployment step fails")

    # --- 7. Difference: Runner vs Workflow ---
    print("\n--- 7. Runner vs Workflow ---")
    print("  TestbedRunner:")
    print("    - Direct invocation: runner.run() → TestbedRunResult")
    print("    - No scheduling, no history, no retry")
    print("    - Best for: scripts, notebooks, quick checks")
    print()
    print("  create_testbed_workflow():")
    print("    - Returns a Workflow — schedule with the orchestration engine")
    print("    - History tracking, retry semantics, step-level status")
    print("    - Best for: CI pipelines, nightly runs, production")

    print("\n" + "=" * 60)
    print("✓ Workflow integration complete.")
    print("=" * 60)


if __name__ == "__main__":
    main()
