"""Schema migration runner for spine-core.

Applies SQL migration files from ``core/schema/`` in filename order,
tracking which have already been applied in the ``_migrations`` table.
This ensures database schemas evolve safely across deployments without
manual DDL execution or lost migrations.

Usage::

    from spine.core.migrations import MigrationRunner

    runner = MigrationRunner(conn)
    runner.apply_pending()   # idempotent -- skips already-applied files

Modules
-------
runner    MigrationRunner class with apply_pending() / status()
"""

from spine.core.migrations.runner import MigrationRunner

__all__ = ["MigrationRunner"]
