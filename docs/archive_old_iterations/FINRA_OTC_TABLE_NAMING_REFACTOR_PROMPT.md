# FINRA OTC Transparency — Table Naming Refactor (Basic Tier)

This doc is **both**:
1) recommendations for a cleaner table naming scheme aligned with the new pipeline namespace `finra.otc_transparency.*`, and  
2) a **paste‑ready Claude prompt** to implement it in `market-spine-basic`.

Context: the domain pipelines are now named:

- `finra.otc_transparency.ingest_week`
- `finra.otc_transparency.normalize_week`
- `finra.otc_transparency.aggregate_week`
- `finra.otc_transparency.compute_rolling`
- `finra.otc_transparency.backfill_range`

…but the SQLite tables are still generically named (`otc_*`), which will clash once we add other FINRA sources (TRACE, TRF, ORF, SLATE, etc.).

---

## 1) Recommendation: a naming scheme that scales

SQLite doesn’t have schemas, so **prefixing** is the standard way to prevent collisions.

### 1.1 Goals

- Avoid name collisions as FINRA grows to multiple data families.
- Make it obvious what’s **core framework** vs **domain**.
- Make it obvious what’s **raw** vs **normalized** vs **derived**.
- Keep table names predictable for future APIs.

### 1.2 Proposed table naming convention

**Core / framework tables**
- Keep `core_*` for framework-owned tables (manifest/quality/rejects/etc).
- Keep `_migrations` (or consider renaming to `core_migrations` later; not required).

**Domain tables**
Use:  
`finra_otc_transparency__<layer>__<entity>` (double underscore helps readability)

Where:
- `<layer>` ∈ `raw | norm | agg | calc | snap`
- `<entity>` is the logical dataset.

This matches how you already think about the system (“bronze/silver/gold”), but avoids introducing metal words into table names.

### 1.3 Concrete mapping (old → new)

These are the tables currently present in `schema.sql`:

- `_migrations`
- `executions`
- `otc_raw`
- `otc_venue_volume`
- `otc_symbol_summary`
- `otc_venue_share`
- `otc_symbol_rolling_6w`
- `otc_liquidity_score`
- `otc_research_snapshot`

Proposed mapping:

| Old table | New table | Layer | Notes |
|---|---|---|---|
| `otc_raw` | `finra_otc_transparency__raw__trades_weekly` | raw | “trades_weekly” is the raw per-venue weekly rows |
| `otc_venue_volume` | `finra_otc_transparency__norm__venue_volume_weekly` | norm | normalized fact table |
| `otc_symbol_summary` | `finra_otc_transparency__agg__symbol_summary_weekly` | agg | per-symbol weekly rollup |
| `otc_symbol_rolling_6w` | `finra_otc_transparency__calc__symbol_rolling_6w` | calc | rolling window metrics |
| `otc_liquidity_score` | `finra_otc_transparency__calc__liquidity_score` | calc | derived score table |
| `otc_venue_share` | `finra_otc_transparency__calc__venue_share` | calc | derived market share |
| `otc_research_snapshot` | `finra_otc_transparency__snap__research_snapshot` | snap | ad‑hoc/research oriented |

Also present:
| Old | New | Layer | Notes |
|---|---|---|---|
| `executions` | `core_executions` (or keep as `executions`) | core | choose consistency with the rest of `core_*` |

**Tip:** If you’d rather avoid long names, a shorter but still clear prefix works too:  
`finra_otc__raw__...` or `finra_otc_tr__...` — but the above is the most descriptive.

### 1.4 Backward compatibility (optional for Basic)

You said Basic can be destructive, so you can:
- **drop and rebuild** from scratch (simplest)  
OR
- use `ALTER TABLE ... RENAME TO ...` (safe; preserves data)  
AND optionally create **views** with the old names:

```sql
CREATE VIEW otc_raw AS SELECT * FROM finra_otc_transparency__raw__trades_weekly;
```

Views keep the old names usable for quick scripts, while code moves forward.

---

## 2) Additional improvements worth doing at the same time

These are “low effort / high leverage” changes that align with the refactor:

### 2.1 Capture ID prefix alignment

Current capture IDs look like: `finra_otc:OTC:2025-12-05:76c34c`.

Recommend aligning to the namespace you already expose to users:

- `finra.otc_transparency:{tier}:{week_ending}:{hash}`

This makes joins between logs, executions, and tables more intuitive.

### 2.2 Domain label consistency

In logs you currently emit `domain=finra_otc_transparency` in some places.
That’s fine, but consider standardizing on either:

- dot namespace: `finra.otc_transparency` (user-facing)  
- underscore namespace: `finra_otc_transparency` (internal)

Pick one and apply everywhere (table prefix, log domain, capture_id prefix).

### 2.3 CLI error UX (observed from logs)

