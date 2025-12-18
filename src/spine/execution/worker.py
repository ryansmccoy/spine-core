"""Background worker loop — polls pending executions and dispatches them.

The WorkerLoop bridges the ops layer (DB-only submit) to actual execution.
It periodically polls ``core_executions`` for rows with status='pending',
converts them to :class:`WorkSpec`, and dispatches via a configured
:class:`Executor`.

Usage (programmatic)::

    from spine.execution.worker import WorkerLoop
    from spine.execution.executors.local import LocalExecutor

    worker = WorkerLoop(db_path="spine.db", executor=LocalExecutor())
    worker.start()  # blocking — runs until SIGINT/SIGTERM

Usage (CLI)::

    spine worker start --workers 4 --poll-interval 2
"""

from __future__ import annotations

import json
import logging
import os
import signal
import sqlite3
import threading
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass
class WorkerInfo:
    """Metadata about a running worker."""

    worker_id: str
    pid: int
    started_at: datetime
    poll_interval: float
    max_workers: int
    status: str = "running"
    runs_processed: int = 0
    runs_failed: int = 0
    current_run_id: str | None = None
    hostname: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "worker_id": self.worker_id,
            "pid": self.pid,
            "started_at": self.started_at.isoformat(),
            "poll_interval": self.poll_interval,
            "max_workers": self.max_workers,
            "status": self.status,
            "runs_processed": self.runs_processed,
            "runs_failed": self.runs_failed,
            "current_run_id": self.current_run_id,
            "hostname": self.hostname,
        }


@dataclass
class WorkerStats:
    """Aggregate statistics for a worker."""

    total_processed: int = 0
    total_failed: int = 0
    total_completed: int = 0
    total_cancelled: int = 0
    uptime_seconds: float = 0
    last_poll_at: datetime | None = None
    active_runs: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_processed": self.total_processed,
            "total_failed": self.total_failed,
            "total_completed": self.total_completed,
            "total_cancelled": self.total_cancelled,
            "uptime_seconds": round(self.uptime_seconds, 2),
            "last_poll_at": self.last_poll_at.isoformat() if self.last_poll_at else None,
            "active_runs": self.active_runs,
        }


# --------------------------------------------------------------------------- #
# Global worker registry (for stats / health endpoints)
# --------------------------------------------------------------------------- #

_active_workers: dict[str, WorkerLoop] = {}
_workers_lock = threading.Lock()


def get_active_workers() -> list[WorkerInfo]:
    """Return info about all active worker loops (in this process)."""
    with _workers_lock:
        return [w.info for w in _active_workers.values()]


def get_worker_stats() -> list[dict[str, Any]]:
    """Return stats dicts for all active workers."""
    with _workers_lock:
        return [w.get_stats().to_dict() for w in _active_workers.values()]


# --------------------------------------------------------------------------- #
# WorkerLoop
# --------------------------------------------------------------------------- #


