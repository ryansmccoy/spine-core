"""Workflow Executor — bridges dispatcher to orchestration runner.

WHY
───
When a ``WorkSpec(kind="workflow")`` is submitted, the execution
layer needs to hand off to the orchestration layer.  This module
registers a handler that looks up the workflow, creates a
``WorkflowRunner`` **with the dispatcher as its Runnable**, so
pipeline steps inside the workflow also get full ``RunRecord``
tracking.

ARCHITECTURE
────────────
::

    EventDispatcher.submit(workflow_spec("ingest.daily"))
      │
      ▼
    _make_workflow_handler(dispatcher)
      │
      ├── get_workflow(name)           ─ from workflow_registry
      ├── WorkflowRunner(runnable=dispatcher)
      └── runner.execute(workflow, params)
            │
            └── pipeline steps → dispatcher.submit_pipeline_sync()
                 (full RunRecord tracking preserved)

    register_workflow_executor(registry) ─ wire into HandlerRegistry

Related modules:
    dispatcher.py              — the calling dispatcher
    orchestration.workflow_runner — WorkflowRunner
    orchestration.workflow_registry — get_workflow(name)

Registration::

    from spine.execution.workflow_executor import register_workflow_executor
    register_workflow_executor(registry)
"""

from __future__ import annotations

from typing import Any

from spine.core.logging import get_logger

from spine.execution.registry import HandlerRegistry
from spine.execution.runnable import Runnable
from spine.orchestration.workflow import Workflow
from spine.orchestration.workflow_registry import WorkflowNotFoundError, get_workflow
from spine.orchestration.workflow_runner import WorkflowResult, WorkflowRunner, WorkflowStatus

logger = get_logger(__name__)


def _make_workflow_handler(
    runnable: Runnable | None = None,
) -> Any:
    """Create a workflow handler closed over the given ``Runnable``.

    When the returned coroutine is invoked by the executor it creates a
    :class:`WorkflowRunner` that uses *runnable* for pipeline steps,
    ensuring those steps get full ``RunRecord`` tracking.
    """

    async def _handler(params: dict[str, Any]) -> dict[str, Any]:
        """Execute a workflow by name (handler for ``kind='workflow'``)."""
        spec_name = params.pop("__spec_name__", None)
        params.pop("__spec_metadata__", None)

        if not spec_name:
            return {"status": "failed", "error": "No workflow name provided"}

        logger.info("workflow_executor.start", workflow=spec_name)

        try:
            workflow = get_workflow(spec_name)
        except WorkflowNotFoundError:
            logger.error("workflow_executor.not_found", workflow=spec_name)
            return {"status": "failed", "error": f"Workflow '{spec_name}' not found"}

        runner = WorkflowRunner(
            runnable=runnable,
            dry_run=params.pop("__dry_run__", False),
        )
        result: WorkflowResult = runner.execute(workflow, params=params)

        summary: dict[str, Any] = {
            "status": result.status.value,
            "workflow_name": result.workflow_name,
            "run_id": result.run_id,
            "duration_seconds": result.duration_seconds,
            "completed_steps": result.completed_steps,
            "failed_steps": result.failed_steps,
        }

        if result.status != WorkflowStatus.COMPLETED:
            summary["error_step"] = result.error_step
            summary["error"] = result.error

        logger.info(
            "workflow_executor.complete",
            workflow=spec_name,
            status=result.status.value,
            duration=result.duration_seconds,
        )

        return summary

    return _handler


def execute_workflow(
    workflow: Workflow,
    params: dict[str, Any] | None = None,
    dry_run: bool = False,
    runnable: Runnable | None = None,
) -> WorkflowResult:
    """Execute a workflow directly (no dispatcher needed).

    This is a convenience wrapper around :class:`WorkflowRunner` for
    cases where you want to run a workflow synchronously without going
    through the full ``EventDispatcher`` submission path.

    Args:
        workflow: The workflow to execute.
        params: Input parameters.
        dry_run: If ``True``, pipeline steps return mock success.
        runnable: ``EventDispatcher`` (or any ``Runnable``) for
            pipeline step tracking.
    """
    runner = WorkflowRunner(runnable=runnable, dry_run=dry_run)
    return runner.execute(workflow, params=params)


def register_workflow_executor(
    registry: HandlerRegistry | None = None,
    runnable: Runnable | None = None,
) -> None:
    """Register the workflow handler with the execution handler registry.

    This connects the execution layer (``WorkSpec`` submission) to the
    orchestration layer (:class:`WorkflowRunner`).  After calling this,
    submitting ``workflow_spec("my.workflow")`` to an ``EventDispatcher``
    will execute the workflow found in the workflow registry.

    Args:
        registry: ``HandlerRegistry`` to register with (uses default
            if ``None``).
        runnable: An ``EventDispatcher`` (or any ``Runnable``) that
            the ``WorkflowRunner`` will use for pipeline steps.
            Pass the **same** ``EventDispatcher`` that owns the
            executor so pipeline sub-steps get proper ``RunRecord``
            tracking.

    Example::

        from spine.execution.dispatcher import EventDispatcher
        from spine.execution.executors import MemoryExecutor
        from spine.execution.registry import get_default_registry
        from spine.execution.workflow_executor import register_workflow_executor

        dispatcher = EventDispatcher(executor=MemoryExecutor())
        registry = get_default_registry()
        register_workflow_executor(registry, runnable=dispatcher)
    """
    if registry is None:
        from spine.execution.registry import get_default_registry

        registry = get_default_registry()

    # Register a generic "workflow" handler.  The MemoryExecutor passes
    # spec_name via params["__spec_name__"], so one handler covers all
    # workflow names.
    if not registry.has("workflow", "__all__"):
        handler = _make_workflow_handler(runnable=runnable)
        registry.register(
            kind="workflow",
            name="__all__",
            handler=handler,
            description="Bridges WorkSpec(kind=workflow) to WorkflowRunner",
            tags=["orchestration", "workflow"],
        )

    logger.debug("workflow_executor.registered")
