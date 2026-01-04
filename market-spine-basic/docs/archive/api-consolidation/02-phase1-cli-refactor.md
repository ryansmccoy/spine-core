# Phase 1: CLI → Command Refactor

> Status: 🔴 Not Started | Priority: HIGH

## Goal

Make CLI a thin adapter over the command layer, eliminating duplicate logic.

## Files Affected

| File | Change | Status |
|------|--------|--------|
| `cli/commands/query.py` | Replace raw SQL with `QueryWeeksCommand`, `QuerySymbolsCommand` | ⬜ Not Started |
| `cli/commands/list_.py` | Replace `list_pipelines()` with `ListPipelinesCommand` | ⬜ Not Started |
| `cli/commands/run.py` | Replace `Dispatcher` calls with `RunPipelineCommand` | ⬜ Not Started |

## What Changes

- CLI functions become: parse args → build Request → call Command → format Result
- Error handling moves from try/catch around framework calls to checking `Result.success`
- Tier normalization uses `TierNormalizer` (already exists in services)

## What Does NOT Change

- CLI-specific concerns remain in CLI:
  - Typer decorators and argument parsing
  - Rich table formatting and progress indicators
  - Interactive prompts and confirmations
  - Console output styling
- Commands remain sync (no async changes)
- No new abstractions introduced

## Why This Phase Exists

Without this, CLI and API will drift. Bug fixes or behavior changes require editing two places. This is the highest-risk maintenance burden.

## Implementation Pattern

```python
# BEFORE (direct framework call)
def query_weeks(tier: str, limit: int) -> None:
    normalized_tier = normalize_tier(tier)
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT ...", (normalized_tier, limit))
    # format and print

# AFTER (via command)
def query_weeks(tier: str, limit: int) -> None:
    command = QueryWeeksCommand()
    result = command.execute(QueryWeeksRequest(tier=tier, limit=limit))
    
    if not result.success:
        render_error_panel(result.error.code.value, result.error.message)
        raise typer.Exit(1)
    
    # format and print result.weeks
```

---

## TODO

- [ ] Refactor `cli/commands/query.py` to use `QueryWeeksCommand`
- [ ] Refactor `cli/commands/query.py` to use `QuerySymbolsCommand`
- [ ] Refactor `cli/commands/list_.py` to use `ListPipelinesCommand`
- [ ] Refactor `cli/commands/run.py` to use `RunPipelineCommand`
- [ ] Verify CLI behavior unchanged after refactor
- [ ] Run existing CLI tests to confirm no regressions
