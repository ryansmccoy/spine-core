"""Managed Workflows — import existing functions, get full lifecycle management.

This module is the **primary entry point** for bringing external code into
spine-core.  It provides a fluent builder that takes plain Python functions
and gives you:

- **Persistence** — every run is recorded (SQLite file or PostgreSQL)
- **Idempotency** — re-running with the same partition is a no-op
- **Observability** — query history, inspect failures, see timing
- **Zero coupling** — your functions never import spine types

Quick start
-----------
::

    from spine.orchestration.managed_workflow import ManagedWorkflow

    # 1. Build a pipeline from plain functions
    pipeline = (
        ManagedWorkflow("sec.risk_analysis")
        .step("fetch", fetch_filing_data, config={"cik": "0000320193"})
        .step("score", calculate_risk_score, config={"threshold": 50})
        .build()
    )

    # 2. Run it (in-memory by default, or pass db= for persistence)
    result = pipeline.run()

    # 3. Query results
    pipeline.show()          # pretty-print last run
    pipeline.history()       # list all runs
    pipeline.query_table()   # raw SQL against the backing store

Persistent mode
~~~~~~~~~~~~~~~
::

    # File-based SQLite — runs persist across restarts
    pipeline = (
        ManagedWorkflow("sec.risk_analysis", db="examples/spine.db")
        .step("fetch", fetch_filing_data)
        .build()
    )

    # PostgreSQL (requires Docker or remote)
    pipeline = (
        ManagedWorkflow("sec.risk_analysis",
                        db="postgresql://spine:spine@localhost:10432/spine")
        .step("fetch", fetch_filing_data)
        .build()
    )

Design
------
``ManagedWorkflow`` is a builder that produces a ``ManagedPipeline``.
The pipeline wraps ``TrackedWorkflowRunner`` (persistent) or
``WorkflowRunner`` (in-memory) and provides query helpers.

Tier: Basic (spine-core)
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from spine.core.logging import get_logger

from spine.core.connection import ConnectionInfo, create_connection
from spine.orchestration.step_adapters import adapt_function, is_workflow_step
from spine.orchestration.step_result import StepResult
from spine.orchestration.step_types import ErrorPolicy, Step
from spine.orchestration.workflow import Workflow
from spine.orchestration.workflow_context import WorkflowContext
from spine.orchestration.workflow_runner import (
    StepExecution,
    WorkflowResult,
    WorkflowRunner,
    WorkflowStatus,
)

logger = get_logger(__name__)


# ── Stub Runnable (lambda-only workflows don't need a real one) ──────────


class _StubRunnable:
    """No-op runnable for workflows that only use lambda/function steps."""

    def submit_pipeline_sync(
        self,
        pipeline_name: str,
        params: dict[str, Any] | None = None,
        *,
        parent_run_id: str | None = None,
        correlation_id: str | None = None,
    ) -> Any:
        from spine.execution.runnable import PipelineRunResult

        return PipelineRunResult(status="completed")





# ── Step definition ──────────────────────────────────────────────────────


@dataclass
class StepDef:
    """A step definition in the builder."""

    name: str
    fn: Callable[..., Any]
    config: dict[str, Any]
    depends_on: list[str]
    strict: bool
    on_error: ErrorPolicy


# ── ManagedPipeline (the built result) ───────────────────────────────────


class ManagedPipeline:
    """A fully-configured pipeline ready to run and query.

    Do not construct directly — use ``ManagedWorkflow.build()``.
    """

    def __init__(
        self,
        workflow: Workflow,
        conn: Any,
        info: ConnectionInfo,
    ) -> None:
        self._workflow = workflow
        self._conn = conn
        self._info = info
        self._persistent = info.persistent
        self._db_url = info.url
        self._runs: list[WorkflowResult] = []

    # ── Execute ──────────────────────────────────────────────────────

    def run(
        self,
        params: dict[str, Any] | None = None,
        partition: dict[str, Any] | None = None,
    ) -> WorkflowResult:
        """Execute the pipeline.

        Parameters
        ----------
        params:
            Runtime parameters merged into each step's context.
        partition:
            Partition key for idempotent execution.  When provided,
            uses ``TrackedWorkflowRunner`` with manifest tracking.
            Without a partition, uses the basic ``WorkflowRunner``.

        Returns
        -------
        WorkflowResult
        """
        runnable = _StubRunnable()

        if partition is not None:
            # Use tracked runner for persistence + idempotency
            from spine.orchestration.tracked_runner import TrackedWorkflowRunner

            runner = TrackedWorkflowRunner(
                self._conn,
                runnable=runnable,
                skip_if_completed=True,
            )
            result = runner.execute(
                self._workflow,
                params=params,
                partition=partition,
            )
        else:
            # Basic runner — still records in self._runs
            runner = WorkflowRunner(runnable=runnable)
            result = runner.execute(self._workflow, params=params)

        self._runs.append(result)
        return result

    # ── Query / Inspect ──────────────────────────────────────────────

    def show(self, run_index: int = -1) -> None:
        """Pretty-print a run result.

        Parameters
        ----------
        run_index:
            Index into the internal runs list.  Defaults to the last run.
        """
        if not self._runs:
            print("  (no runs yet)")
            return

        result = self._runs[run_index]
        print(f"\n  Pipeline : {result.workflow_name}")
        print(f"  Run ID   : {result.run_id}")
        print(f"  Status   : {result.status.value}")
        print(f"  Duration : {result.duration_seconds:.3f}s" if result.duration_seconds else "  Duration : —")
        if result.error:
            print(f"  Error    : {result.error}")

        if result.step_executions:
            print(f"  Steps    :")
            for se in result.step_executions:
                icon = "OK" if se.status == "completed" else "FAIL" if se.status == "failed" else "SKIP"
                out_preview = ""
                if se.result and se.result.output:
                    out_preview = f" → {_truncate(str(se.result.output), 60)}"
                dur = f" ({se.duration_seconds:.3f}s)" if se.duration_seconds else ""
                print(f"    [{icon}] {se.step_name}{dur}{out_preview}")

        # Show step outputs from context
        if result.context:
            print(f"  Outputs  :")
            for step_name in result.completed_steps:
                out = result.context.get_output(step_name)
                if out:
                    print(f"    {step_name}: {_truncate(str(out), 70)}")

    def history(self) -> list[dict[str, Any]]:
        """Return a list of all run summaries (in-memory + DB).

        Returns
        -------
        list[dict]
            Each dict has ``run_id``, ``status``, ``started_at``,
            ``duration_seconds``, ``completed_steps``, ``error``.
        """
        # In-memory runs
        summaries = []
        for r in self._runs:
            summaries.append({
                "run_id": r.run_id,
                "workflow": r.workflow_name,
                "status": r.status.value,
                "started_at": r.started_at.isoformat() if r.started_at else None,
                "duration_seconds": r.duration_seconds,
                "completed_steps": r.completed_steps,
                "failed_steps": r.failed_steps,
                "error": r.error,
            })
        return summaries

    def query_db(self, sql: str, params: tuple = ()) -> list[dict]:
        """Run a SQL query against the backing database.

        Parameters
        ----------
        sql:
            SQL query string (use ``?`` for SQLite, ``%s`` for Postgres).
        params:
            Query parameters.

        Returns
        -------
        list[dict]
            Rows as dictionaries.
        """
        cursor = self._conn.execute(sql, params)
        rows = cursor.fetchall()
        if not rows:
            return []
        # Convert Row objects to dicts
        if hasattr(rows[0], "keys"):
            return [dict(r) for r in rows]
        # Fall back — zip with column names
        cols = [d[0] for d in cursor.description] if cursor.description else []
        return [dict(zip(cols, r)) for r in rows]

    def table_counts(self) -> dict[str, int]:
        """Return row counts for all core tables.

        Useful for verifying that data was persisted.
        """
        tables_sql = (
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name LIKE 'core_%' ORDER BY name"
        )
        try:
            rows = self._conn.execute(tables_sql).fetchall()
        except Exception:
            return {}

        counts: dict[str, int] = {}
        for row in rows:
            name = row[0] if isinstance(row, (tuple, list)) else row["name"]
            try:
                count_row = self._conn.execute(f"SELECT COUNT(*) FROM [{name}]").fetchone()
                counts[name] = count_row[0] if count_row else 0
            except Exception:
                counts[name] = -1
        return counts

    def close(self) -> None:
        """Close the backing database connection."""
        if hasattr(self._conn, "close"):
            self._conn.close()

    @property
    def workflow(self) -> Workflow:
        """The underlying Workflow object."""
        return self._workflow

    @property
    def conn(self) -> Any:
        """The database connection (for advanced queries)."""
        return self._conn

    @property
    def is_persistent(self) -> bool:
        """Whether this pipeline persists data to disk/server."""
        return self._persistent

    @property
    def last_result(self) -> WorkflowResult | None:
        """The most recent run result, or None."""
        return self._runs[-1] if self._runs else None

    def __repr__(self) -> str:
        mode = "persistent" if self._persistent else "in-memory"
        steps = [s.name for s in self._workflow.steps]
        return (
            f"ManagedPipeline(name={self._workflow.name!r}, "
            f"steps={steps}, mode={mode!r}, runs={len(self._runs)})"
        )


# ── ManagedWorkflow builder ─────────────────────────────────────────────


class ManagedWorkflow:
    """Fluent builder for managed pipelines.

    Import your existing functions, chain ``.step()`` calls, then
    ``.build()`` to get a ``ManagedPipeline`` with full lifecycle
    management.

    Examples
    --------
    Minimal (in-memory)::

        pipeline = (
            ManagedWorkflow("my.pipeline")
            .step("fetch", fetch_data, config={"url": "..."})
            .step("transform", transform, config={"format": "json"})
            .build()
        )
        result = pipeline.run()

    Persistent (SQLite file)::

        pipeline = (
            ManagedWorkflow("my.pipeline", db="pipeline_runs.db")
            .step("fetch", fetch_data)
            .build()
        )
        result = pipeline.run(partition={"date": "2026-02-16"})

        # Query the database afterwards
        pipeline.show()
        runs = pipeline.query_db(
            "SELECT * FROM core_manifest WHERE domain LIKE ?",
            ("%my.pipeline%",)
        )
    """

    def __init__(
        self,
        name: str,
        *,
        db: str | None = None,
        domain: str | None = None,
        description: str = "",
    ) -> None:
        """Initialize the builder.

        Parameters
        ----------
        name:
            Workflow name (e.g. ``"sec.risk_analysis"``).
        db:
            Database URL or file path.  Options:

            - ``None`` — in-memory SQLite (default, ephemeral)
            - ``"path/to/file.db"`` — file-based SQLite (persistent)
            - ``"postgresql://user:pass@host:port/db"`` — PostgreSQL

        domain:
            Logical domain for tracking (defaults to name).
        description:
            Human-readable description.
        """
        self._name = name
        self._db = db
        self._domain = domain or name
        self._description = description
        self._steps: list[StepDef] = []
        self._defaults: dict[str, Any] = {}

    def step(
        self,
        name: str,
        fn: Callable[..., Any],
        *,
        config: dict[str, Any] | None = None,
        depends_on: list[str] | None = None,
        strict: bool = False,
        on_error: str = "stop",
    ) -> ManagedWorkflow:
        """Add a step backed by a plain Python function.

        The function should accept keyword arguments and return a dict,
        bool, str, int, float, or None.  The return value is
        automatically coerced to ``StepResult`` via
        ``StepResult.from_value()``.

        Parameters
        ----------
        name:
            Step name (unique within the workflow).
        fn:
            Any callable — no framework imports required.
        config:
            Static configuration passed as kwargs to the function.
        depends_on:
            Names of steps that must complete first.
        strict:
            If ``True``, fail early when required params are missing.
        on_error:
            Error policy: ``"stop"`` (default), ``"continue"``, or ``"retry"``.

        Returns
        -------
        self (for chaining)
        """
        self._steps.append(StepDef(
            name=name,
            fn=fn,
            config=config or {},
            depends_on=depends_on or [],
            strict=strict,
            on_error=ErrorPolicy(on_error),
        ))
        return self

    def defaults(self, **kwargs: Any) -> ManagedWorkflow:
        """Set default parameters for all steps.

        These are available via ``ctx.params`` and are merged with
        step-specific config.

        Returns
        -------
        self (for chaining)
        """
        self._defaults.update(kwargs)
        return self

    def build(self) -> ManagedPipeline:
        """Build the pipeline — creates DB connection and workflow.

        Returns
        -------
        ManagedPipeline
            Ready to ``.run()``, ``.show()``, ``.history()``, etc.
        """
        if not self._steps:
            raise ValueError("No steps defined — call .step() before .build()")

        # Convert StepDefs to Step objects
        steps = []
        for sd in self._steps:
            step = Step.from_function(
                name=sd.name,
                fn=sd.fn,
                config=sd.config,
                on_error=sd.on_error,
                depends_on=sd.depends_on if sd.depends_on else None,
                strict=sd.strict,
            )
            steps.append(step)

        workflow = Workflow(
            name=self._name,
            domain=self._domain,
            description=self._description,
            steps=steps,
            defaults=self._defaults,
        )

        conn, info = create_connection(self._db, init_schema=True)
        return ManagedPipeline(workflow, conn, info)


# ── Convenience function ─────────────────────────────────────────────────


def manage(
    *functions: Callable[..., Any],
    name: str | None = None,
    db: str | None = None,
    configs: dict[str, dict[str, Any]] | None = None,
) -> ManagedPipeline:
    """One-liner: wrap plain functions into a managed pipeline.

    Each function becomes a step named after the function.  Steps run
    sequentially in the order provided.

    Parameters
    ----------
    *functions:
        Plain callables to chain as sequential workflow steps.
    name:
        Workflow name.  Defaults to the first function's name.
    db:
        Database URL or file path (same as ``ManagedWorkflow.db``).
    configs:
        Optional per-step configs keyed by function name.

    Returns
    -------
    ManagedPipeline

    Example::

        from spine.orchestration.managed_workflow import manage

        pipeline = manage(fetch_data, validate, transform, db="runs.db")
        pipeline.run(partition={"date": "2026-02-16"})
        pipeline.show()
    """
    if not functions:
        raise ValueError("At least one function is required")

    configs = configs or {}
    wf_name = name or functions[0].__name__

    builder = ManagedWorkflow(wf_name, db=db)
    for fn in functions:
        step_name = fn.__name__
        builder.step(step_name, fn, config=configs.get(step_name, {}))

    return builder.build()


# ── Helpers ──────────────────────────────────────────────────────────────


def _truncate(s: str, max_len: int = 60) -> str:
    """Truncate a string for display."""
    return s if len(s) <= max_len else s[: max_len - 3] + "..."
