#!/usr/bin/env python3
"""State Machine Transitions — Enforced Lifecycle for Job Executions.

================================================================================
WHAT IS A STATE MACHINE?
================================================================================

A **state machine** (or finite-state machine, FSM) is a computational model
where a system can be in exactly ONE state at any time, and transitions
between states follow explicit, predefined rules.

In spine-core, every job execution (operation, task, workflow) has a lifecycle
governed by state machines.  This prevents impossible states like:
- A job being "completed" before it ever started
- A successful job being retried
- A cancelled job suddenly running again

Why This Matters for Job Engines:
    Without explicit state machine enforcement, distributed systems suffer from:
    1. **Race conditions** — Two workers both try to "start" the same job
    2. **Zombie jobs** — Jobs stuck in "running" forever after crashes
    3. **Audit failures** — Can't prove a job didn't run twice
    4. **Recovery confusion** — Which jobs are safe to retry?

    State machines make these problems *impossible by construction*.


================================================================================
ARCHITECTURE: TWO-LEVEL STATE MACHINES
================================================================================

spine-core uses TWO distinct but related state machines::

    ┌─────────────────────────────────────────────────────────────────────────┐
    │  LEVEL 1: ExecutionStatus (Operation/Workflow Level)                    │
    │  ═══════════════════════════════════════════════════                   │
    │  Tracks the overall execution of a operation or workflow.               │
    │  A workflow may contain many steps, but it has ONE ExecutionStatus.    │
    └─────────────────────────────────────────────────────────────────────────┘

                                ┌─────────┐
                                │ PENDING │ ◄─── Job submitted, waiting
                                └────┬────┘
                      ┌──────────────┼──────────────┐
                      ▼              ▼              ▼
                ┌─────────┐    ┌─────────┐    ┌───────────┐
                │ QUEUED  │    │ RUNNING │    │ CANCELLED │ (terminal)
                └────┬────┘    └────┬────┘    └───────────┘
                     │              │
                     └──────┬───────┘
                            ▼
              ┌─────────────┼─────────────┬──────────────┐
              ▼             ▼             ▼              ▼
        ┌───────────┐ ┌─────────┐   ┌───────────┐  ┌───────────┐
        │ COMPLETED │ │ FAILED  │   │ TIMED_OUT │  │ CANCELLED │
        └───────────┘ └────┬────┘   └─────┬─────┘  └───────────┘
          (terminal)       │              │          (terminal)
                           └──────┬───────┘
                                  ▼
                            ┌─────────┐
                            │ PENDING │ ◄─── Retry cycle
                            └─────────┘


    ┌─────────────────────────────────────────────────────────────────────────┐
    │  LEVEL 2: RunStatus (Individual Task/Step Level)                       │
    │  ═══════════════════════════════════════════════                       │
    │  Tracks individual task executions.  A workflow with 5 steps has       │
    │  5 RunRecords, each with its own RunStatus.                            │
    └─────────────────────────────────────────────────────────────────────────┘

                                ┌─────────┐
                                │ PENDING │
                                └────┬────┘
                      ┌──────────────┼──────────────┐
                      ▼              ▼              ▼
                ┌─────────┐    ┌─────────┐    ┌───────────┐
                │ QUEUED  │ ──►│ RUNNING │    │ CANCELLED │
                └─────────┘    └────┬────┘    └───────────┘
                                    │
                      ┌─────────────┼─────────────┐
                      ▼             ▼             ▼
                ┌───────────┐ ┌─────────┐   ┌───────────┐
                │ COMPLETED │ │ FAILED  │──►│DEAD_LETTER│
                └───────────┘ └────┬────┘   └─────┬─────┘
                                   │              │
                                   └──────┬───────┘
                                          ▼
                                    ┌─────────┐
                                    │ PENDING │ ◄─── Retry
                                    └─────────┘


================================================================================
DATABASE SCHEMA: STORING EXECUTION STATE
================================================================================

The execution state is persisted to enable crash recovery and auditing::

    ┌─────────────────────────────────────────────────────────────────────────┐
    │  Table: core_runs                                                       │
    ├─────────────────────────────────────────────────────────────────────────┤
    │  run_id          VARCHAR(36)  PRIMARY KEY  -- ULID/UUID                │
    │  status          VARCHAR(20)  NOT NULL     -- RunStatus enum value     │
    │  spec_kind       VARCHAR(20)  NOT NULL     -- 'task'|'operation'|...    │
    │  spec_name       VARCHAR(255) NOT NULL     -- Handler name             │
    │  spec_params     JSON                      -- Execution parameters     │
    │  created_at      TIMESTAMP    NOT NULL     -- When submitted           │
    │  started_at      TIMESTAMP                 -- When execution began     │
    │  completed_at    TIMESTAMP                 -- When finished            │
    │  result          JSON                      -- Output on success        │
    │  error           TEXT                      -- Error message on failure │
    │  error_type      VARCHAR(255)              -- Exception class name     │
    │  executor_name   VARCHAR(50)               -- 'celery'|'local'|'k8s'   │
    │  external_ref    VARCHAR(255)              -- Celery task_id, etc.     │
    │  attempt         INTEGER      DEFAULT 1    -- Retry attempt number     │
    │  duration_sec    REAL                      -- Execution time           │
    └─────────────────────────────────────────────────────────────────────────┘

    Indexes:
    - idx_runs_status ON core_runs(status) -- Find all PENDING/RUNNING jobs
    - idx_runs_name   ON core_runs(spec_name) -- Find runs of specific task


================================================================================
WHY EXPLICIT TRANSITION VALIDATION?
================================================================================

Could we just set `run.status = 'completed'` directly?  Yes, but consider:

    PROBLEM 1: Invalid State Sequences
    ───────────────────────────────────
    Without validation, this compiles and runs:

        run.status = 'completed'  # Oops, never started!
        run.status = 'running'    # Wait, it's already done?
        run.status = 'pending'    # Retry a success?!

    The database now contains lies.  Dashboards show nonsense.  Alerts fire
    incorrectly.  Billing is wrong.  Compliance fails.

    SOLUTION: Explicit transition functions raise InvalidTransitionError
    when the transition graph is violated.


    PROBLEM 2: Distributed Race Conditions
    ───────────────────────────────────────
    Two workers see a PENDING job at the same time.  Both try to start it:

        Worker A: run.status = 'running'
        Worker B: run.status = 'running'  # Who wins?

    With explicit transitions + database locks:

        Worker A: validate_transition(PENDING → RUNNING) ✓
                  UPDATE runs SET status='running' WHERE id=? AND status='pending'
                  (affects 1 row)

        Worker B: validate_transition(PENDING → RUNNING) ✓
                  UPDATE runs SET status='running' WHERE id=? AND status='pending'
                  (affects 0 rows — already running!)


    PROBLEM 3: Crash Recovery
    ─────────────────────────
    Worker crashes mid-execution.  Job is stuck in RUNNING forever.

    State machine enables recovery policy:
    - Jobs RUNNING > 1 hour with no heartbeat → mark FAILED, retry
    - Jobs FAILED < 3 times → transition to PENDING (retry)
    - Jobs FAILED 3+ times → transition to DEAD_LETTERED


================================================================================
BEST PRACTICES
================================================================================

1. **Never set status directly** — Always use transition methods::

       # BAD
       run.status = RunStatus.COMPLETED

       # GOOD
       run.mark_completed(result={"rows": 42})

2. **Always check for InvalidTransitionError** in production code::

       try:
           run.mark_started()
       except InvalidTransitionError:
           logger.warning(f"Run {run.run_id} already started by another worker")
           return  # Don't double-execute

3. **Design for idempotency** — Your handlers should be safe to run twice::

       def ingest_filings(params):
           # Use idempotency keys so re-runs don't duplicate data
           key = f"ingest:{params['cik']}:{params['form_type']}"
           if already_processed(key):
               return {"skipped": True}
           # ... do work ...
           mark_processed(key)

4. **Log all transitions** — Essential for debugging and compliance::

       def mark_completed(self, result=None):
           logger.info(
               "run_transition",
               run_id=self.run_id,
               from_status=self.status.value,
               to_status="completed",
           )
           self._transition_to(RunStatus.COMPLETED)


================================================================================
EXAMPLE USAGE
================================================================================

Run this example:
    python examples/02_execution/17_state_machine.py

See Also:
    - :mod:`spine.execution.models` — ExecutionStatus, transition rules
    - :mod:`spine.execution.runs` — RunRecord, RunStatus
    - :mod:`spine.execution.dispatcher` — Coordinated execution with transitions
    - :mod:`spine.execution.dlq` — Dead letter queue for failed jobs
"""
from datetime import UTC, datetime

