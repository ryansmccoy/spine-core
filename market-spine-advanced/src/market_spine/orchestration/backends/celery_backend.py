"""CeleryBackend - Distributed task execution backend."""

import structlog

from market_spine.config import get_settings
from market_spine.db import get_connection

logger = structlog.get_logger()


class CeleryBackend:
    """
    Celery-based backend for distributed pipeline execution.

    Uses Celery tasks to execute pipelines across multiple workers.
    Supports task cancellation via revoke.
    """

    name = "celery"

    def __init__(self):
        self._celery_app = None

    def _get_celery_app(self):
        """Get or create Celery app."""
        if self._celery_app is None:
            from market_spine.celery_app import celery_app

            self._celery_app = celery_app
        return self._celery_app

    def start(self) -> None:
        """
        Start the backend.

        For Celery, this is a no-op as workers are started separately.
        """
        logger.info("celery_backend_initialized")

    def stop(self) -> None:
        """Stop the backend."""
        logger.info("celery_backend_stopped")

    def submit(self, execution_id: str) -> str | None:
        """
        Submit an execution to Celery.

        Creates a Celery task and returns the task ID.
        """
        from market_spine.tasks import run_pipeline_task

        # Update execution status
        with get_connection() as conn:
            conn.execute(
                """
                UPDATE executions 
                SET status = 'queued', backend = %s
                WHERE id = %s AND status = 'pending'
                """,
                (self.name, execution_id),
            )
            conn.commit()

        # Submit to Celery
        task = run_pipeline_task.delay(execution_id)

        # Store task ID
        with get_connection() as conn:
            conn.execute(
                """
                UPDATE executions 
                SET backend_run_id = %s
                WHERE id = %s
                """,
                (task.id, execution_id),
            )
            conn.commit()

        logger.info(
            "execution_submitted_to_celery",
            execution_id=execution_id,
            task_id=task.id,
        )

        return task.id

    def cancel(self, execution_id: str) -> bool:
        """
        Cancel an execution.

        For pending/queued: marks as cancelled
        For running: revokes the Celery task
        """
        with get_connection() as conn:
            # Check current status
            result = conn.execute(
                "SELECT status, backend_run_id FROM executions WHERE id = %s",
                (execution_id,),
            )
            row = result.fetchone()

            if not row:
                return False

            status = row["status"]
            task_id = row["backend_run_id"]

            if status in ("pending", "queued"):
                # Can cancel directly
                conn.execute(
                    """
                    UPDATE executions 
                    SET status = 'cancelled', completed_at = NOW()
                    WHERE id = %s
                    """,
                    (execution_id,),
                )
                conn.commit()
                logger.info("execution_cancelled", execution_id=execution_id)
                return True

            elif status == "running" and task_id:
                # Revoke the Celery task
                celery_app = self._get_celery_app()
                celery_app.control.revoke(task_id, terminate=True)

                # Note: Celery revoke is best-effort
                logger.warning(
                    "execution_revoke_requested",
                    execution_id=execution_id,
                    task_id=task_id,
                )
                return True

        return False

    def health(self) -> dict:
        """Check Celery backend health."""
        try:
            celery_app = self._get_celery_app()

            # Ping workers
            inspect = celery_app.control.inspect()
            stats = inspect.stats()

            if stats:
                worker_count = len(stats)
                return {
                    "healthy": True,
                    "message": f"{worker_count} workers available",
                    "workers": list(stats.keys()),
                }
            else:
                return {
                    "healthy": False,
                    "message": "No workers available",
                    "workers": [],
                }
        except Exception as e:
            return {
                "healthy": False,
                "message": f"Health check failed: {str(e)}",
                "workers": [],
            }

    def get_task_status(self, task_id: str) -> dict:
        """Get status of a Celery task."""
        celery_app = self._get_celery_app()
        result = celery_app.AsyncResult(task_id)

        return {
            "task_id": task_id,
            "status": result.status,
            "ready": result.ready(),
            "successful": result.successful() if result.ready() else None,
            "result": result.result if result.ready() and result.successful() else None,
        }
