#!/usr/bin/env python3
"""WorkerLoop — Background Polling Engine for Database-Backed Task Execution.

================================================================================
WHY A WORKER LOOP?
================================================================================

REST APIs accept work by writing to a database::

    POST /api/v1/runs  →  INSERT INTO core_runs (status='pending', ...)

But who actually RUNS the work?  The WorkerLoop bridges this gap::

    API writes to DB  →  WorkerLoop polls DB  →  WorkerLoop executes handlers

This is the same pattern used by Celery, Sidekiq, and every serious job queue:
    1. **Decouple submission from execution** — API responds immediately (202)
    2. **Survive restarts** — Work is persisted, not lost if worker crashes
    3. **Scale horizontally** — Multiple workers can poll the same queue
    4. **Rate limiting** — Workers control how fast they consume work


================================================================================
ARCHITECTURE: SUBMIT → POLL → EXECUTE
================================================================================

::

    ┌──────────┐     POST /runs    ┌──────────────┐
    │  Client  │──────────────────►│   Database   │
    └──────────┘   (status=PENDING)│  core_runs   │
                                   └──────┬───────┘
                                          │
                     poll_interval=1s     │ SELECT ... WHERE status='pending'
                                          │
                                   ┌──────┴───────┐
                                   │  WorkerLoop  │
                                   │              │
                                   │  1. Claim run │  UPDATE status='running'
                                   │  2. Resolve   │  HandlerRegistry.get()
                                   │  3. Execute   │  handler(params)
                                   │  4. Update    │  status='completed'
                                   └──────────────┘


================================================================================
EXAMPLE USAGE
================================================================================

Run this example:
    python examples/02_execution/14_worker_loop.py

See Also:
    - :mod:`spine.execution.worker` — WorkerLoop
    - :mod:`spine.execution.registry` — HandlerRegistry
    - ``examples/02_execution/08_fastapi_integration.py`` — API that submits work
"""
import json
import sqlite3
import time
from datetime import UTC, datetime
from uuid import uuid4

from spine.execution.registry import HandlerRegistry
from spine.execution.worker import WorkerLoop


def create_schema(conn: sqlite3.Connection) -> None:
    """Create execution tables."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS core_executions (
            id TEXT PRIMARY KEY,
            pipeline TEXT,
            params TEXT DEFAULT '{}',
            status TEXT DEFAULT 'pending',
            lane TEXT DEFAULT 'default',
            trigger_source TEXT DEFAULT 'api',
            parent_execution_id TEXT,
            created_at TEXT,
            started_at TEXT,
            completed_at TEXT,
            result TEXT,
            error TEXT,
            retry_count INTEGER DEFAULT 0,
            idempotency_key TEXT
        );
        CREATE TABLE IF NOT EXISTS core_execution_events (
            id TEXT PRIMARY KEY,
            execution_id TEXT,
            event_type TEXT,
            timestamp TEXT,
            data TEXT DEFAULT '{}'
        );
    """)


def submit_run(conn: sqlite3.Connection, kind: str, name: str, params: dict) -> str:
    """Simulate POST /runs — insert a pending execution."""
    run_id = str(uuid4())
    now = datetime.now(UTC).isoformat()
    conn.execute(
        "INSERT INTO core_executions (id, pipeline, params, status, created_at) "
        "VALUES (?, ?, ?, 'pending', ?)",
        (run_id, f"{kind}:{name}", json.dumps(params), now),
    )
    conn.commit()
    return run_id


def get_run(conn: sqlite3.Connection, run_id: str) -> dict:
    """Query a run by ID."""
    cur = conn.execute("SELECT * FROM core_executions WHERE id = ?", (run_id,))
    row = cur.fetchone()
    cols = [d[0] for d in cur.description]
    return dict(zip(cols, row))


def main():
    print("=" * 60)
    print("Worker Loop — Background Task Execution")
    print("=" * 60)

    # Set up in-memory database
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    create_schema(conn)

    # Register handlers
    registry = HandlerRegistry()
    registry.register("task", "echo", lambda p: {"echoed": p})
    registry.register("task", "add", lambda p: {"result": p.get("a", 0) + p.get("b", 0)})
    registry.register("pipeline", "etl_stub",
                       lambda p: {"pipeline": "etl_stub", "records": p.get("records", 0)})

    # Submit some runs (simulating API calls)
    print("\n[1] Submitting runs …")
    run1 = submit_run(conn, "task", "echo", {"msg": "hello"})
    run2 = submit_run(conn, "task", "add", {"a": 17, "b": 25})
    run3 = submit_run(conn, "pipeline", "etl_stub", {"records": 500})
    print(f"  Submitted: {run1[:8]}… (echo)")
    print(f"  Submitted: {run2[:8]}… (add)")
    print(f"  Submitted: {run3[:8]}… (etl_stub)")

    # Start background worker
    print("\n[2] Starting worker …")
    worker = WorkerLoop(
        conn=conn,
        poll_interval=0.2,
        batch_size=10,
        max_workers=2,
        registry=registry,
        worker_id="demo-worker",
    )
    t = worker.start_background()

    # Wait for processing
    time.sleep(1.5)

    # Check results
    print("\n[3] Results:")
    for rid, label in [(run1, "echo"), (run2, "add"), (run3, "etl_stub")]:
        row = get_run(conn, rid)
        status = row["status"]
        result = json.loads(row["result"]) if row["result"] else None
        started = row["started_at"]
        completed = row["completed_at"]
        print(f"  {label}: status={status}")
        if result:
            print(f"    result={result}")
        if started and completed:
            print(f"    started={started[:19]}  completed={completed[:19]}")

    # Worker stats
    print("\n[4] Worker stats:")
    stats = worker.get_stats()
    print(f"  processed={stats.total_processed}")
    print(f"  completed={stats.total_completed}")
    print(f"  failed={stats.total_failed}")
    print(f"  uptime={stats.uptime_seconds:.1f}s")

    # Shutdown
    worker.stop()
    t.join(timeout=2)
    conn.close()
    print("\n✓ Done!")


if __name__ == "__main__":
    main()
