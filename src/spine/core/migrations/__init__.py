"""Schema migration runner for spine-core.

Manifesto:
    Database schemas must evolve safely across deployments.  Manual DDL
    execution is error-prone and unrepeatable.  The migration runner
    applies numbered .sql files idempotently, tracking what has already
    been applied in the ``_migrations`` table.

Applies SQL migration files from ``core/schema/`` in filename order,
tracking which have already been applied in the ``_migrations`` table.

Modules
-------
runner    MigrationRunner class with apply_pending() / status()

Tags:
    spine-core, migrations, schema, database, idempotent, DDL

Doc-Types:
    package-overview
"""

from spine.core.migrations.runner import MigrationRunner

__all__ = ["MigrationRunner"]
