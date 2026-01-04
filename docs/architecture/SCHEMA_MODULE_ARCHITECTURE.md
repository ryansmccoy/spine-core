# Schema Module Architecture

**Status**: ✅ Implemented  
**Owner**: Market Spine - Core Team  
**Last Updated**: 2025-01-05

---

## Overview

The Market Spine schema is now organized into **modular files** owned by their respective packages:

- **Core framework tables** → `packages/spine-core/src/spine/core/schema/`
- **Domain-specific tables** → `packages/spine-domains/src/spine/domains/{domain}/schema/`

This maintains **ownership clarity** and **modularity** while still producing a **single operational artifact** for DBAs to apply.

---

## Directory Structure

```
spine-core/
├── packages/
│   ├── spine-core/
│   │   └── src/spine/core/schema/
│   │       └── 00_core.sql                # Core framework tables
│   │
│   └── spine-domains/
│       └── src/spine/domains/
│           ├── finra/otc_transparency/schema/
│           │   ├── 00_tables.sql          # FINRA tables
│           │   ├── 01_indexes.sql         # FINRA indexes
│           │   └── 02_views.sql           # FINRA views
│           │
│           └── reference/exchange_calendar/schema/
│               ├── 00_tables.sql          # Reference tables
│               └── 01_indexes.sql         # Reference indexes
│
├── scripts/
│   └── build_schema.py                    # Combines modules → single schema
│
└── market-spine-basic/
    └── migrations/
        └── schema.sql                     # ⚠️ GENERATED - DO NOT EDIT
```

---

## Workflow

### 1️⃣ Editing Schema

When you need to modify the schema:

**Edit the module files** (NOT the generated `schema.sql`):

```bash
# For core framework changes
vim packages/spine-core/src/spine/core/schema/00_core.sql

# For FINRA domain changes
vim packages/spine-domains/src/spine/domains/finra/otc_transparency/schema/00_tables.sql

# For reference domain changes
vim packages/spine-domains/src/spine/domains/reference/exchange_calendar/schema/00_tables.sql
```

### 2️⃣ Building Combined Schema

After editing modules, regenerate the operational artifact using any of these methods:

**Python (always works):**
```bash
python scripts/build_schema.py
```

**Just (recommended - cross-platform):**
```bash
just schema-build
```

**Make (Unix/macOS):**
```bash
make schema-build
```

**Docker:**
```bash
cd market-spine-basic
docker compose --profile schema run --rm schema-build
```

Output:
```
✅ Schema built successfully!
   Output: market-spine-basic/migrations/schema.sql
   Size: 37,365 bytes
   Modules: 6
```

### 3️⃣ Applying to Database

Use the generated schema as before:

```bash
spine db init
```

Or manually:

```bash
sqlite3 market_spine.db < market-spine-basic/migrations/schema.sql
```

### 4️⃣ Commit Changes

Commit **both** the module files AND the generated schema:

```bash
git add packages/spine-core/src/spine/core/schema/00_core.sql
git add market-spine-basic/migrations/schema.sql
git commit -m "feat(schema): Add core_new_table for X"
```

---

## Module Ownership

| Module | Owner Package | Tables | Responsibility |
|--------|--------------|--------|----------------|
| `00_core.sql` | spine-core | `core_*` | Execution tracking, manifest, quality, anomalies, work scheduling, dependencies, schedules, readiness |
| `finra/.../00_tables.sql` | spine-domains | `finra_otc_transparency_*` | FINRA OTC weekly trading data (raw, normalized, silver, gold layers) |
| `finra/.../01_indexes.sql` | spine-domains | Indexes for FINRA tables | Performance optimization |
| `finra/.../02_views.sql` | spine-domains | Views for FINRA tables | "Latest only" convenience views |
| `reference/.../00_tables.sql` | spine-domains | `reference_exchange_calendar_*` | Exchange holiday calendars, trading days |
| `reference/.../01_indexes.sql` | spine-domains | Indexes for reference tables | Performance optimization |

---

## Naming Conventions

**Core Framework Tables:**
- Prefix: `core_*`
- Example: `core_executions`, `core_manifest`, `core_anomalies`

**Domain-Specific Tables:**
- Prefix: `{domain}_{subdomain}_*`
- FINRA example: `finra_otc_transparency_raw`, `finra_otc_transparency_symbol_summary`
- Reference example: `reference_exchange_calendar_holidays`

**Views:**
- Suffix: `_latest` for point-in-time "current" views
- Example: `finra_otc_transparency_symbol_summary_latest`

---

## Adding a New Domain

To add a new domain (e.g., SEC EDGAR filings):

1. **Create directory structure:**
   ```bash
   mkdir -p packages/spine-domains/src/spine/domains/sec/edgar/schema
   ```

