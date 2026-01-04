# Claude Prompt — Redo the CLI (Modern, Intuitive, “Bells & Whistles”)

You are improving the **market-spine-basic** CLI (`spine`) after an initial “modernization” pass that still feels clunky and confusing.  
Your job: **redo the CLI UX end-to-end** so it feels like a polished, modern Python tool.

## What’s wrong today (symptoms from real usage)

### 1) Confusing argument passing for pipelines
Users naturally try:
- `spine run finra.otc_transparency.normalize_week --week-ending 2025-12-05 --tier OTC` → **fails** (“No such option”)
- `spine run finra.otc_transparency.normalize_week week_ending=... tier=...` → **fails** (“unexpected extra arguments”)
Only `-p key=value` works, which is not ergonomic.

**Goal:** make running pipelines feel first-class and obvious.

### 2) Help text looks broken / duplicated
`spine run --help` currently prints repeated “Options:” blocks.

**Goal:** clean, concise help output.

### 3) Tier mismatch in `query` UX
`spine query symbols --tier` offers `[Tier1|Tier2|OTC]`, but the data contains tiers like `NMS_TIER_1`, `NMS_TIER_2`, `OTC`.  
So `--tier NMS_TIER_1` fails; `--tier Tier1` succeeds syntactically but returns no results.

**Goal:** align CLI enums with **actual** tier values stored in DB.

### 4) PowerShell / uv stderr logging annoyance
In PowerShell, `uv run spine ... 2>&1 | Select-Object ...` can show `uv : ... NativeCommandError` because logs are emitted on stderr (treated as error records).  
Your current structured logs are useful, but the default “human CLI experience” should not look like an error stream.

**Goal:** “human output” should go to stdout and be pleasant; structured logs should be optional.

---

## Hard requirements

### A) Choose a modern CLI stack
Use a modern combination, preferably:
- **Typer** (Click-based) for commands + option parsing
- **Rich** for tables, progress/spinners, panels
- Optional: **questionary** (or Rich prompts) for interactive menus

If you choose alternatives (e.g., Textual), justify and keep it lightweight.

### B) The CLI must support BOTH:
1) **Non-interactive / scriptable usage** (CI-friendly)
2) **Interactive mode** with a menu when the user runs `spine` without args (or `spine ui`)

### C) “Progress” should be step phases (not percent)
Use **phase-based progress** like:
- Phase 1/4: Validate inputs
- Phase 2/4: Load data
- Phase 3/4: Transform/compute
- Phase 4/4: Persist + finalize

For long steps (like ingesting 50k+ rows), show a spinner + elapsed time; only show a progress bar if you can measure total work reliably.

### D) Keep the architecture decoupled
The CLI is **presentation / UX**. It should call into the already-existing runner/dispatcher/pipeline registry rather than embedding domain logic.

---

## Concrete UX spec

### 1) Command structure (top-level)
Keep existing command groups but polish them:

- `spine --version`
- `spine list`  
  - Show pipelines table (name + description), optionally filter by prefix (`--prefix finra.`)
- `spine run <pipeline>`  
  - MUST accept pipeline parameters in **three ways**:
    - `--param key=value` repeated (keep for compatibility)
    - `key=value` as extra args (ergonomic)
    - If the pipeline has well-known params (week_ending, tier, file_path), also provide **nice options**:
      - `--week-ending YYYY-MM-DD`
      - `--tier OTC|NMS_TIER_1|NMS_TIER_2`
      - `--file PATH`
  - Provide `spine run <pipeline> --help-params` that shows:
    - required params
    - optional params
    - types and example values
  - Provide `--dry-run` to show resolved params + what would execute.
  - Provide `--quiet` to suppress structured logs and show only the Rich status output.
  - Provide `--log-format pretty|json` (default: pretty)
  - Provide `--log-level info|debug|warning|error`

- `spine db init` / `spine db reset` (basic uses SQLite)
  - `init` creates DB if missing
  - `reset` (destructive) deletes and recreates DB (confirm prompt unless `--yes`)

- `spine verify tables` / `spine verify data`
  - Use Rich tables + clear success/fail summary.

- `spine query weeks`
- `spine query symbols`  
  - MUST support:
    - `--week YYYY-MM-DD` (or `--week-ending`)
    - `--tier OTC|NMS_TIER_1|NMS_TIER_2`
    - `--top N`
    - positional optional `SYMBOL`
  - Ensure tier filter matches database values exactly.

