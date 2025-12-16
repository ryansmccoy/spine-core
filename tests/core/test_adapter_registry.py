"""Tests for database adapter registration and the new adapters."""

from __future__ import annotations

import pytest

from spine.core.adapters.registry import adapter_registry
from spine.core.adapters.sqlite import SQLiteAdapter
from spine.core.dialect import (
    DB2Dialect,
    Dialect,
    MySQLDialect,
    OracleDialect,
    PostgreSQLDialect,
    SQLiteDialect,
    get_dialect,
)


class TestAdapterRegistry:
    def test_sqlite_registered(self) -> None:
        assert "sqlite" in adapter_registry.list_adapters()

    def test_postgresql_registered(self) -> None:
        assert "postgresql" in adapter_registry.list_adapters()

    def test_postgres_alias_registered(self) -> None:
        assert "postgres" in adapter_registry.list_adapters()

    def test_db2_registered(self) -> None:
        assert "db2" in adapter_registry.list_adapters()

    def test_mysql_registered(self) -> None:
        assert "mysql" in adapter_registry.list_adapters()

    def test_oracle_registered(self) -> None:
        assert "oracle" in adapter_registry.list_adapters()

    def test_unknown_raises(self) -> None:
        from spine.core.errors import ConfigError

        with pytest.raises(ConfigError, match="Unknown database adapter"):
            adapter_registry.create("mongodb")


class TestDialectIntegration:
    """Verify get_dialect returns proper dialect for each adapter-supported backend."""

    @pytest.mark.parametrize(
        "name,dialect_type",
        [
            ("sqlite", SQLiteDialect),
            ("postgresql", PostgreSQLDialect),
            ("postgres", PostgreSQLDialect),
            ("db2", DB2Dialect),
            ("mysql", MySQLDialect),
            ("oracle", OracleDialect),
        ],
    )
    def test_get_dialect_by_name(self, name: str, dialect_type: type) -> None:
        d = get_dialect(name)
        assert isinstance(d, dialect_type)
