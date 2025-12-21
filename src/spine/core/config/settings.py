"""
Centralized settings for spine-core.

Manifesto:
    One validated, cached settings object replaces the ad-hoc per-module
    settings classes that each parsed the same environment variables
    differently.  ``SpineCoreSettings`` cooperates with the env-file
    loader and TOML profiles to resolve values in a single place.

:class:`SpineCoreSettings` replaces the ad-hoc per-module settings
classes with a single, validated, cached source of truth.  It
cooperates with the :mod:`~spine.core.config.loader` (env-file
cascade) and :mod:`~spine.core.config.profiles` (TOML profiles) to
resolve values.

Tags:
    spine-core, configuration, settings, pydantic, caching, validation

Doc-Types:
    api-reference
"""

from __future__ import annotations

import os
from pathlib import Path

try:
    from pydantic_settings import BaseSettings, SettingsConfigDict
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "spine.core.config.settings requires pydantic-settings. "
        "Install it with: pip install spine-core[settings]"
    ) from exc

from pydantic import Field, model_validator

from .components import (
    CacheBackend,
    ComponentWarning,
    DatabaseBackend,
    EventBackend,
    MetricsBackend,
    SchedulerBackend,
    TracingBackend,
    WorkerBackend,
    validate_component_combination,
)


class SpineCoreSettings(BaseSettings):
    """Spine-core centralized configuration.

    All fields can be set via ``SPINE_*`` environment variables (e.g.
    ``SPINE_DATABASE_BACKEND=postgres``) or through ``.env`` files and
    TOML profiles.
    """

    model_config = SettingsConfigDict(
        env_prefix="SPINE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_nested_delimiter="__",
    )

    # ── Meta ─────────────────────────────────────────────────────
    tier: str = Field(default="", description="Deployment tier (minimal/standard/full/custom)")

    # ── Component backends ───────────────────────────────────────
    database_backend: DatabaseBackend = Field(default=DatabaseBackend.SQLITE)
    scheduler_backend: SchedulerBackend = Field(default=SchedulerBackend.THREAD)
    cache_backend: CacheBackend = Field(default=CacheBackend.NONE)
    worker_backend: WorkerBackend = Field(default=WorkerBackend.INPROCESS)
    metrics_backend: MetricsBackend = Field(default=MetricsBackend.NONE)
    tracing_backend: TracingBackend = Field(default=TracingBackend.NONE)
    event_backend: EventBackend = Field(default=EventBackend.MEMORY)

    # ── Database ─────────────────────────────────────────────────
    database_url: str = Field(default="sqlite:///data/spine.db")
    database_pool_size: int = Field(default=5)
    database_max_overflow: int = Field(default=10)
    database_echo: bool = Field(default=False)

    # ── Redis ────────────────────────────────────────────────────
    redis_url: str = Field(default="redis://localhost:10379/0")
    redis_max_connections: int = Field(default=10)

    # ── Events ───────────────────────────────────────────────────
    event_redis_url: str = Field(
        default="redis://localhost:10379/3",
        description="Redis URL for event bus (if event_backend=redis)",
    )

    # ── Celery ───────────────────────────────────────────────────
    celery_broker_url: str = Field(default="redis://localhost:10379/1")
    celery_result_backend: str = Field(default="redis://localhost:10379/2")
    celery_worker_concurrency: int = Field(default=4)

    # ── Scheduler ────────────────────────────────────────────────
    scheduler_interval_seconds: int = Field(default=10)
    scheduler_misfire_grace_seconds: int = Field(default=60)

    # ── API ──────────────────────────────────────────────────────
    api_host: str = Field(default="0.0.0.0")
    api_port: int = Field(default=12000, description="Bind port (spine-core block: 12000-12099)")
    api_prefix: str = Field(default="/api/v1")
    api_reload: bool = Field(default=False)
    api_workers: int = Field(default=1)

    # ── CORS ─────────────────────────────────────────────────────
    cors_origins: list[str] = Field(default=["http://localhost:3000", "http://localhost:5173", "http://localhost:12000"])

    # ── Rate limiting ────────────────────────────────────────────
    rate_limit_enabled: bool = Field(default=False)
    rate_limit_rpm: int = Field(default=120)

    # ── Logging ──────────────────────────────────────────────────
    log_level: str = Field(default="INFO")
    log_format: str = Field(default="json")

    # ── Metrics / Tracing ────────────────────────────────────────
    metrics_port: int = Field(default=9090)
    otel_endpoint: str = Field(default="http://localhost:4317")
    otel_service_name: str = Field(default="spine-core")

    # ── Feature flags ────────────────────────────────────────────
    enable_dlq: bool = Field(default=True)
    enable_quality_checks: bool = Field(default=True)
    enable_anomaly_detection: bool = Field(default=True)

    # ── Paths ────────────────────────────────────────────────────
    data_dir: str = Field(default="data")
    log_dir: str = Field(default="logs")

    # ── Computed ─────────────────────────────────────────────────
    component_warnings: list[ComponentWarning] = Field(default_factory=list, exclude=True)

    @model_validator(mode="after")
    def _validate_components(self) -> SpineCoreSettings:
        """Run component-combination validation after all fields are set."""
        try:
            warnings = validate_component_combination(
                database=self.database_backend,
                scheduler=self.scheduler_backend,
                cache=self.cache_backend,
                worker=self.worker_backend,
                metrics=self.metrics_backend,
                tracing=self.tracing_backend,
            )
        except ValueError:
            raise  # propagate error-severity issues
        object.__setattr__(self, "component_warnings", warnings)
        return self

    # ── Derived properties ───────────────────────────────────────

    @property
    def requires_redis(self) -> bool:
        return self.cache_backend == CacheBackend.REDIS or self.worker_backend in (
            WorkerBackend.CELERY,
            WorkerBackend.RQ,
        )

    @property
    def requires_postgres(self) -> bool:
        return self.database_backend in (DatabaseBackend.POSTGRES, DatabaseBackend.TIMESCALE)

    @property
    def is_sqlite(self) -> bool:
        return self.database_backend == DatabaseBackend.SQLITE

    def infer_tier(self) -> str:
        """Infer the deployment tier from the chosen components."""
        if self.tier:
            return self.tier
        if self.database_backend == DatabaseBackend.TIMESCALE or self.worker_backend == WorkerBackend.CELERY:
            return "full"
        if self.database_backend == DatabaseBackend.POSTGRES:
            return "standard"
        return "minimal"


