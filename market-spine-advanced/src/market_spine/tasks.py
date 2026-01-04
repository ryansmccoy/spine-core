"""Celery tasks for pipeline execution."""

import structlog

from market_spine.celery_app import celery_app
from market_spine.config import get_settings

logger = structlog.get_logger()


@celery_app.task(
    bind=True,
    name="market_spine.tasks.run_pipeline",
    max_retries=0,  # We handle retries via DLQ
    acks_late=True,
)
def run_pipeline_task(self, execution_id: str):
    """
    Celery task to execute a pipeline.

    This is the main entry point for async pipeline execution.
    """
    from market_spine.runner import run_pipeline
    from market_spine.orchestration.dlq import DLQManager
    from market_spine.db import get_connection

    log = logger.bind(execution_id=execution_id, task_id=self.request.id)
    log.info("celery_task_started")

    try:
        # Update status to running
        with get_connection() as conn:
            conn.execute(
                """
                UPDATE executions
                SET status = 'running', started_at = NOW()
                WHERE id = %s AND status = 'queued'
                """,
                (execution_id,),
            )
            conn.commit()

        # Run the pipeline
        result = run_pipeline(execution_id)

        log.info("celery_task_completed", result=result)
        return result

    except Exception as e:
        log.error("celery_task_failed", error=str(e))

        # Check if should move to DLQ
        with get_connection() as conn:
            result = conn.execute(
                "SELECT retry_count, max_retries FROM executions WHERE id = %s",
                (execution_id,),
            )
            row = result.fetchone()

            if row and row["retry_count"] >= row["max_retries"]:
                # Move to DLQ
                dlq = DLQManager()
                dlq.move_to_dlq(execution_id, str(e))

        raise


@celery_app.task(name="market_spine.tasks.check_scheduled_pipelines")
def check_scheduled_pipelines():
    """
    Check for scheduled pipelines that are due to run.

    This task runs periodically via Celery Beat.
    """
    from market_spine.orchestration.scheduler import ScheduleManager
    from market_spine.dispatcher import Dispatcher

    scheduler = ScheduleManager()
    dispatcher = Dispatcher()

    due_schedules = scheduler.get_due_schedules()

    if not due_schedules:
        return {"checked": 0, "triggered": 0}

    triggered = 0
    for schedule in due_schedules:
        try:
            # Submit the pipeline
            execution_id = dispatcher.submit(
                pipeline_name=schedule["pipeline_name"],
                params=schedule["params"],
                logical_key=f"schedule:{schedule['id']}",
            )

            # Mark as run
            scheduler.mark_run(schedule["id"])
            triggered += 1

            logger.info(
                "scheduled_pipeline_triggered",
                schedule_id=schedule["id"],
                schedule_name=schedule["name"],
                execution_id=execution_id,
            )

        except ValueError as e:
            # Likely logical key conflict - already running
            logger.warning(
                "scheduled_pipeline_skipped",
                schedule_id=schedule["id"],
                reason=str(e),
            )
        except Exception as e:
            logger.error(
                "scheduled_pipeline_error",
                schedule_id=schedule["id"],
                error=str(e),
            )

    return {"checked": len(due_schedules), "triggered": triggered}


@celery_app.task(name="market_spine.tasks.auto_retry_dlq")
def auto_retry_dlq():
    """
    Automatically retry eligible DLQ items.

    This task runs periodically via Celery Beat.
    """
    settings = get_settings()

    if not settings.scheduler_enabled:
        return {"skipped": True, "reason": "scheduler disabled"}

    from market_spine.orchestration.dlq import DLQManager
    from market_spine.dispatcher import Dispatcher

    dlq = DLQManager()
    dispatcher = Dispatcher()

    # Get retriable items
    dlq_items = dlq.list_dlq(limit=100)
    retriable = [item for item in dlq_items if item["retry_count"] < item["max_retries"]]

    if not retriable:
        return {"checked": len(dlq_items), "retried": 0}

    retried = 0
    for item in retriable:
        new_id = dlq.retry(item["id"])
        if new_id:
            # Submit the new execution
            dispatcher.submit(item["pipeline_name"], item["params"])
            retried += 1

    logger.info("auto_retry_dlq_complete", checked=len(dlq_items), retried=retried)
    return {"checked": len(dlq_items), "retried": retried}
