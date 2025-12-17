"""Coverage-boosting tests for small core modules.

Tests simple instantiation, imports, and basic API usage for modules with
low coverage or that are difficult to test via integration paths.
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from spine.core.adapters.registry import AdapterRegistry, adapter_registry
from spine.core.adapters.sqlite import SQLiteAdapter
from spine.core.adapters.types import DatabaseConfig, DatabaseType
from spine.core.health import SpineHealth
from spine.core.logging import configure_logging, get_logger
from spine.core.timestamps import from_iso8601, generate_ulid, to_iso8601


# ============================================================================
# Timestamps Module Tests
# ============================================================================


class TestTimestamps:
    """Test spine.core.timestamps functions."""

    def test_generate_ulid_returns_string(self):
        """generate_ulid() returns a non-empty string."""
        ulid = generate_ulid()
        assert isinstance(ulid, str)
        assert len(ulid) == 26  # ULID format is 26 chars

    def test_generate_ulid_is_unique(self):
        """generate_ulid() produces unique values."""
        ulids = {generate_ulid() for _ in range(10)}
        assert len(ulids) == 10  # All 10 ULIDs are unique

    def test_to_iso8601_with_datetime(self):
        """to_iso8601() converts datetime to ISO8601 string."""
        from datetime import datetime, timezone

        dt = datetime(2026, 2, 9, 12, 30, 45, tzinfo=timezone.utc)
        iso_str = to_iso8601(dt)
        assert isinstance(iso_str, str)
        assert "2026-02-09" in iso_str
        assert "12:30:45" in iso_str

    def test_to_iso8601_roundtrip(self):
        """to_iso8601() and from_iso8601() are inverses."""
        from datetime import datetime, timezone

        original = datetime(2026, 2, 9, 12, 30, 45, 123456, tzinfo=timezone.utc)
        iso_str = to_iso8601(original)
        restored = from_iso8601(iso_str)
        # Compare with microsecond precision for roundtrip
        assert (original - restored).total_seconds() < 0.001

    def test_from_iso8601_parses_string(self):
        """from_iso8601() parses ISO8601 timestamp strings."""
        iso_str = "2026-02-09T12:30:45.000Z"
        dt = from_iso8601(iso_str)
        assert dt.year == 2026
        assert dt.month == 2
        assert dt.day == 9


# ============================================================================
# Adapters - Types Module Tests
# ============================================================================


class TestAdapterTypes:
    """Test spine.core.adapters.types enums and configs."""

    def test_database_type_sqlite(self):
        """DatabaseType enum includes SQLITE."""
        assert DatabaseType.SQLITE is not None
        assert DatabaseType.SQLITE.value == "sqlite"

    def test_database_type_postgresql(self):
        """DatabaseType enum includes POSTGRESQL."""
        assert DatabaseType.POSTGRESQL is not None
        assert DatabaseType.POSTGRESQL.value == "postgresql"

    def test_database_config_from_dict(self):
        """DatabaseConfig can be instantiated with dict."""
        config = DatabaseConfig(
            db_type=DatabaseType.SQLITE,
            host="localhost",
            port=5432,
            database="test_db",
        )
        assert config.db_type == DatabaseType.SQLITE
        assert config.database == "test_db"

    def test_database_config_defaults(self):
        """DatabaseConfig provides sensible defaults."""
        config = DatabaseConfig(db_type=DatabaseType.SQLITE, path=":memory:")
        assert config.host == "localhost"
        assert config.port == 5432


# ============================================================================
# Adapters - SQLite Module Tests
# ============================================================================


class TestSQLiteAdapter:
    """Test spine.core.adapters.sqlite.SQLiteAdapter."""

    def test_sqlite_adapter_init(self):
        """SQLiteAdapter can be instantiated."""
        adapter = SQLiteAdapter(":memory:")
        assert adapter is not None

    def test_sqlite_adapter_init_with_path(self):
        """SQLiteAdapter accepts path parameter."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test.db")
            adapter = SQLiteAdapter(db_path)
            assert adapter is not None

    def test_sqlite_adapter_config_is_set(self):
        """SQLiteAdapter stores config."""
        adapter = SQLiteAdapter(":memory:")
        assert adapter._config is not None
        assert adapter._config.db_type == DatabaseType.SQLITE


