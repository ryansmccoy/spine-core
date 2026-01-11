"""LocalBackend - Thread-based execution backend."""

import threading
import time
from concurrent.futures import ThreadPoolExecutor, Future
from typing import Callable

import structlog

from market_spine.config import get_settings
from market_spine.db import get_connection
from market_spine.repositories.executions import ExecutionRepository

logger = structlog.get_logger()


class LocalBackend:
    """
    Local thread-based backend for pipeline execution.

    Uses a background thread to poll for pending executions and
    a thread pool to execute them concurrently.
    """

    name = "local"

    def __init__(
        self,
        poll_interval: float | None = None,
        max_concurrent: int | None = None,
        run_pipeline_fn: Callable[[str], None] | None = None,
    ):
        settings = get_settings()
        self.poll_interval = poll_interval or settings.worker_poll_interval
        self.max_concurrent = max_concurrent or settings.worker_max_concurrent

        self._run_pipeline_fn = run_pipeline_fn

        self._running = False
        self._poll_thread: threading.Thread | None = None
        self._executor: ThreadPoolExecutor | None = None
        self._active_futures: dict[str, Future] = {}
        self._lock = threading.Lock()

    def _get_run_pipeline(self) -> Callable[[str], None]:
        """Get the run_pipeline function."""
        if self._run_pipeline_fn:
            return self._run_pipeline_fn
        from market_spine.pipelines.runner import PipelineRunner

        def run_pipeline(execution_id: str) -> None:
            """Run a pipeline given an execution ID."""
            # Get execution details from DB
            exec_repo = ExecutionRepository()
            execution = exec_repo.get(execution_id)
            if execution:
                PipelineRunner.run(
                    execution_id=execution_id,
                    pipeline_name=execution["pipeline_name"],
                    params=execution.get("params"),
                )

        return run_pipeline

    def start(self) -> None:
        """Start the backend polling loop."""
        if self._running:
            logger.warning("backend_already_running")
            return

        logger.info(
            "backend_starting",
            backend=self.name,
            poll_interval=self.poll_interval,
            max_concurrent=self.max_concurrent,
        )

        self._running = True
        self._executor = ThreadPoolExecutor(max_workers=self.max_concurrent)
        self._poll_thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._poll_thread.start()

    def stop(self) -> None:
        """Stop the backend gracefully."""
        if not self._running:
            return

        logger.info("backend_stopping")
        self._running = False

        if self._poll_thread:
            self._poll_thread.join(timeout=5.0)

        if self._executor:
            self._executor.shutdown(wait=True, cancel_futures=False)

        logger.info("backend_stopped")

    def submit(
        self, execution_id: str, pipeline_name: str | None = None, params: dict | None = None
    ) -> str | None:
        """
        Submit an execution for processing.

        In synchronous mode (no poll loop running), runs immediately.
        In async mode (poll loop running), queues for background processing.
        """
        with get_connection() as conn:
            # Update backend info
            conn.execute(
                """
                UPDATE executions 
                SET backend = %s, backend_run_id = %s
                WHERE id = %s
                """,
                (self.name, execution_id, execution_id),
            )
            conn.commit()

        # If not running the poll loop, run immediately (synchronous mode)
        if not self._running:
            self._run_immediately(execution_id)
        else:
            # Queue for background processing
            with get_connection() as conn:
                conn.execute(
                    """
                    UPDATE executions 
                    SET status = 'queued'
                    WHERE id = %s AND status = 'pending'
                    """,
                    (execution_id,),
                )
                conn.commit()
            logger.debug("execution_queued", execution_id=execution_id)

        return execution_id

    def _run_immediately(self, execution_id: str) -> None:
        """Run a pipeline execution immediately (synchronous)."""
        run_pipeline = self._get_run_pipeline()

        with get_connection() as conn:
            conn.execute(
                """
                UPDATE executions 
                SET status = 'running', started_at = NOW()
                WHERE id = %s
                """,
                (execution_id,),
            )
            conn.commit()

        try:
            run_pipeline(execution_id)

            with get_connection() as conn:
                conn.execute(
                    """
                    UPDATE executions 
                    SET status = 'completed', completed_at = NOW()
                    WHERE id = %s
                    """,
                    (execution_id,),
                )
                conn.commit()

            logger.info("execution_completed", execution_id=execution_id)
        except Exception as e:
            with get_connection() as conn:
                conn.execute(
                    """
                    UPDATE executions 
                    SET status = 'failed', completed_at = NOW(), error_message = %s
                    WHERE id = %s
                    """,
                    (str(e), execution_id),
                )
                conn.commit()

            logger.error("execution_failed", execution_id=execution_id, error=str(e))

    def cancel(self, execution_id: str) -> bool:
        """Request cancellation of an execution."""
        with get_connection() as conn:
            result = conn.execute(
                """
                UPDATE executions 
                SET status = 'cancelled', completed_at = NOW()
                WHERE id = %s AND status IN ('pending', 'queued')
                RETURNING id
                """,
                (execution_id,),
            )
            if result.fetchone():
                conn.commit()
                logger.info("execution_cancelled", execution_id=execution_id)
                return True
        return False

    def health(self) -> dict:
        """Check backend health."""
        active_count = len(self._active_futures)
        return {
            "healthy": self._running,
            "message": "running" if self._running else "stopped",
            "active_executions": active_count,
            "max_concurrent": self.max_concurrent,
        }

    def _poll_loop(self) -> None:
        """Background loop that polls for and processes executions."""
        logger.info("poll_loop_started")

        while self._running:
            try:
                self._cleanup_completed_futures()

                with self._lock:
                    available_slots = self.max_concurrent - len(self._active_futures)

                if available_slots > 0:
                    self._claim_and_process(available_slots)

            except Exception as e:
                logger.error("poll_loop_error", error=str(e))

            time.sleep(self.poll_interval)

        logger.info("poll_loop_stopped")

    def _cleanup_completed_futures(self) -> None:
        """Remove completed futures from tracking."""
        with self._lock:
            completed = [
                exec_id for exec_id, future in self._active_futures.items() if future.done()
            ]
            for exec_id in completed:
                future = self._active_futures.pop(exec_id)
                try:
                    future.result()
                except Exception as e:
                    logger.error("execution_future_error", execution_id=exec_id, error=str(e))

    def _claim_and_process(self, limit: int) -> None:
        """Claim queued executions and submit them for processing."""
        with get_connection() as conn:
            result = conn.execute(
                """
                SELECT id FROM executions
                WHERE status = 'queued' AND backend = %s
                ORDER BY created_at
                LIMIT %s
                FOR UPDATE SKIP LOCKED
                """,
                (self.name, limit),
            )
            rows = result.fetchall()

            if not rows:
                return

            execution_ids = [row["id"] for row in rows]

            for exec_id in execution_ids:
                conn.execute(
                    """
                    UPDATE executions 
                    SET status = 'running', started_at = NOW()
                    WHERE id = %s
                    """,
                    (exec_id,),
                )

            conn.commit()

        run_pipeline = self._get_run_pipeline()
        with self._lock:
            for exec_id in execution_ids:
                logger.info("submitting_execution", execution_id=exec_id)
                future = self._executor.submit(run_pipeline, exec_id)
                self._active_futures[exec_id] = future