In your sample logs, parameter mistakes (like missing `tier`) end up logged as `runner.pipeline_not_found` which is misleading.

Suggestion:
- Add a lightweight **params validation step** (before pipeline.run) that raises a `PipelineParamError`.
- Log it under a distinct event name: `pipeline.params.invalid`
- Have CLI print: what’s missing + an example command.

This will matter even more once you add an interactive CLI.

---

## 3) Paste‑ready Claude prompt: implement the table naming refactor

You are working in **market-spine-basic**. The FINRA OTC Transparency domain has already been renamed at the pipeline level to:

`finra.otc_transparency.*`

But the SQLite tables are still generically named (`otc_*`). I want to refactor the database schema + code to align table names to the FINRA namespace so we can safely add more FINRA domains later (TRACE/TRF/ORF/etc).

### Requirements
1) **Rename tables** to a scalable prefixed naming scheme. Use the mapping below (or propose a better one if you strongly prefer, but keep it deterministic and documented).
2) Update **all code** that references these tables:
   - SQL strings
   - ORM/helpers (if any)
   - `spine verify tables`
   - docs
3) Update **tests** to match, and add at least one regression test that asserts the table set in a newly initialized DB contains the new names.
4) Keep it **Basic-tier friendly**:
   - SQLite first
   - destructive reset is acceptable
   - migrations can be kept or replaced with schema.sql, but be consistent.
5) Add **optional compatibility views** for old table names *only if* it’s easy; otherwise skip.
6) Produce a clear summary of what changed and how to verify.

### Current schema input
The current DB schema is in: `schema.sql` (already in the repo / working directory).

Tables currently include:
- `_migrations`
- `executions`
- `otc_raw`
- `otc_venue_volume`
- `otc_symbol_summary`
- `otc_symbol_rolling_6w`
- `otc_liquidity_score`
- `otc_research_snapshot`
- `otc_venue_share`
…and some framework tables in SQLite like `core_manifest`, `core_rejects`, `core_quality` (keep those as-is).

### Proposed new table names (implement this mapping)
- `otc_raw` → `finra_otc_transparency__raw__trades_weekly`
- `otc_venue_volume` → `finra_otc_transparency__norm__venue_volume_weekly`
- `otc_symbol_summary` → `finra_otc_transparency__agg__symbol_summary_weekly`
- `otc_symbol_rolling_6w` → `finra_otc_transparency__calc__symbol_rolling_6w`
- `otc_liquidity_score` → `finra_otc_transparency__calc__liquidity_score`
- `otc_venue_share` → `finra_otc_transparency__calc__venue_share`
- `otc_research_snapshot` → `finra_otc_transparency__snap__research_snapshot`

Core:
- Decide whether `executions` should become `core_executions` (preferred for consistency), or leave it as-is. If you rename it, update code + docs accordingly.

### Implementation approach (choose one and execute)
Option A (simplest for Basic, destructive ok):
- Update `schema.sql` / migrations to create the new tables only.
- Update code to reference new names.
- Document that Basic reset is: delete DB and re-run init.

Option B (preserve data; do this only if it’s not painful):
- Write a SQLite migration that does `ALTER TABLE old RENAME TO new` for each table.
- Rename relevant indexes.
- (Optional) create views for old names.

### Also do these quick wins (if low effort)
- Align capture_id prefix with pipeline namespace:
  - from `finra_otc:...` to `finra.otc_transparency:...` (if safe)
- Improve CLI error UX:
  - missing params should not log `runner.pipeline_not_found`
  - add `pipeline.params.invalid` and print a nice example command

### Verification commands you must provide
- Clean init:
  - `Remove-Item spine.db -ErrorAction SilentlyContinue; uv run spine db init`
- Verify tables:
  - `uv run spine verify tables`
- Golden path:
  - `uv run spine run finra.otc_transparency.ingest_week -p file_path=data/fixtures/otc/week_2025-12-12.psv -p tier=OTC`
  - `uv run spine run finra.otc_transparency.normalize_week -p week_ending=2025-12-05 -p tier=OTC`
  - `uv run spine run finra.otc_transparency.aggregate_week -p week_ending=2025-12-05 -p tier=OTC`
- Tests:
  - `uv run pytest -q`

### Output format
Return:
1) short rationale for the naming choice
2) updated file tree (only relevant parts)
3) diffs (unified)
4) test changes summary
5) verification commands + expected outcomes

---

## 4) Notes for Intermediate (don’t implement yet)

In Postgres/Timescale, you *can* introduce real schemas:

- schema: `finra`
- tables: `otc_transparency__raw__...`

This Basic work should make that transition mechanical:
- sqlite prefix → postgres schema qualifier

But for now: implement the SQLite prefixing, keep it clean, and move on.