# ── Settings factory with caching ────────────────────────────────────────

_settings_cache: dict[str, SpineCoreSettings] = {}


def get_settings(
    *,
    profile: str | None = None,
    tier: str | None = None,
    project_root: Path | None = None,
    _force_reload: bool = False,
) -> SpineCoreSettings:
    """Load, validate, and cache a :class:`SpineCoreSettings` instance.

    Parameters
    ----------
    profile:
        Profile name to apply.  Overrides the active profile.
    tier:
        Explicit tier.  Overrides ``SPINE_TIER``.
    project_root:
        Override the auto-detected project root.
    _force_reload:
        Bypass cache and reload from disk.
    """
    from .loader import discover_env_files, find_project_root

    root = (project_root or find_project_root()).resolve()
    cache_key = f"{root}:{tier or ''}:{profile or ''}"

    if not _force_reload and cache_key in _settings_cache:
        return _settings_cache[cache_key]

    # Resolve profile env vars
    profile_env: dict[str, str] = {}
    active_profile: str | None = profile

    if not active_profile:
        from .profiles import ProfileManager

        manager = ProfileManager(project_root=root)
        if active := manager.get_active_profile():
            profile_env = manager.resolve_profile(active)
            active_profile = active
    elif active_profile:
        from .profiles import ProfileManager

        manager = ProfileManager(project_root=root)
        profile_env = manager.resolve_profile(active_profile)

    # Inject profile env into os.environ temporarily
    # (Pydantic will read from env during init)
    original_env: dict[str, str | None] = {}
    for key, value in profile_env.items():
        if key not in os.environ:  # Don't override explicit env vars
            original_env[key] = os.environ.get(key)
            os.environ[key] = value

    try:
        # Discover env files
        env_files = discover_env_files(root, tier)

        # Create settings with discovered env files
        settings = SpineCoreSettings(
            _env_file=env_files,  # type: ignore[call-arg]
        )

        # Store metadata (bypass frozen model if needed)
        object.__setattr__(settings, "_project_root", root)
        object.__setattr__(settings, "_env_files_loaded", env_files)
        object.__setattr__(settings, "_active_profile", active_profile)
    finally:
        # Restore original environment
        for key, orig_value in original_env.items():
            if orig_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = orig_value

    _settings_cache[cache_key] = settings
    return settings


def clear_settings_cache() -> None:
    """Clear the settings cache (primarily for testing)."""
    _settings_cache.clear()