2. **Create module files:**
   ```
   packages/spine-domains/src/spine/domains/sec/edgar/schema/
   ├── 00_tables.sql    # CREATE TABLE sec_edgar_filings ...
   ├── 01_indexes.sql   # CREATE INDEX idx_sec_edgar_filings_date ...
   └── 02_views.sql     # CREATE VIEW sec_edgar_filings_latest ...
   ```

3. **Update build script:**
   ```python
   # In scripts/build_schema.py, add to SCHEMA_MODULES:
   ("SEC EDGAR - Tables", DOMAINS_SCHEMA_DIR / "sec/edgar/schema/00_tables.sql"),
   ("SEC EDGAR - Indexes", DOMAINS_SCHEMA_DIR / "sec/edgar/schema/01_indexes.sql"),
   ("SEC EDGAR - Views", DOMAINS_SCHEMA_DIR / "sec/edgar/schema/02_views.sql"),
   ```

4. **Rebuild and test:**
   ```bash
   python scripts/build_schema.py
   pytest tests/test_schema_modules.py
   ```

---

## Validation Tests

Schema module separation is validated by `tests/test_schema_modules.py`:

- ✅ Core module contains only `core_*` tables
- ✅ FINRA module contains only `finra_otc_transparency_*` tables
- ✅ Reference module contains only `reference_exchange_calendar_*` tables
- ✅ No cross-contamination between modules
- ✅ Generated schema includes all modules
- ✅ Tables/indexes/views correctly separated

Run validation:
```bash
pytest tests/test_schema_modules.py -v
```

---

## Benefits

### For Developers
- **Clear ownership**: Each package owns its schema modules
- **Easier review**: Smaller files, focused changes
- **Modularity**: Add new domains without touching core schema

### For Operations
- **Single artifact**: Still deploy one `schema.sql` file
- **No workflow change**: `spine db init` works as before
- **Auditability**: Generated file includes module provenance

### For Compliance
- **Separation of concerns**: Core vs domain data clearly separated
- **Change tracking**: Git history shows which module changed
- **Dependency visibility**: Build script documents module order

---

## Generated Schema Header

The generated `market-spine-basic/migrations/schema.sql` includes:

```sql
-- =============================================================================
-- MARKET SPINE SCHEMA - COMBINED OPERATIONAL ARTIFACT
-- =============================================================================
-- 
-- ⚠️  THIS FILE IS GENERATED - DO NOT EDIT DIRECTLY ⚠️
--
-- To modify the schema:
--   1. Edit the source module files in:
--      - packages/spine-core/src/spine/core/schema/
--      - packages/spine-domains/src/spine/domains/{domain}/schema/
--   2. Run: python scripts/build_schema.py
--   3. Commit both module files AND this generated file
--
-- Generated: 2025-01-05T10:30:00
-- Build script: scripts/build_schema.py
--
-- MODULES INCLUDED (in order):
--   - Core Framework
--   - FINRA OTC Transparency - Tables
--   - FINRA OTC Transparency - Indexes
--   - FINRA OTC Transparency - Views
--   - Reference: Exchange Calendar - Tables
--   - Reference: Exchange Calendar - Indexes
--
-- =============================================================================
```

---

## Module Load Order

Modules are loaded in **deterministic order** to satisfy dependencies:

1. **Core framework** (`00_core.sql`) - First, because domains reference `core_manifest.domain`
2. **Domain tables** (`finra/.../00_tables.sql`, `reference/.../00_tables.sql`)
3. **Domain indexes** (`01_indexes.sql`) - After tables exist
4. **Domain views** (`02_views.sql`) - After tables and indexes

This order is enforced by `scripts/build_schema.py` in the `SCHEMA_MODULES` list.

---

## Troubleshooting

### "Generated schema is missing tables"
- Check module file exists in `SCHEMA_MODULES` list
- Rebuild: `python scripts/build_schema.py`

### "UnicodeDecodeError when running tests"
- Ensure test fixture uses `encoding='utf-8'` when reading schema
- Example: `schema_sql = db_path.read_text(encoding='utf-8')`

### "Table already exists" error
- Check for duplicate table definitions across modules
- Run validation: `pytest tests/test_schema_modules.py`

### "Module not found" during build
- Verify directory structure matches expected paths
- Check `CORE_SCHEMA_DIR` and `DOMAINS_SCHEMA_DIR` in build script

---

## Related Documentation

- [Institutional Hardening Summary](../ops/INSTITUTIONAL_HARDENING_SUMMARY.md) - Why we have anomalies, readiness, schedules
- [Table Storage Patterns](../architecture/TABLE_STORAGE_PATTERNS.md) - Materialized vs views guidance
- [Failure Scenarios](../analytics/FAILURE_SCENARIOS.md) - Real trading analytics failure cases

---

## Change History

| Date | Change | Rationale |
|------|--------|-----------|
| 2025-01-05 | Initial schema refactoring | Improve ownership clarity and modularity while maintaining single operational artifact |
