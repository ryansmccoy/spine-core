"""Application settings with Pydantic."""

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database
    database_url: str = "postgresql://spine:spine@localhost:5432/spine"
    db_pool_min_size: int = 2
    db_pool_max_size: int = 10

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Celery
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_reload: bool = False

    # Execution
    max_retries: int = 3
    retry_delay_seconds: int = 60
    execution_timeout_seconds: int = 3600

    # Observability
    log_level: str = "INFO"
    log_format: str = "json"  # json or console
    metrics_enabled: bool = True
    tracing_enabled: bool = False
    otlp_endpoint: str = "http://localhost:4317"

    # Storage
    storage_backend: str = "local"  # local or s3
    storage_local_path: str = "./data/storage"
    storage_s3_bucket: str = ""
    storage_s3_prefix: str = "market-spine/"

    # External API
    external_api_base_url: str = ""
    external_api_timeout: float = 30.0
    external_api_retries: int = 3

    # Retention
    retention_days: int = 90
    cleanup_batch_size: int = 1000

    # Scheduling
    schedule_ingest_enabled: bool = True
    schedule_ingest_interval_seconds: int = 60
    schedule_cleanup_enabled: bool = True
    schedule_cleanup_cron: str = "0 2 * * *"  # 2 AM daily

    @property
    def database_host(self) -> str:
        """Extract host from database URL."""
        # postgresql://user:pass@host:port/db
        parts = self.database_url.split("@")
        if len(parts) > 1:
            host_port = parts[1].split("/")[0]
            return host_port.split(":")[0]
        return "localhost"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
