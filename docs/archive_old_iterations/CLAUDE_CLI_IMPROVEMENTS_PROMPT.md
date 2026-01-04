# Spine CLI Modernization — Consolidated Improvements + Claude Implementation Prompt
*(Market Spine — Basic tier, Windows/PowerShell friendly)*

## What’s broken / confusing right now (from real usage)
1. **Duplicate `list list` command**
   - Example: `uv run spine list list --prefix finra.otc_transparency.normalize`
   - This strongly suggests a **Typer/command-group wiring mistake** (e.g., a `list` command group plus a `list` command inside it, or registering the same sub-app twice).

2. **Pipeline params are not ergonomic**
   - Users *expect*:
     - `--week-ending 2025-12-05 --tier OTC`
     - `week_ending=2025-12-05 tier=OTC`
   - Today only `-p key=value` works, which feels “framework-y” instead of “human-y”.

3. **Tier enum mismatch**
   - CLI suggests: `Tier1`, `Tier2`, `OTC`
   - DB actually contains: `NMS_TIER_1`, `NMS_TIER_2`, `OTC`
   - Result: queries fail, or return empty data even though data exists.

4. **PowerShell stderr issue**
   - Structlog output to stderr causes PowerShell to print `NativeCommandError` style noise even on success.
   - This is not a user problem; it’s an output channel choice problem.

5. **Ingest hides “where the file came from”**
   - In Basic tier, `ingest_week` looks like it only needs `week_ending` + `tier`, but *how does it find the CSV*?
   - Even if the system uses a default data directory or manifest lookup, **the CLI should show the resolved file path / source** and allow override.

---

## Design principles to enforce
- **Single source of truth for command behavior**:
  - Put real logic in a “command/service layer” (pure functions returning typed results).
  - CLI becomes a thin renderer (Rich) + input adapter (Typer).
- **Three parameter passing styles all work**:
  1) Friendly options (`--week-ending`, `--tier`, `--file`)
  2) Positional key=value (`week_ending=... tier=...`)
  3) Repeated `-p key=value` (legacy/back-compat)
- **Tier values should match DB**, but provide aliases:
  - Accept `Tier1`/`Tier2` as aliases mapping to `NMS_TIER_1`/`NMS_TIER_2`
  - Always *display* canonical DB values in output.
- **No duplicate help blocks**, no repeated “Options:” sections.
- **Default to stdout for UI + logs** on Windows; optionally support `--log-to stderr` for Unix pipelines.

---

## Concrete UX improvements to implement
### A) Fix the `list list` bug
- Make `spine list` be a single command:
  - `spine list` → pipelines (default)
  - `spine list --prefix finra.otc` → filtered
- If you want more listables later, use distinct subcommands:
  - `spine list pipelines`
  - `spine list captures`
  - `spine list executions`

### B) Make `run` accept friendly pipeline parameters
- Support:
  - `spine run PIPE --week-ending YYYY-MM-DD --tier OTC`
  - `spine run PIPE week_ending=YYYY-MM-DD tier=OTC`
  - `spine run PIPE -p week_ending=YYYY-MM-DD -p tier=OTC`
- Merge rules (deterministic):
  - `--options` override positional `key=value`, which override `-p`.
  - Conflicts should produce a helpful error: *what conflicted + how to fix*.

### C) Add `--help-params` that actually helps
- It should show:
  - required vs optional params
  - types / allowed enums
  - examples
- Use the pipeline registry metadata as the source of truth.

### D) Fix tier handling everywhere
- Update the CLI tier enum to canonical DB values:
  - `OTC`, `NMS_TIER_1`, `NMS_TIER_2`
- Add aliases:
  - `Tier1` → `NMS_TIER_1`
  - `Tier2` → `NMS_TIER_2`
- Ensure `spine query symbols --tier NMS_TIER_1` works and returns data when present.

### E) Ingest visibility + override
For Basic tier (local CSV ingestion):
- Add `--file` / `--file-path` option to `ingest_week` **and show what file is used**:
  - If user passes `--file`, use it.
  - Else resolve from configured data directory + naming convention **or** manifest lookup.
- Print a small “Resolved Inputs” panel before execution:
  - pipeline name
  - week_ending, tier
  - resolved file path (or “download URL” in the future)
  - captured_at (when available)
- Add `spine data` (or `spine list captures`) to show what’s available:
  - Weeks/tiers present in raw table
  - File paths known in manifest (if tracked)
  - Optional “missing file” hints

Future-proofing for Intermediate+ (API download):
- Keep the CLI contract: `--week-ending` + `--tier` is enough **but still show**:
  - FINRA endpoint + query params that will be used
  - download target path
  - checksum/size (if available)

### F) Logging defaults that don’t scare PowerShell users
- Default:
  - Rich UI to stdout
  - Structlog to stdout
- Provide knobs:
  - `--quiet`: UI only summary
  - `--verbose`: show logs inline
  - `--log-format [pretty|json]`
  - `--log-to [stdout|stderr|file]` (file optional)
- Also: do not log at `error` level for normal “skipped already aggregated” flows.

### G) Rich “bells and whistles” that actually help
- Phase-based progress:
  - Validate → Load → Compute → Persist
- Clean error panels with actionable hints (missing params, invalid tier, file not found, etc.)
- `--dry-run` for every pipeline:
  - prints resolved params + what would run
- Optional: interactive prompts for missing params:
  - `spine run PIPE --prompt` (or auto-prompt if running with no params)

---

## Claude Implementation Prompt (copy/paste)
You are working in `market-spine-basic` (Basic tier, SQLite). Redo the CLI implementation to be modern, intuitive, and Windows/PowerShell friendly.

**Primary goals**
1) Fix the `list list` bug so `uv run spine list` works (no duplicate command name).
2) Make pipeline parameters work in THREE ways:
   - friendly options like `--week-ending 2025-12-05 --tier OTC`
   - positional `key=value` args
   - repeated `-p key=value` (backward compatible)
3) Fix tier enums to match DB values: `OTC`, `NMS_TIER_1`, `NMS_TIER_2`, but accept aliases `Tier1`, `Tier2`.
4) Fix PowerShell output: logs/UI must default to stdout (no false NativeCommandError noise).
5) Improve ingest visibility: `ingest_week` must accept `--file` override and always display the resolved file path/source before running.

**Constraints**
- Keep the dispatcher/runner interfaces stable.
- Avoid duplicating business logic: create a shared command/service layer that CLI calls.
- Keep existing tests passing; add focused CLI param parsing tests.

**Deliverables**
- Updated CLI module organization (Typer + Rich).
- A robust param parser/merger with deterministic precedence and great error messages.
- Updated `query` commands with correct tier handling and working examples.
- Ingest command shows resolved file path and supports `--file`.
- Updated README CLI examples (remove any `list list` mistakes).
- Add/adjust tests: param parsing, tier alias mapping, and a couple integration CLI tests if feasible.

**Acceptance tests (must pass)**
- `uv run spine --version`
- `uv run spine list --prefix finra.otc_transparency`
- `uv run spine run finra.otc_transparency.normalize_week --week-ending 2025-12-05 --tier OTC`
- `uv run spine run finra.otc_transparency.normalize_week week_ending=2025-12-05 tier=OTC`
- `uv run spine query symbols --week 2025-12-19 --tier NMS_TIER_1 --top 10`
- PowerShell: no NativeCommandError noise on success (default logging not on stderr)
- `ingest_week` shows the resolved file path (or download URL in future) before execution