from spine.execution.models import (
    EXECUTION_VALID_TRANSITIONS,
    ExecutionStatus,
    InvalidTransitionError,
    validate_execution_transition,
)
from spine.execution.runs import (
    RUN_VALID_TRANSITIONS,
    RunRecord,
    RunStatus,
)
from spine.execution.spec import task_spec


def main():
    print("=" * 60)
    print("State Machine Transition Examples")
    print("=" * 60)

    # =================================================================
    # 1. Execution status — valid transition graph
    # =================================================================
    print("\n[1] ExecutionStatus Transition Graph")
    print("-" * 40)

    for status in ExecutionStatus:
        targets = EXECUTION_VALID_TRANSITIONS.get(status, frozenset())
        if targets:
            target_names = ", ".join(t.value for t in sorted(targets, key=lambda t: t.value))
            print(f"  {status.value:>10}  →  {target_names}")
        else:
            print(f"  {status.value:>10}  →  (terminal — no outgoing)")

    # =================================================================
    # 2. Valid transitions pass silently
    # =================================================================
    print("\n[2] Valid Transitions (no exception)")
    print("-" * 40)

    transitions = [
        (ExecutionStatus.PENDING, ExecutionStatus.QUEUED),
        (ExecutionStatus.QUEUED, ExecutionStatus.RUNNING),
        (ExecutionStatus.RUNNING, ExecutionStatus.COMPLETED),
        (ExecutionStatus.RUNNING, ExecutionStatus.FAILED),
        (ExecutionStatus.FAILED, ExecutionStatus.PENDING),  # retry
    ]
    for current, target in transitions:
        validate_execution_transition(current, target)
        print(f"  ✓  {current.value} → {target.value}")

    # =================================================================
    # 3. Invalid transitions raise InvalidTransitionError
    # =================================================================
    print("\n[3] Blocked Transitions (InvalidTransitionError)")
    print("-" * 40)

    blocked = [
        (ExecutionStatus.COMPLETED, ExecutionStatus.RUNNING, "terminal state"),
        (ExecutionStatus.RUNNING, ExecutionStatus.QUEUED, "can't go backward"),
        (ExecutionStatus.COMPLETED, ExecutionStatus.PENDING, "no retry from success"),
    ]
    for current, target, reason in blocked:
        try:
            validate_execution_transition(current, target)
        except InvalidTransitionError as e:
            print(f"  ✗  {current.value} → {target.value}  ({reason})")
            print(f"     Error: {e}")

    # =================================================================
    # 4. RunRecord lifecycle — happy path
    # =================================================================
    print("\n[4] RunRecord Happy Path: PENDING → RUNNING → COMPLETED")
    print("-" * 40)

    run = RunRecord(
        run_id="run-001",
        spec=task_spec("ingest_filings", params={"form_type": "10-K"}),
        status=RunStatus.PENDING,
        created_at=datetime.now(UTC),
    )
    print(f"  Created:   status={run.status.value}")

    run.mark_started()
    print(f"  Started:   status={run.status.value}, started_at={run.started_at}")

    run.mark_completed(result={"filings_processed": 42})
    print(f"  Completed: status={run.status.value}, result={run.result}")
    print(f"             duration={run.duration_seconds:.3f}s")

    # =================================================================
    # 5. RunRecord lifecycle — failure + retry
    # =================================================================
    print("\n[5] Failure Path: PENDING → RUNNING → FAILED")
    print("-" * 40)

    run2 = RunRecord(
        run_id="run-002",
        spec=task_spec("fetch_price_data", params={"ticker": "AAPL"}),
        status=RunStatus.PENDING,
        created_at=datetime.now(UTC),
    )
    run2.mark_started()
    run2.mark_failed("Connection timeout", error_type="TimeoutError")
    print(f"  Status: {run2.status.value}")
    print(f"  Error:  {run2.error} ({run2.error_type})")

    # =================================================================
    # 6. RunRecord — blocking illegal transitions
    # =================================================================
    print("\n[6] RunRecord Enforcement — Blocked Transitions")
    print("-" * 40)

    # Try to complete a run that's already completed
    try:
        run.mark_started()  # run is COMPLETED from step 4
    except InvalidTransitionError as e:
        print(f"  ✗  Cannot restart completed run: {e}")

    # Try to complete a PENDING run (must start first)
    fresh = RunRecord(
        run_id="run-003",
        spec=task_spec("validate_data"),
        status=RunStatus.PENDING,
        created_at=datetime.now(UTC),
    )
    try:
        fresh.mark_completed()
    except InvalidTransitionError as e:
        print(f"  ✗  Cannot complete without starting: {e}")

    # =================================================================
    # 7. RunStatus transition graph
    # =================================================================
    print("\n[7] RunStatus Transition Graph")
    print("-" * 40)

    for status in RunStatus:
        targets = RUN_VALID_TRANSITIONS.get(status, frozenset())
        if targets:
            target_names = ", ".join(t.value for t in sorted(targets, key=lambda t: t.value))
            print(f"  {status.value:>14}  →  {target_names}")
        else:
            print(f"  {status.value:>14}  →  (terminal)")

    # =================================================================
    # 8. Cancellation from multiple states
    # =================================================================
    print("\n[8] Cancellation — Valid From PENDING and RUNNING")
    print("-" * 40)

    for initial in [RunStatus.PENDING, RunStatus.RUNNING]:
        r = RunRecord(
            run_id=f"cancel-{initial.value}",
            spec=task_spec("slow_job"),
            status=RunStatus.PENDING,
            created_at=datetime.now(UTC),
        )
        if initial == RunStatus.RUNNING:
            r.mark_started()
        r.mark_cancelled()
        print(f"  ✓  {initial.value} → cancelled")

    print("\n" + "=" * 60)
    print("All state machine examples completed successfully!")
    print("=" * 60)


if __name__ == "__main__":
    main()
