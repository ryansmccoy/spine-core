"""Configuration management using Pydantic Settings."""

from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_prefix="",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database
    database_url: str = "postgresql://spine:spine_dev@localhost:5432/market_spine"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Backend
    backend_type: Literal["local", "celery"] = "celery"

    # Worker (Local backend)
    worker_poll_interval: float = 0.5
    worker_max_concurrent: int = 4

    # Celery
    celery_broker_url: str | None = None  # If set, uses Celery backend
    celery_task_default_queue: str = "market_spine"
    celery_task_acks_late: bool = True
    celery_worker_prefetch_multiplier: int = 1

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # Storage
    storage_type: Literal["local", "s3"] = "local"
    storage_local_path: str = "./data"
    storage_s3_bucket: str = "market-spine-data"
    storage_s3_endpoint: str | None = None  # For MinIO or localstack
    storage_s3_region: str = "us-east-1"
    storage_s3_access_key: str | None = None
    storage_s3_secret_key: str | None = None

    # External APIs
    otc_api_base_url: str = "https://api.example.com/otc"
    otc_api_key: str | None = None
    otc_api_timeout: int = 30

    # DLQ
    dlq_max_retries: int = 3
    dlq_retry_delay_seconds: int = 300  # 5 minutes

    # Scheduling
    scheduler_enabled: bool = True

    # Logging
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_format: Literal["json", "console"] = "console"


# Global settings instance
_settings: Settings | None = None


def get_settings() -> Settings:
    """Get or create settings instance."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reset_settings() -> None:
    """Reset settings (for testing)."""
    global _settings
    _settings = None