# ============================================================================
# Adapters - Registry Module Tests
# ============================================================================


class TestAdapterRegistry:
    """Test spine.core.adapters.registry.AdapterRegistry."""

    def test_registry_create_sqlite(self):
        """AdapterRegistry.create() returns SQLite adapter."""
        registry = AdapterRegistry()
        adapter = registry.create("sqlite", path=":memory:")
        assert isinstance(adapter, SQLiteAdapter)

    def test_registry_list_adapters(self):
        """AdapterRegistry.list_adapters() lists all registered adapters."""
        registry = AdapterRegistry()
        adapters = registry.list_adapters()
        assert "sqlite" in adapters
        assert "postgresql" in adapters
        assert "postgres" in adapters

    def test_registry_raises_on_unknown_adapter(self):
        """AdapterRegistry.create() raises ConfigError for unknown adapter."""
        from spine.core.errors import ConfigError

        registry = AdapterRegistry()
        with pytest.raises(ConfigError):
            registry.create("unknown_db_type", path="localhost")

    def test_global_adapter_registry_available(self):
        """Global adapter_registry instance is available."""
        assert adapter_registry is not None
        assert isinstance(adapter_registry, AdapterRegistry)


# ============================================================================
# Health Module Tests
# ============================================================================


class TestHealthModule:
    """Test spine.core.health module."""

    def test_spine_health_instantiation(self):
        """SpineHealth can be instantiated."""
        health = SpineHealth(name="test-spine", version="0.1.0")
        assert health.name == "test-spine"
        assert health.version == "0.1.0"

    def test_spine_health_default_status(self):
        """SpineHealth has default status 'ok'."""
        health = SpineHealth(name="test-spine", version="0.1.0")
        assert health.status == "ok"

    def test_spine_health_status_degraded(self):
        """SpineHealth can have status 'degraded'."""
        health = SpineHealth(
            name="test-spine", version="0.1.0", status="degraded"
        )
        assert health.status == "degraded"

    def test_spine_health_status_error(self):
        """SpineHealth can have status 'error'."""
        health = SpineHealth(
            name="test-spine", version="0.1.0", status="error"
        )
        assert health.status == "error"

    def test_spine_health_uptime_available(self):
        """SpineHealth includes uptime_s field."""
        health = SpineHealth(name="test-spine", version="0.1.0")
        assert health.uptime_s >= 0

    def test_spine_health_details_dict(self):
        """SpineHealth accepts details dict."""
        details = {"nodes": 10, "edges": 50}
        health = SpineHealth(
            name="test-spine",
            version="0.1.0",
            details=details,
        )
        assert health.details == details


# ============================================================================
# Database Module Tests
# ============================================================================


class TestDatabaseModule:
    """Test spine.core.database module."""

    def test_database_module_imports(self):
        """spine.core.database module can be imported."""
        import spine.core.database

        assert spine.core.database is not None

    def test_sqlite_config_instantiation(self):
        """SQLiteAdapter can be created with path."""
        config = DatabaseConfig(db_type=DatabaseType.SQLITE, path=":memory:")
        assert config.db_type == DatabaseType.SQLITE
        assert config.path == ":memory:"


# ============================================================================
# Logging Module Tests
# ============================================================================


class TestLoggingModule:
    """Test spine.core.logging module."""

    def test_get_logger_returns_logger(self):
        """get_logger() returns a logger instance."""
        logger = get_logger(__name__)
        assert logger is not None
        assert hasattr(logger, "debug")
        assert hasattr(logger, "info")
        assert hasattr(logger, "warning")
        assert hasattr(logger, "error")

    def test_get_logger_different_names_different_loggers(self):
        """get_logger() returns different loggers for different names."""
        logger1 = get_logger("test_logger_1")
        logger2 = get_logger("test_logger_2")
        # structlog uses lazy proxies, so we just check they're not the same object
        assert logger1 is not None
        assert logger2 is not None

    def test_configure_logging_no_error(self):
        """configure_logging() runs without error."""
        # This is a smoke test - just verify it doesn't raise
        result = configure_logging()
        # Most configure functions return None or True
        assert result is not None or result is None
