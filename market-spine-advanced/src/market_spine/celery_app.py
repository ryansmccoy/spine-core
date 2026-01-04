"""Celery application configuration."""

from celery import Celery
from celery.schedules import crontab

from market_spine.config import get_settings

settings = get_settings()

# Create Celery app
celery_app = Celery(
    "market_spine",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["market_spine.tasks"],
)

# Configure Celery
celery_app.conf.update(
    # Task settings
    task_default_queue=settings.celery_task_default_queue,
    task_acks_late=settings.celery_task_acks_late,
    worker_prefetch_multiplier=settings.celery_worker_prefetch_multiplier,
    # Serialization
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    # Time settings
    timezone="UTC",
    enable_utc=True,
    # Result backend
    result_expires=86400,  # 24 hours
    # Task tracking
    task_track_started=True,
    task_send_sent_event=True,
)

# Beat schedule for periodic tasks
# These are defaults - actual schedules come from database
celery_app.conf.beat_schedule = {
    # Example: Check for scheduled pipelines every minute
    "check-scheduled-pipelines": {
        "task": "market_spine.tasks.check_scheduled_pipelines",
        "schedule": 60.0,  # Every 60 seconds
    },
    # Example: Auto-retry DLQ items
    "auto-retry-dlq": {
        "task": "market_spine.tasks.auto_retry_dlq",
        "schedule": crontab(minute="*/15"),  # Every 15 minutes
    },
}
