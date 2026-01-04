# ADR 003: SQLite Reset and Development Workflow

**Status**: Accepted  
**Date**: December 2025  
**Context**: Development workflow for Market Spine Basic

## Decision

During development, the primary workflow is **nuke and rebuild**:

```bash
spine db reset --yes
spine db init
```

This is intentional. Basic tier prioritizes simplicity over incremental migration.

## Context

We need a fast, reliable development loop for:
- Testing pipeline changes
- Debugging data issues
- Iterating on schema changes
- Onboarding new developers

Traditional migration-based development:
- Requires writing migration scripts
- Accumulates schema drift
- Complicates rollback
- Slows iteration

## Why This Works for Basic Tier

### 1. SQLite is Local

Each developer has their own `spine.db`. There's no shared database to coordinate.

### 2. Data is Reproducible

All data comes from FINRA files. Re-ingest takes seconds:

```bash
spine db reset --yes
spine db init
spine run otc.backfill_range -p start_week=2025-12-06 -p end_week=2025-12-26 ...
```

### 3. Schema is Stable

Core tables (`core_manifest`, `core_rejects`, `core_quality`) are created via `CREATE TABLE IF NOT EXISTS`. They're idempotent.

### 4. Migrations Exist for Deployment

We still have migration files for:
- CI/CD deployment
- Production (higher tiers)
- Documentation of schema

But developers don't need to write migrations for every change.

## The Workflow

### Day-to-Day Development

```bash
# 1. Make schema changes in migration files
# 2. Reset and rebuild
spine db reset --yes
spine db init

# 3. Re-ingest test data
spine run otc.backfill_range ...

# 4. Test your changes
spine run otc.normalize_week ...
```

### Before Committing

```bash
# Verify migrations work on fresh database
rm spine.db
spine db init
spine run otc.backfill_range ...
python -m pytest tests/
```

### CI Pipeline

```yaml
- run: spine db init
- run: python -m pytest tests/
```

CI always starts fresh. No migration state to manage.

## Implementation

### Reset Command

```python
@db.command()
@click.confirmation_option(prompt="Are you sure?")
def reset():
    """Reset database (delete and reinitialize)."""
    reset_db()  # Deletes spine.db
    init_db()   # Re-runs migrations
```

### Reset Function

```python
def reset_db():
    settings = get_settings()
    db_path = Path(settings.database_path)
    if db_path.exists():
        db_path.unlink()  # Delete file
```

## Consequences

### Positive

1. **Fast iteration** — No migration script writing
2. **Clean state** — No accumulated cruft
3. **Reproducible** — Every run starts fresh
4. **Simple** — No migration version tracking

### Negative

1. **Data loss** — Reset destroys all data
2. **Re-ingest time** — Must re-load data after reset
3. **Not for production** — Only works with local SQLite

### Mitigation

For production (higher tiers):
- Use proper migration tooling (Alembic, etc.)
- Never use `db reset`
- Write incremental migrations

For development:
- Keep sample data files small
- Use `backfill_range` for quick re-population
- Document the workflow

## When NOT to Reset

- Production databases
- Shared development databases
- When debugging specific data issues (you'd lose the data!)

## Related

- [Quickstart](../tutorial/01_quickstart.md) — Uses this workflow
- `market_spine/db.py` — Implementation
