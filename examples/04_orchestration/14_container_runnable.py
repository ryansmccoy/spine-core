#!/usr/bin/env python3
"""ContainerRunnable — bridging orchestration workflows with container execution.

Demonstrates how ``ContainerRunnable`` connects the workflow orchestration
layer with the Job Engine, allowing operation steps to run inside isolated
containers rather than in-process.

Demonstrates:
    1. ``ContainerRunnable`` creation with engine reference
    2. Spec building from operation names + params
    3. Image resolution via custom resolvers
    4. Workflow execution through container delegation
    5. Integration with ``WorkflowRunner`` via the ``Runnable`` protocol
    6. Timeout and error handling during polling

Architecture::

    WorkflowRunner
        │  (calls submit_operation_sync)
        ▼
    ContainerRunnable   ◄── implements Runnable protocol
        │  (builds ContainerJobSpec, submits, polls)
        ▼
    JobEngine
        │  (routes to adapter)
        ▼
    RuntimeAdapter      ◄── LocalProcess / Docker / K8s

Key Concepts:
    - **Runnable protocol**: Single method ``submit_operation_sync()`` that
      ``WorkflowRunner`` calls for each operation step.
    - **Spec building**: Converts operation name + params into a full
      ``ContainerJobSpec`` with image, command, env, labels.
    - **Image resolver**: Callable ``(operation_name) → image`` for
      per-operation container images.
    - **Polling loop**: Calls ``engine.status()`` until terminal state
      or timeout, then converts to ``OperationRunResult``.

See Also:
    - ``15_runnable_protocol.py``   — basic Runnable usage
    - ``11_workflow_serialization.py`` — serializing workflows
    - :mod:`spine.orchestration.container_runnable`

Run:
    python examples/04_orchestration/14_container_runnable.py

Expected Output:
    Five sections: spec building, image resolution, command templates,
    error handling, and workflow integration demo.
"""

from __future__ import annotations

from spine.orchestration.container_runnable import (
    ContainerRunnable,
    _DEFAULT_IMAGE,
    _DEFAULT_POLL_INTERVAL,
    _DEFAULT_TIMEOUT,
)
from spine.orchestration import Workflow, Step, StepType
from spine.execution.runtimes._types import ContainerJobSpec
from spine.execution.runnable import OperationRunResult