### 2) Interactive mode (“awesome basic”)
When `spine` runs with no args, open an interactive menu:

Main menu:
- Run pipeline
- Query data
- Verify database
- Initialize/reset database
- Show pipelines
- Exit

Interactive pipeline run flow:
- fuzzy-search pipeline names
- show pipeline description
- prompt for parameters (week-ending picker via text + validation, tier select, file picker path)
- show resolved params
- confirm then run
- show phase-based progress + final summary (metrics)

### 3) Output design
- Always end with a clean “Summary” panel showing:
  - status (completed/failed/skipped)
  - duration
  - capture_id (if present)
  - key metrics (rows, symbols, rejected)
- On errors:
  - show a concise user-friendly message
  - provide `--debug` / `--log-level debug` to display tracebacks or full context
  - DO NOT print raw stack traces by default unless it’s truly unexpected.

### 4) Logging integration changes (important)
Today logs look fine as structured events, but they harm the CLI UX in PowerShell.

Implement a **dual-channel** approach:
- **Human UI**: Rich progress + summary to **stdout**
- **Structured logs**:
  - default to **stdout** in pretty mode (so PowerShell doesn’t treat it as error)
  - optionally allow `--log-to stderr` for unix pipelines
  - allow `--log-format json` for machine parsing

Also fix the confusing error labeling:
- Some errors show `runner.pipeline_not_found` even when the pipeline exists but a param KeyError occurred.
- Ensure exception mapping is correct:
  - param validation error → “Invalid parameters”
  - pipeline not registered → “Unknown pipeline”
  - pipeline exception → “Pipeline failed” with root cause

### 5) Parameter model / validation
Add a clean parameter parsing layer:
- Accept `key=value` extras and translate into the same dict as `--param`.
- Validate required params before dispatch.
- Validate types:
  - dates (`week_ending`) must parse as YYYY-MM-DD
  - tier must be one of enum values in the domain (OTC, NMS_TIER_1, NMS_TIER_2)
  - file path must exist unless pipeline explicitly allows missing

### 6) Keep compatibility
If the current CLI already exists, do not break existing scripts:
- keep `spine run ... -p key=value` working
- keep current subcommands but feel free to add better aliases (e.g., `spine pipelines` alias of `spine list`)

---

## Implementation constraints
- This is **Basic tier**: keep dependencies modest.
- Must run on Windows (PowerShell) and macOS/Linux.
- Must work under `uv run spine ...`.
- Keep code structured and testable:
  - put CLI under `packages/spine-core/src/spine/cli/` (or equivalent)
  - avoid huge single-file CLI modules

---

## Deliverables (required)
1) **Plan** (ordered checklist)
2) Proposed CLI command UX with examples (copy/paste runnable)
3) File tree + diffs (unified diff format)
4) Any new dependencies added to pyproject (Typer/Rich/questionary/etc.)
5) Update docs (README “CLI Usage” section)
6) Add tests for:
   - param parsing (`-p` + `key=value` + friendly options)
   - tier enum alignment for query commands
   - help output not duplicated (snapshot-ish test or string contains)
7) Verify commands:
   - `uv run spine --version`
   - `uv run spine list`
   - `uv run spine db init`
   - `uv run spine run finra.otc_transparency.ingest_week --file ... --tier OTC`
   - `uv run spine query weeks`
   - `uv run spine query symbols --week ... --tier NMS_TIER_1 --top 10`

---

## Extra improvements (do if easy)
- `spine doctor` command that checks:
  - python version
  - dependency health
  - DB path readability/writability
  - schema present
- `spine completion` to install shell completion if Typer supports it.
- `spine config` to show resolved config (db path, log level, etc.).

---

## Context: current domain + tiers
Pipelines currently include:
- `finra.otc_transparency.ingest_week`
- `finra.otc_transparency.normalize_week`
- `finra.otc_transparency.aggregate_week`
- `finra.otc_transparency.compute_rolling`
- `finra.otc_transparency.backfill_range`

Tier values in DB include:
- `OTC`
- `NMS_TIER_1`
- `NMS_TIER_2`

Ensure CLI reflects these **exact** values.

---

## Definition of done
- Running a pipeline feels natural and discoverable.
- `spine --help` and `spine run --help` are clean.
- Interactive menu works and is genuinely useful.
- PowerShell users don’t see stderr treated like an error unless it truly is.
- Tests cover parsing + tier behavior + core UI helpers.
