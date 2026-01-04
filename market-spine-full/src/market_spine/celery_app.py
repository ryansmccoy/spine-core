"""Celery application configuration."""

from celery import Celery
from celery.schedules import crontab

from market_spine.core.settings import get_settings
from market_spine.observability.tracing import instrument_celery

settings = get_settings()

# Create Celery app
celery_app = Celery(
    "market_spine",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

# Configure Celery
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=settings.execution_timeout_seconds,
    task_soft_time_limit=settings.execution_timeout_seconds - 60,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    # Default queue
    task_default_queue="default",
    # Task routes
    task_routes={
        "market_spine.celery_app.run_pipeline_task": {"queue": "default"},
        "market_spine.celery_app.cleanup_task": {"queue": "maintenance"},
    },
)

# Configure Beat schedule
celery_app.conf.beat_schedule = {}

if settings.schedule_ingest_enabled:
    celery_app.conf.beat_schedule["scheduled-ingest"] = {
        "task": "market_spine.celery_app.scheduled_ingest_task",
        "schedule": settings.schedule_ingest_interval_seconds,
        "options": {"queue": "default"},
    }

if settings.schedule_cleanup_enabled:
    # Parse cron expression
    parts = settings.schedule_cleanup_cron.split()
    if len(parts) == 5:
        celery_app.conf.beat_schedule["scheduled-cleanup"] = {
            "task": "market_spine.celery_app.cleanup_task",
            "schedule": crontab(
                minute=parts[0],
                hour=parts[1],
                day_of_month=parts[2],
                month_of_year=parts[3],
                day_of_week=parts[4],
            ),
            "options": {"queue": "maintenance"},
        }

# Instrument with OpenTelemetry
instrument_celery()


@celery_app.task(name="market_spine.celery_app.run_pipeline_task", bind=True)
def run_pipeline_task(self, execution_id: str) -> dict:
    """
    Celery task that runs a pipeline.

    This is the ONLY Celery task that runs pipeline logic.
    All pipelines go through run_pipeline(execution_id).
    """
    from market_spine.pipelines.runner import run_pipeline
    from market_spine.observability.logging import get_logger

    logger = get_logger(__name__)
    logger.info(
        "celery_task_started",
        execution_id=execution_id,
        task_id=self.request.id,
    )

    result = run_pipeline(execution_id)

    logger.info(
        "celery_task_completed",
        execution_id=execution_id,
        result=result,
    )

    return result


@celery_app.task(name="market_spine.celery_app.scheduled_ingest_task")
def scheduled_ingest_task() -> dict:
    """Scheduled task for periodic OTC ingestion."""
    from market_spine.core.models import TriggerSource
    from market_spine.execution.ledger import ExecutionLedger
    from market_spine.execution.dispatcher import Dispatcher
    from market_spine.backends.celery_backend import CeleryBackend
    from market_spine.observability.logging import get_logger

    logger = get_logger(__name__)
    logger.info("scheduled_ingest_starting")

    ledger = ExecutionLedger()
    backend = CeleryBackend()
    dispatcher = Dispatcher(ledger, backend)

    execution = dispatcher.submit(
        pipeline="otc_full_etl",
        params={"source": "synthetic", "count": 20},
        trigger_source=TriggerSource.SCHEDULE,
    )

    logger.info(
        "scheduled_ingest_submitted",
        execution_id=execution.id,
    )

    return {"execution_id": execution.id}


@celery_app.task(name="market_spine.celery_app.cleanup_task")
def cleanup_task() -> dict:
    """Scheduled task for cleanup of old data."""
    from market_spine.repositories.execution import ExecutionRepository
    from market_spine.observability.logging import get_logger

    logger = get_logger(__name__)
    logger.info("cleanup_task_starting")

    settings = get_settings()
    repo = ExecutionRepository()

    # Clean old executions
    executions_deleted = repo.cleanup_old_executions(days=settings.retention_days)
    dead_letters_deleted = repo.cleanup_old_dead_letters(days=settings.retention_days)

    logger.info(
        "cleanup_task_completed",
        executions_deleted=executions_deleted,
        dead_letters_deleted=dead_letters_deleted,
    )

    return {
        "executions_deleted": executions_deleted,
        "dead_letters_deleted": dead_letters_deleted,
    }


@celery_app.task(name="market_spine.celery_app.retry_dead_letter_task")
def retry_dead_letter_task(dlq_id: str) -> dict:
    """Retry a dead letter entry (creates NEW execution)."""
    from market_spine.core.models import TriggerSource
    from market_spine.execution.ledger import ExecutionLedger
    from market_spine.execution.dlq import DLQManager
    from market_spine.execution.dispatcher import Dispatcher
    from market_spine.backends.celery_backend import CeleryBackend
    from market_spine.observability.logging import get_logger
    from market_spine.observability.metrics import dead_letters_retried_counter

    logger = get_logger(__name__)

    dlq = DLQManager()
    retry_info = dlq.prepare_retry(dlq_id)

    if retry_info is None:
        logger.warning("dlq_retry_not_possible", dlq_id=dlq_id)
        return {"error": "Cannot retry dead letter"}

    pipeline, params, parent_execution_id = retry_info

    ledger = ExecutionLedger()
    backend = CeleryBackend()
    dispatcher = Dispatcher(ledger, backend)

    execution = dispatcher.submit(
        pipeline=pipeline,
        params=params,
        trigger_source=TriggerSource.RETRY,
        parent_execution_id=parent_execution_id,
    )

    # Mark DLQ as resolved
    dlq.resolve(dlq_id, resolved_by=f"retry:{execution.id}")
    dead_letters_retried_counter.labels(pipeline=pipeline).inc()

    logger.info(
        "dlq_retry_submitted",
        dlq_id=dlq_id,
        new_execution_id=execution.id,
    )

    return {
        "dlq_id": dlq_id,
        "new_execution_id": execution.id,
    }
