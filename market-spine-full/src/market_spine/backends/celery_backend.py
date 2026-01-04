"""Celery backend for distributed task execution."""

from market_spine.observability.logging import get_logger

logger = get_logger(__name__)


class CeleryBackend:
    """Celery-based execution backend."""

    def submit(self, execution_id: str, pipeline: str, lane: str) -> None:
        """Submit an execution to Celery."""
        # Import here to avoid circular imports
        from market_spine.celery_app import run_pipeline_task

        # Submit task to Celery
        run_pipeline_task.apply_async(
            args=[execution_id],
            queue=lane,
            task_id=f"execution-{execution_id}",
        )
        logger.info(
            "celery_task_submitted",
            execution_id=execution_id,
            pipeline=pipeline,
            queue=lane,
        )

    def cancel(self, execution_id: str) -> bool:
        """Cancel a Celery task."""
        from market_spine.celery_app import celery_app

        try:
            celery_app.control.revoke(
                f"execution-{execution_id}",
                terminate=True,
                signal="SIGTERM",
            )
            logger.info("celery_task_cancelled", execution_id=execution_id)
            return True
        except Exception as e:
            logger.error(
                "celery_task_cancel_failed",
                execution_id=execution_id,
                error=str(e),
            )
            return False
