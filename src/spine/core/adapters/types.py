"""Database types and configuration."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from spine.core.errors import ConfigError


class DatabaseType(str, Enum):
    """Supported database types."""

    SQLITE = "sqlite"
    POSTGRESQL = "postgresql"
    DB2 = "db2"
    MYSQL = "mysql"
    ORACLE = "oracle"


@dataclass
class DatabaseConfig:
    """
    Configuration for database connection.

    Different fields are used by different database types.
    """

    # Common
    db_type: DatabaseType = DatabaseType.SQLITE

    # SQLite
    path: str | None = None

    # PostgreSQL / MySQL / Oracle
    host: str = "localhost"
    port: int = 5432
    database: str = ""
    username: str | None = None
    password: str | None = None

    # Connection pool
    pool_size: int = 5
    pool_overflow: int = 10
    pool_timeout: int = 30

    # SSL
    ssl_mode: str = "prefer"  # disable, prefer, require, verify-ca, verify-full
    ssl_cert: str | None = None
    ssl_key: str | None = None
    ssl_ca: str | None = None

    # Options
    connect_timeout: int = 10
    query_timeout: int = 30
    readonly: bool = False

    # Extra options (driver-specific)
    options: dict[str, Any] = field(default_factory=dict)

    def to_connection_string(self) -> str:
        """Generate connection string for the database type."""
        match self.db_type:
            case DatabaseType.SQLITE:
                return self.path or ":memory:"
            case DatabaseType.POSTGRESQL:
                return f"postgresql://{self.username}:{self.password}@{self.host}:{self.port}/{self.database}"
            case DatabaseType.MYSQL:
                return f"mysql://{self.username}:{self.password}@{self.host}:{self.port}/{self.database}"
            case DatabaseType.DB2:
                return (
                    f"DATABASE={self.database};"
                    f"HOSTNAME={self.host};"
                    f"PORT={self.port};"
                    f"PROTOCOL=TCPIP;"
                    f"UID={self.username or ''};"
                    f"PWD={self.password or ''};"
                )
            case DatabaseType.ORACLE:
                return f"oracle://{self.username}:{self.password}@{self.host}:{self.port}/{self.database}"
            case _:
                raise ConfigError(f"Connection string not supported for: {self.db_type}")


__all__ = [
    "DatabaseType",
    "DatabaseConfig",
]