def main() -> None:
    """Run all ContainerRunnable demonstrations."""

    print("=" * 72)
    print("SECTION 1: ContainerRunnable Basics")
    print("=" * 72)

    # ContainerRunnable wraps a JobEngine and implements Runnable.
    # Since we don't have a real engine here, we'll demonstrate the
    # spec-building logic which is the core translation layer.

    print(f"\nDefault image:         {_DEFAULT_IMAGE}")
    print(f"Default poll interval: {_DEFAULT_POLL_INTERVAL}s")
    print(f"Default timeout:       {_DEFAULT_TIMEOUT}s")

    # The Runnable protocol requires submit_operation_sync():
    import inspect
    from spine.execution.runnable import Runnable

    assert hasattr(Runnable, "submit_operation_sync")
    print(f"\nRunnable protocol method: submit_operation_sync()")
    print("  Args: operation_name, params, *, parent_run_id, correlation_id")
    print("  Returns: OperationRunResult")

    # Verify ContainerRunnable satisfies the protocol
    print(f"\nContainerRunnable has submit_operation_sync: "
          f"{hasattr(ContainerRunnable, 'submit_operation_sync')}")

    # ─────────────────────────────────────────────────────────────────
    print("\n" + "=" * 72)
    print("SECTION 2: Spec Building — Operation to Container Translation")
    print("=" * 72)

    # The _build_spec method translates operation parameters into
    # a ContainerJobSpec. Let's simulate this manually.

    operation_name = "finra.daily_ingest"
    params = {"date": "2026-01-15", "source": "finra", "batch_size": "1000"}

    # Parameter → env var conversion: SPINE_PARAM_{KEY_UPPER}
    env: dict[str, str] = {}
    for k, v in params.items():
        env[f"SPINE_PARAM_{k.upper()}"] = str(v)
    env["SPINE_PARENT_RUN_ID"] = "run-abc-123"

    spec = ContainerJobSpec(
        name=f"operation-{operation_name.replace('.', '-')}",
        image=_DEFAULT_IMAGE,
        command=["spine-cli", "run", operation_name],
        env=env,
        labels={
            "spine.operation": operation_name,
            "spine.parent_run_id": "run-abc-123",
        },
    )

    print(f"\nOperation:    {operation_name}")
    print(f"Image:       {spec.image}")
    print(f"Command:     {spec.command}")
    print(f"Env vars:    {len(spec.env)} entries")
    for k, v in sorted(spec.env.items()):
        print(f"  {k} = {v}")
    print(f"Labels:      {spec.labels}")
    print(f"Container name: {spec.name}")

    # ─────────────────────────────────────────────────────────────────
    print("\n" + "=" * 72)
    print("SECTION 3: Custom Image Resolver")
    print("=" * 72)

    # Image resolvers let you map operation names to container images
    IMAGE_MAP = {
        "finra.daily_ingest": "spine-finra:v2.1",
        "sec.filing_fetch": "spine-sec:latest",
        "edgar.parse_10k": "spine-edgar:v1.0",
    }

    def resolve_image(operation_name: str) -> str:
        """Map operation names to specific container images."""
        return IMAGE_MAP.get(operation_name, _DEFAULT_IMAGE)

    print("\nImage resolution map:")
    for operation, image in IMAGE_MAP.items():
        resolved = resolve_image(operation)
        print(f"  {operation:30s} → {resolved}")

    # Unknown operations get the default
    unknown = resolve_image("unknown.operation")
    print(f"  {'unknown.operation':30s} → {unknown} (default)")

    # ─────────────────────────────────────────────────────────────────
    print("\n" + "=" * 72)
    print("SECTION 4: Command Template Customization")
    print("=" * 72)

    # The default command is ["spine-cli", "run", "{operation}"]
    # but you can provide a custom template with {operation} placeholder

    custom_template = ["python", "-m", "spine.cli", "operation", "execute", "{operation}"]
    expanded = [part.replace("{operation}", "my.operation") for part in custom_template]
    print(f"\nCustom template: {custom_template}")
    print(f"Expanded:        {expanded}")

    # Docker-specific template
    docker_template = ["/app/run.sh", "--operation={operation}", "--mode=production"]
    expanded_docker = [part.replace("{operation}", "sec.10k") for part in docker_template]
    print(f"\nDocker template: {docker_template}")
    print(f"Expanded:        {expanded_docker}")

    # ─────────────────────────────────────────────────────────────────
    print("\n" + "=" * 72)
    print("SECTION 5: OperationRunResult — What Comes Back")
    print("=" * 72)

    from datetime import datetime, UTC, timedelta

    # Successful result
    started = datetime.now(UTC)
    completed = started + timedelta(seconds=45)
    success_result = OperationRunResult(
        status="completed",
        error=None,
        metrics={
            "execution_id": "exec-12345",
            "exit_code": 0,
            "runtime_state": "succeeded",
        },
        run_id="exec-12345",
        started_at=started,
        completed_at=completed,
    )
    print(f"\nSuccess result:")
    print(f"  status:    {success_result.status}")
    print(f"  succeeded: {success_result.succeeded}")
    print(f"  duration:  {success_result.duration_seconds:.1f}s")
    print(f"  exit_code: {success_result.metrics.get('exit_code')}")

    # Failed result
    fail_result = OperationRunResult(
        status="failed",
        error="Container exited with code 1: OOM killed",
        metrics={"execution_id": "exec-99999", "exit_code": 137},
        run_id="exec-99999",
        started_at=started,
        completed_at=started + timedelta(seconds=5),
    )
    print(f"\nFailed result:")
    print(f"  status:    {fail_result.status}")
    print(f"  succeeded: {fail_result.succeeded}")
    print(f"  error:     {fail_result.error}")
    print(f"  exit_code: {fail_result.metrics.get('exit_code')}")

    # Timeout result
    timeout_result = OperationRunResult(
        status="failed",
        error="Timed out after 600s",
        metrics={"execution_id": "exec-88888"},
        run_id="exec-88888",
        started_at=started,
        completed_at=started + timedelta(seconds=600),
    )
    print(f"\nTimeout result:")
    print(f"  status:    {timeout_result.status}")
    print(f"  error:     {timeout_result.error}")

    # ─────────────────────────────────────────────────────────────────
    print("\n" + "=" * 72)
    print("SECTION 6: Workflow Integration Pattern")
    print("=" * 72)

    # Build a workflow that would use ContainerRunnable
    wf = Workflow(
        name="etl.containerized",
        steps=[
            Step.operation("fetch", "data.fetch_source"),
            Step.operation("normalize", "data.normalize", depends_on=("fetch",)),
            Step.operation("validate", "data.validate", depends_on=("normalize",)),
            Step.operation("store", "data.store_results", depends_on=("validate",)),
        ],
        domain="data",
        description="4-step ETL running each step in a container",
        tags=["etl", "containerized"],
    )

    print(f"\nWorkflow: {wf.name}")
    print(f"Steps:    {len(wf.steps)}")
    print(f"Operation names used:")
    for name in wf.operation_names():
        image = resolve_image(name)
        print(f"  {name:30s} → container: {image}")

    print("""
Integration code (not run here — requires live engine):

    from spine.execution.runtimes.engine import JobEngine
    from spine.execution.runtimes.router import RuntimeAdapterRouter
    from spine.orchestration.container_runnable import ContainerRunnable
    from spine.orchestration import WorkflowRunner

    # Set up engine
    router = RuntimeAdapterRouter()
    router.register("docker", docker_adapter)
    engine = JobEngine(router=router)

    # Bridge to orchestration
    runnable = ContainerRunnable(
        engine=engine,
        image_resolver=resolve_image,
        timeout=300,
    )

    # Run the workflow — each operation step runs in a container!
    runner = WorkflowRunner(runnable=runnable)
    result = runner.execute(wf, params={"date": "2026-01-15"})
""")

    print("=" * 72)
    print("All ContainerRunnable demonstrations complete!")
    print("=" * 72)


if __name__ == "__main__":
    main()
