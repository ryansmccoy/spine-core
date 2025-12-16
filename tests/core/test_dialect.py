"""Tests for the Dialect abstraction layer."""

from __future__ import annotations

import pytest

from spine.core.dialect import (
    DB2Dialect,
    Dialect,
    MySQLDialect,
    OracleDialect,
    PostgreSQLDialect,
    SQLiteDialect,
    get_dialect,
    register_dialect,
)


# =========================================================================
# Fixtures
# =========================================================================


@pytest.fixture(params=["sqlite", "postgresql", "db2", "mysql", "oracle"])
def dialect(request: pytest.FixtureRequest) -> Dialect:
    """Parametric fixture: run each test against every dialect."""
    return get_dialect(request.param)


@pytest.fixture
def sqlite() -> SQLiteDialect:
    return SQLiteDialect()


@pytest.fixture
def pg() -> PostgreSQLDialect:
    return PostgreSQLDialect()


@pytest.fixture
def db2() -> DB2Dialect:
    return DB2Dialect()


@pytest.fixture
def mysql() -> MySQLDialect:
    return MySQLDialect()


@pytest.fixture
def oracle() -> OracleDialect:
    return OracleDialect()


# =========================================================================
# Protocol conformance
# =========================================================================


class TestProtocol:
    """Verify all concrete dialects implement the Dialect protocol."""

    def test_isinstance(self, dialect: Dialect) -> None:
        assert isinstance(dialect, Dialect)

    def test_name(self, dialect: Dialect) -> None:
        assert isinstance(dialect.name, str)
        assert len(dialect.name) > 0

    def test_all_methods_exist(self, dialect: Dialect) -> None:
        for attr in [
            "placeholder",
            "placeholders",
            "now",
            "interval",
            "insert_or_ignore",
            "insert_or_replace",
            "upsert",
            "json_set",
            "auto_increment",
            "timestamp_default_now",
            "boolean_true",
            "boolean_false",
            "table_exists_query",
        ]:
            assert callable(getattr(dialect, attr)), f"Missing {attr}"


# =========================================================================
# Placeholder generation
# =========================================================================


class TestPlaceholders:
    def test_single_placeholder_returns_string(self, dialect: Dialect) -> None:
        result = dialect.placeholder(0)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_placeholders_count_1(self, dialect: Dialect) -> None:
        result = dialect.placeholders(1)
        # Should not contain commas for a single placeholder
        assert "," not in result

    def test_placeholders_count_3(self, dialect: Dialect) -> None:
        result = dialect.placeholders(3)
        parts = [p.strip() for p in result.split(",")]
        assert len(parts) == 3

    def test_sqlite_placeholder(self, sqlite: SQLiteDialect) -> None:
        assert sqlite.placeholder(0) == "?"
        assert sqlite.placeholder(5) == "?"  # Index ignored
        assert sqlite.placeholders(3) == "?, ?, ?"

    def test_pg_placeholder(self, pg: PostgreSQLDialect) -> None:
        assert pg.placeholder(0) == "%s"
        assert pg.placeholders(3) == "%s, %s, %s"

    def test_db2_placeholder(self, db2: DB2Dialect) -> None:
        assert db2.placeholder(0) == "?"
        assert db2.placeholders(3) == "?, ?, ?"

    def test_mysql_placeholder(self, mysql: MySQLDialect) -> None:
        assert mysql.placeholder(0) == "%s"
        assert mysql.placeholders(3) == "%s, %s, %s"

    def test_oracle_placeholder(self, oracle: OracleDialect) -> None:
        assert oracle.placeholder(0) == ":1"
        assert oracle.placeholder(1) == ":2"
        assert oracle.placeholder(2) == ":3"
        assert oracle.placeholders(3) == ":1, :2, :3"


# =========================================================================
# Timestamp expressions
# =========================================================================


class TestTimestamps:
    def test_now_returns_string(self, dialect: Dialect) -> None:
        assert isinstance(dialect.now(), str)
        assert len(dialect.now()) > 0

    def test_sqlite_now(self, sqlite: SQLiteDialect) -> None:
        assert sqlite.now() == "datetime('now')"

    def test_pg_now(self, pg: PostgreSQLDialect) -> None:
        assert pg.now() == "NOW()"

    def test_db2_now(self, db2: DB2Dialect) -> None:
        assert db2.now() == "CURRENT TIMESTAMP"

    def test_mysql_now(self, mysql: MySQLDialect) -> None:
        assert mysql.now() == "NOW()"

    def test_oracle_now(self, oracle: OracleDialect) -> None:
        assert oracle.now() == "SYSTIMESTAMP"


class TestInterval:
    def test_negative_interval(self, dialect: Dialect) -> None:
        result = dialect.interval(-7, "days")
        assert isinstance(result, str)
        assert "7" in result

    def test_positive_interval(self, dialect: Dialect) -> None:
        result = dialect.interval(1, "hours")
        assert isinstance(result, str)

    def test_sqlite_interval(self, sqlite: SQLiteDialect) -> None:
        assert sqlite.interval(-7, "days") == "datetime('now', '-7 days')"

    def test_pg_interval(self, pg: PostgreSQLDialect) -> None:
        assert pg.interval(-7, "days") == "NOW() - INTERVAL '7 days'"


