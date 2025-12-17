"""Tests for spine.core.config.settings — SpineCoreSettings + get_settings."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from spine.core.config.components import (
    CacheBackend,
    DatabaseBackend,
    MetricsBackend,
    SchedulerBackend,
    TracingBackend,
    WorkerBackend,
)
from spine.core.config.settings import (
    SpineCoreSettings,
    clear_settings_cache,
    get_settings,
)


@pytest.fixture(autouse=True)
def _clear_cache():
    """Clear settings cache before and after each test."""
    clear_settings_cache()
    yield
    clear_settings_cache()


# ── SpineCoreSettings defaults ───────────────────────────────────────────


class TestDefaults:
    def test_default_database_backend(self):
        s = SpineCoreSettings()
        assert s.database_backend == DatabaseBackend.SQLITE

    def test_default_scheduler_backend(self):
        s = SpineCoreSettings()
        assert s.scheduler_backend == SchedulerBackend.THREAD

    def test_default_cache_backend(self):
        s = SpineCoreSettings()
        assert s.cache_backend == CacheBackend.NONE

    def test_default_worker_backend(self):
        s = SpineCoreSettings()
        assert s.worker_backend == WorkerBackend.INPROCESS

    def test_default_metrics_backend(self):
        s = SpineCoreSettings()
        assert s.metrics_backend == MetricsBackend.NONE

    def test_default_tracing_backend(self):
        s = SpineCoreSettings()
        assert s.tracing_backend == TracingBackend.NONE

    def test_default_api_port(self):
        s = SpineCoreSettings()
        assert s.api_port == 12000

    def test_default_log_level(self):
        s = SpineCoreSettings()
        assert s.log_level == "INFO"

    def test_default_feature_flags(self):
        s = SpineCoreSettings()
        assert s.enable_dlq is True
        assert s.enable_quality_checks is True
        assert s.enable_anomaly_detection is True


# ── Environment variable override ────────────────────────────────────────


class TestEnvOverride:
    def test_env_overrides_database_backend(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("SPINE_DATABASE_BACKEND", "postgres")
        s = SpineCoreSettings()
        assert s.database_backend == DatabaseBackend.POSTGRES

    def test_env_overrides_api_port(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("SPINE_API_PORT", "9999")
        s = SpineCoreSettings()
        assert s.api_port == 9999

    def test_env_overrides_cors_origins(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("SPINE_CORS_ORIGINS", '["http://localhost:3000"]')
        s = SpineCoreSettings()
        assert s.cors_origins == ["http://localhost:3000"]


# ── Component validation ────────────────────────────────────────────────


class TestComponentValidation:
    def test_valid_minimal(self):
        """Minimal combo → no warnings."""
        s = SpineCoreSettings()
        assert s.component_warnings == []

    def test_sqlite_celery_warns(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("SPINE_DATABASE_BACKEND", "sqlite")
        monkeypatch.setenv("SPINE_WORKER_BACKEND", "celery")
        monkeypatch.setenv("SPINE_CACHE_BACKEND", "redis")
        s = SpineCoreSettings()
        assert any("WAL-lock" in w.message for w in s.component_warnings)

    def test_celery_beat_no_redis_raises(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("SPINE_SCHEDULER_BACKEND", "celery_beat")
        monkeypatch.setenv("SPINE_CACHE_BACKEND", "none")
        with pytest.raises(ValueError, match="Celery Beat"):
            SpineCoreSettings()


# ── Derived properties ──────────────────────────────────────────────────


class TestDerivedProperties:
    def test_requires_redis_celery(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("SPINE_WORKER_BACKEND", "celery")
        monkeypatch.setenv("SPINE_CACHE_BACKEND", "redis")
        s = SpineCoreSettings()
        assert s.requires_redis is True

    def test_requires_redis_rq(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("SPINE_WORKER_BACKEND", "rq")
        monkeypatch.setenv("SPINE_CACHE_BACKEND", "redis")
        s = SpineCoreSettings()
        assert s.requires_redis is True

    def test_requires_postgres(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("SPINE_DATABASE_BACKEND", "postgres")
        s = SpineCoreSettings()
        assert s.requires_postgres is True

    def test_is_sqlite(self):
        s = SpineCoreSettings()
        assert s.is_sqlite is True

    def test_infer_tier_minimal(self):
        s = SpineCoreSettings()
        assert s.infer_tier() == "minimal"

    def test_infer_tier_standard(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("SPINE_DATABASE_BACKEND", "postgres")
        s = SpineCoreSettings()
        assert s.infer_tier() == "standard"

    def test_infer_tier_full(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("SPINE_DATABASE_BACKEND", "timescale")
        s = SpineCoreSettings()
        assert s.infer_tier() == "full"

    def test_infer_tier_explicit(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("SPINE_TIER", "custom")
        s = SpineCoreSettings()
        assert s.infer_tier() == "custom"


# ── get_settings factory ────────────────────────────────────────────────


class TestGetSettings:
    def test_caching(self, tmp_path: Path):
        """Same call returns cached instance."""
        s1 = get_settings(project_root=tmp_path)
        s2 = get_settings(project_root=tmp_path)
        assert s1 is s2

    def test_force_reload(self, tmp_path: Path):
        """_force_reload bypasses cache."""
        s1 = get_settings(project_root=tmp_path)
        s2 = get_settings(project_root=tmp_path, _force_reload=True)
        assert s1 is not s2

    def test_tier_parameter(self, tmp_path: Path):
        """Tier parameter changes cache key."""
        s1 = get_settings(project_root=tmp_path)
        s2 = get_settings(project_root=tmp_path, tier="standard")
        # Different cache keys → different instances
        assert s1 is not s2

    def test_loads_env_files(self, tmp_path: Path):
        """get_settings discovers and loads .env files."""
        (tmp_path / "pyproject.toml").touch()
        (tmp_path / ".env.base").write_text("SPINE_LOG_LEVEL=WARNING\n")
        s = get_settings(project_root=tmp_path)
        assert s.log_level == "WARNING"

    def test_profile_applied(self, tmp_path: Path):
        """get_settings applies profile settings."""
        (tmp_path / "pyproject.toml").touch()
        profiles_dir = tmp_path / ".spine" / "profiles"
        profiles_dir.mkdir(parents=True)
        (profiles_dir / "test.toml").write_text(
            '[profile]\nname = "test"\n\n'
            'log_level = "ERROR"\n'
        )
        s = get_settings(project_root=tmp_path, profile="test")
        assert s.log_level == "ERROR"

    def test_clear_settings_cache(self, tmp_path: Path):
        s1 = get_settings(project_root=tmp_path)
        clear_settings_cache()
        s2 = get_settings(project_root=tmp_path)
        assert s1 is not s2