class WorkerLoop:
    """Polls the database for pending executions and runs them.

    Architecture:
        1. ``_poll()`` fetches pending rows (``SELECT … FOR UPDATE SKIP LOCKED``
           on PG, advisory-lock-free on SQLite).
        2. Atomically transitions status ``pending → running`` and records
           a ``started`` event.
        3. Resolves the handler via :class:`HandlerRegistry`.
        4. Executes the handler in a thread pool.
        5. On completion, transitions status to ``completed`` or ``failed``
           and records the corresponding event.

    Thread-safety:
        The worker uses a single SQLite connection with ``check_same_thread=False``.
        The thread pool handles concurrent execution; the poll loop is
        single-threaded to avoid double-dispatch.
    """

    def __init__(
        self,
        db_path: str | None = None,
        conn: Any | None = None,
        executor: Any | None = None,
        poll_interval: float = 2.0,
        batch_size: int = 10,
        max_workers: int = 4,
        worker_id: str | None = None,
        registry: Any | None = None,
    ):
        """
        Args:
            db_path: Path to SQLite database. Ignored if *conn* is provided.
            conn: Pre-existing DB connection (sqlite3 or psycopg-compatible).
            executor: Optional Executor instance. If ``None``, a
                :class:`LocalExecutor` is created with *max_workers* threads.
            poll_interval: Seconds between poll cycles.
            batch_size: Max rows to claim per poll.
            max_workers: Thread pool size (for LocalExecutor creation).
            worker_id: Custom worker identifier. Auto-generated if ``None``.
            registry: Optional :class:`HandlerRegistry`.  Falls back to
                the global default registry.
        """
        from concurrent.futures import ThreadPoolExecutor

        self._worker_id = worker_id or f"worker-{uuid.uuid4().hex[:8]}"
        self._poll_interval = poll_interval
        self._batch_size = batch_size
        self._max_workers = max_workers
        self._shutdown = threading.Event()
        self._started_at = _utcnow()
        self._stats = WorkerStats()

        # --- DB connection ---------------------------------------------------
        if conn is not None:
            self._conn = conn
            self._owns_conn = False
        elif db_path:
            self._conn = sqlite3.connect(db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._owns_conn = True
        else:
            raise ValueError("Either db_path or conn must be provided")

        # --- Executor --------------------------------------------------------
        if executor is not None:
            self._executor = executor
        else:
            from .executors.local import LocalExecutor
            self._executor = LocalExecutor(max_workers=max_workers)

        # --- Handler registry ------------------------------------------------
        if registry is not None:
            self._registry = registry
        else:
            from .registry import get_default_registry
            self._registry = get_default_registry()

        # --- Thread pool for execution (separate from executor) -----
        self._pool = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix=f"{self._worker_id}",
        )

        # --- Info object (for /workers endpoint) ---
        import platform
        self.info = WorkerInfo(
            worker_id=self._worker_id,
            pid=os.getpid(),
            started_at=self._started_at,
            poll_interval=self._poll_interval,
            max_workers=self._max_workers,
            hostname=platform.node(),
        )

        # Active run tracking
        self._active_run_ids: set[str] = set()
        self._active_lock = threading.Lock()

        # DB lock — required for SQLite which doesn't support concurrent writes
        self._db_lock = threading.Lock()

    @property
    def worker_id(self) -> str:
        return self._worker_id

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #

    def start(self) -> None:
        """Start the poll loop (blocking). Installs signal handlers for
        graceful shutdown on SIGINT / SIGTERM.
        """
        logger.info(
            "Worker %s starting — polling every %.1fs, batch=%d, workers=%d",
            self._worker_id,
            self._poll_interval,
            self._batch_size,
            self._max_workers,
        )

        # Register in global registry
        with _workers_lock:
            _active_workers[self._worker_id] = self

        # Signal handlers (only in main thread)
        try:
            signal.signal(signal.SIGINT, self._handle_signal)
            signal.signal(signal.SIGTERM, self._handle_signal)
        except (ValueError, OSError):
            pass  # Not in main thread — skip signal registration

        try:
            self._run_loop()
        finally:
            self._cleanup()

    def start_background(self) -> threading.Thread:
        """Start the worker in a daemon thread. Returns the thread."""
        t = threading.Thread(
            target=self.start,
            name=f"{self._worker_id}-loop",
            daemon=True,
        )
        t.start()
        return t

    def stop(self) -> None:
        """Request graceful shutdown."""
        logger.info("Worker %s shutting down…", self._worker_id)
        self._shutdown.set()
        self.info.status = "stopping"

    def get_stats(self) -> WorkerStats:
        """Return current worker statistics."""
        with self._active_lock:
            self._stats.active_runs = len(self._active_run_ids)
        self._stats.uptime_seconds = (_utcnow() - self._started_at).total_seconds()
        return self._stats

    # ------------------------------------------------------------------ #
    # Main loop
    # ------------------------------------------------------------------ #

    def _run_loop(self) -> None:
        while not self._shutdown.is_set():
            try:
                claimed = self._poll()
                if claimed:
                    logger.debug("Worker %s claimed %d run(s)", self._worker_id, claimed)
            except Exception:
                logger.exception("Worker %s poll error", self._worker_id)

            self._stats.last_poll_at = _utcnow()
            self._shutdown.wait(self._poll_interval)

    def _poll(self) -> int:
        """Fetch pending executions and dispatch them. Returns count claimed."""
        with self._db_lock:
            cursor = self._conn.cursor()

            # Claim pending rows — atomically set to 'running'
            cursor.execute(
                "SELECT id, workflow, params, lane, trigger_source, "
                "       parent_execution_id, idempotency_key, retry_count "
                "FROM core_executions "
                "WHERE status = 'pending' "
                "ORDER BY created_at ASC "
                "LIMIT ?",
                (self._batch_size,),
            )
            rows = cursor.fetchall()
            if not rows:
                return 0

            claimed = 0
            dispatch_list: list[tuple[str, str, dict, str, int]] = []

            for row in rows:
                run_id = row[0] if isinstance(row, (tuple, list)) else row["id"]
                workflow = row[1] if isinstance(row, (tuple, list)) else row["workflow"]
                params_raw = row[2] if isinstance(row, (tuple, list)) else row["params"]
                lane = row[3] if isinstance(row, (tuple, list)) else row["lane"]
                trigger_source = row[4] if isinstance(row, (tuple, list)) else row["trigger_source"]
                parent_id = row[5] if isinstance(row, (tuple, list)) else row["parent_execution_id"]
                idemp_key = row[6] if isinstance(row, (tuple, list)) else row["idempotency_key"]
                retry_count = row[7] if isinstance(row, (tuple, list)) else row["retry_count"]

                # Atomically claim — only transition if still pending
                cursor.execute(
                    "UPDATE core_executions "
                    "SET status = 'running', started_at = ? "
                    "WHERE id = ? AND status = 'pending'",
                    (_utcnow().isoformat(), run_id),
                )
                if cursor.rowcount == 0:
                    continue  # somebody else claimed it

                # Record started event
                cursor.execute(
                    "INSERT INTO core_execution_events "
                    "(id, execution_id, event_type, timestamp, data) "
                    "VALUES (?, ?, 'started', ?, ?)",
                    (
                        str(uuid.uuid4()),
                        run_id,
                        _utcnow().isoformat(),
                        json.dumps({"worker": self._worker_id}),
                    ),
                )
                self._conn.commit()
                claimed += 1

                # Parse params
                params: dict[str, Any] = {}
                if params_raw:
                    try:
                        params = json.loads(params_raw) if isinstance(params_raw, str) else params_raw
                    except (json.JSONDecodeError, TypeError):
                        params = {}

                dispatch_list.append((run_id, workflow or "", params, lane or "default", retry_count or 0))

        # Dispatch outside the DB lock
        for run_id, workflow, params, lane, retry_count in dispatch_list:
            with self._active_lock:
                self._active_run_ids.add(run_id)

            self._pool.submit(
                self._execute_run,
                run_id=run_id,
                workflow=workflow,
                params=params,
                lane=lane,
                retry_count=retry_count,
            )

        return claimed

    # ------------------------------------------------------------------ #
    # Execution
    # ------------------------------------------------------------------ #

    def _execute_run(
        self,
        run_id: str,
        workflow: str,
        params: dict[str, Any],
        lane: str,
        retry_count: int,
    ) -> None:
        """Execute a single run in a worker thread."""
        logger.info("Worker %s executing run %s (%s)", self._worker_id, run_id, workflow)
        self._stats.total_processed += 1

        try:
            # Determine kind — stored in workflow field as "kind:name"
            # or just workflow name (default to "task")
            if ":" in workflow:
                kind, name = workflow.split(":", 1)
            else:
                kind, name = "task", workflow

            # Look up handler
            handler = self._registry.get(kind, name)

            # Execute
            result = handler(params)

            # Mark completed
            self._mark_completed(run_id, result)
            self._stats.total_completed += 1
            logger.info("Worker %s run %s completed", self._worker_id, run_id)

        except ValueError as exc:
            # No handler registered — mark failed
            error_msg = str(exc)
            logger.warning("Worker %s run %s no handler: %s", self._worker_id, run_id, error_msg)
            self._mark_failed(run_id, error_msg)
            self._stats.total_failed += 1

        except Exception as exc:
            error_msg = f"{type(exc).__name__}: {exc}"
            logger.error("Worker %s run %s failed: %s", self._worker_id, run_id, error_msg)
            self._mark_failed(run_id, error_msg)
            self._stats.total_failed += 1

        finally:
            with self._active_lock:
                self._active_run_ids.discard(run_id)

    def _mark_completed(self, run_id: str, result: Any) -> None:
        """Transition run to completed status."""
        now = _utcnow().isoformat()
        result_json = None
        if result is not None:
            try:
                result_json = json.dumps(result) if not isinstance(result, str) else result
            except (TypeError, ValueError):
                result_json = json.dumps({"value": str(result)})

        with self._db_lock:
            cursor = self._conn.cursor()
            cursor.execute(
                "UPDATE core_executions "
                "SET status = 'completed', completed_at = ?, result = ? "
                "WHERE id = ?",
                (now, result_json, run_id),
            )
            cursor.execute(
                "INSERT INTO core_execution_events "
                "(id, execution_id, event_type, timestamp, data) "
                "VALUES (?, ?, 'completed', ?, ?)",
                (str(uuid.uuid4()), run_id, now, json.dumps({"result": result_json})),
            )
            self._conn.commit()

    def _mark_failed(self, run_id: str, error: str) -> None:
        """Transition run to failed status."""
        now = _utcnow().isoformat()
        with self._db_lock:
            cursor = self._conn.cursor()
            cursor.execute(
                "UPDATE core_executions "
                "SET status = 'failed', completed_at = ?, error = ? "
                "WHERE id = ?",
                (now, error, run_id),
            )
            cursor.execute(
                "INSERT INTO core_execution_events "
                "(id, execution_id, event_type, timestamp, data) "
                "VALUES (?, ?, 'failed', ?, ?)",
                (str(uuid.uuid4()), run_id, now, json.dumps({"error": error})),
            )
            self._conn.commit()

    # ------------------------------------------------------------------ #
    # Signal handling & cleanup
    # ------------------------------------------------------------------ #

    def _handle_signal(self, signum, frame):
        logger.info("Worker %s received signal %s — shutting down", self._worker_id, signum)
        self.stop()

    def _cleanup(self) -> None:
        """Clean up resources."""
        self.info.status = "stopped"

        with _workers_lock:
            _active_workers.pop(self._worker_id, None)

        self._pool.shutdown(wait=True, cancel_futures=False)

        if self._owns_conn:
            self._conn.close()

        logger.info("Worker %s stopped (processed=%d, failed=%d)",
                     self._worker_id, self._stats.total_processed, self._stats.total_failed)