# =========================================================================
# DML helpers
# =========================================================================


class TestInsertOrIgnore:
    def test_returns_sql(self, dialect: Dialect) -> None:
        sql = dialect.insert_or_ignore("t", ["a", "b"])
        assert "t" in sql
        assert isinstance(sql, str)

    def test_sqlite(self, sqlite: SQLiteDialect) -> None:
        sql = sqlite.insert_or_ignore("locks", ["id", "val"])
        assert "INSERT OR IGNORE" in sql
        assert "locks" in sql
        assert "?, ?" in sql

    def test_pg(self, pg: PostgreSQLDialect) -> None:
        sql = pg.insert_or_ignore("locks", ["id", "val"])
        assert "ON CONFLICT DO NOTHING" in sql

    def test_mysql(self, mysql: MySQLDialect) -> None:
        sql = mysql.insert_or_ignore("locks", ["id", "val"])
        assert "INSERT IGNORE" in sql

    def test_oracle(self, oracle: OracleDialect) -> None:
        sql = oracle.insert_or_ignore("locks", ["id", "val"])
        assert "MERGE" in sql
        assert "WHEN NOT MATCHED" in sql

    def test_db2(self, db2: DB2Dialect) -> None:
        sql = db2.insert_or_ignore("locks", ["id", "val"])
        assert "MERGE" in sql


class TestUpsert:
    def test_returns_sql(self, dialect: Dialect) -> None:
        sql = dialect.upsert("t", ["a", "b", "c"], ["a"])
        assert "t" in sql

    def test_sqlite_upsert(self, sqlite: SQLiteDialect) -> None:
        sql = sqlite.upsert("manifest", ["domain", "key", "val"], ["domain", "key"])
        assert "ON CONFLICT" in sql
        assert "DO UPDATE SET" in sql
        assert "val = excluded.val" in sql

    def test_pg_upsert(self, pg: PostgreSQLDialect) -> None:
        sql = pg.upsert("manifest", ["domain", "key", "val"], ["domain", "key"])
        assert "ON CONFLICT" in sql
        assert "val = EXCLUDED.val" in sql

    def test_mysql_upsert(self, mysql: MySQLDialect) -> None:
        sql = mysql.upsert("manifest", ["domain", "key", "val"], ["domain", "key"])
        assert "ON DUPLICATE KEY UPDATE" in sql

    def test_oracle_upsert(self, oracle: OracleDialect) -> None:
        sql = oracle.upsert("manifest", ["domain", "key", "val"], ["domain", "key"])
        assert "MERGE" in sql
        assert "WHEN MATCHED" in sql
        assert "WHEN NOT MATCHED" in sql


# =========================================================================
# JSON helpers
# =========================================================================


class TestJsonSet:
    def test_returns_sql(self, dialect: Dialect) -> None:
        sql = dialect.json_set("col", "$.path", "?")
        assert isinstance(sql, str)

    def test_sqlite(self, sqlite: SQLiteDialect) -> None:
        sql = sqlite.json_set("metadata", "$.note", "?")
        assert "json_set" in sql
        assert "metadata" in sql
        assert "$.note" in sql


# =========================================================================
# DDL helpers
# =========================================================================


class TestDDL:
    def test_auto_increment(self, dialect: Dialect) -> None:
        result = dialect.auto_increment()
        assert isinstance(result, str)
        assert "PRIMARY KEY" in result or "IDENTITY" in result

    def test_timestamp_default(self, dialect: Dialect) -> None:
        result = dialect.timestamp_default_now()
        assert isinstance(result, str)
        assert "DEFAULT" in result

    def test_booleans(self, dialect: Dialect) -> None:
        t = dialect.boolean_true()
        f = dialect.boolean_false()
        assert t != f

    def test_table_exists(self, dialect: Dialect) -> None:
        result = dialect.table_exists_query()
        assert isinstance(result, str)
        assert len(result) > 10


# =========================================================================
# Registry / Factory
# =========================================================================


class TestRegistry:
    def test_get_dialect_sqlite(self) -> None:
        d = get_dialect("sqlite")
        assert d.name == "sqlite"

    def test_get_dialect_postgresql(self) -> None:
        d = get_dialect("postgresql")
        assert d.name == "postgresql"

    def test_get_dialect_postgres_alias(self) -> None:
        d = get_dialect("postgres")
        assert d.name == "postgresql"

    def test_get_dialect_db2(self) -> None:
        d = get_dialect("db2")
        assert d.name == "db2"

    def test_get_dialect_mysql(self) -> None:
        d = get_dialect("mysql")
        assert d.name == "mysql"

    def test_get_dialect_oracle(self) -> None:
        d = get_dialect("oracle")
        assert d.name == "oracle"

    def test_get_dialect_case_insensitive(self) -> None:
        d = get_dialect("SQLITE")
        assert d.name == "sqlite"

    def test_get_dialect_unknown_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown dialect"):
            get_dialect("mongodb")

    def test_register_custom(self) -> None:
        custom = SQLiteDialect()
        register_dialect("custom_test", custom)
        d = get_dialect("custom_test")
        assert d.name == "sqlite"

    def test_singletons(self) -> None:
        """Same dialect object returned on repeated calls."""
        a = get_dialect("sqlite")
        b = get_dialect("sqlite")
        assert a is b
