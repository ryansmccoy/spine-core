"""Alembic environment configuration for spine-core.

Reads DATABASE_URL from environment (falling back to alembic.ini default).
Imports all ORM models so autogenerate can detect schema changes.
"""

from __future__ import annotations

import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

# Alembic Config object — provides access to .ini values
config = context.config

# Override sqlalchemy.url from environment if set
database_url = os.environ.get("SPINE_DATABASE_URL") or os.environ.get("DATABASE_URL")
if database_url:
    config.set_main_option("sqlalchemy.url", database_url)

# Python logging from .ini file
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Import ORM models so Alembic autogenerate sees all tables.
# This triggers the import of all 30+ mapped table classes.
from spine.core.orm.base import SpineBase  # noqa: E402

# Import all table modules to register them with the metadata
import spine.core.orm.tables  # noqa: E402, F401

target_metadata = SpineBase.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (SQL script output only)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,  # SQLite ALTER TABLE support
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode (live database connection)."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,  # SQLite ALTER TABLE support
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
