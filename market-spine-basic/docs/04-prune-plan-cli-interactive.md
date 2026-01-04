# Prune Plan — CLI Interactive Module

> Generated: January 2026 | Post Phase 1-4 Consolidation

This document analyzes the `cli/interactive/` folder and recommends what stays, goes, or changes.

---

## Current State

### Files

```
cli/interactive/
├── __init__.py      # Exports run_interactive_menu
├── menu.py          # 313 lines - Main menu loop with 7 menu options
└── prompts.py       # 83 lines - Pipeline parameter prompting
```

### Functionality

| Menu Option | Implementation | Uses Commands? |
|-------------|----------------|----------------|
| Run a pipeline | `run_pipeline_interactive()` | ❌ subprocess |
| List available pipelines | `list_pipelines_interactive()` | ❌ subprocess |
| Query data | `query_data_interactive()` | ❌ subprocess |
| Verify database | `verify_interactive()` | ❌ subprocess |
| Database operations | `database_operations_interactive()` | ❌ subprocess |
| Health check | `run_health_check_interactive()` | ❌ subprocess |
| Exit | Built-in | N/A |

### Dependencies

```python
# menu.py imports:
import questionary
from spine.framework.registry import list_pipelines  # ⚠️ Direct framework
from ..console import TIER_VALUES, console           # ⚠️ Uses shim
from ..params import ParamParser
from .prompts import prompt_pipeline_params

# prompts.py imports:
import questionary
from spine.framework.registry import get_pipeline   # ⚠️ Direct framework
from ..console import TIER_VALUES, console          # ⚠️ Uses shim
```

---

## Analysis

### Why Subprocess Pattern?

The interactive module shells out to CLI instead of calling commands directly:

```python
def run_pipeline_interactive():
    cmd_parts = ["uv", "run", "spine", "run", "run", pipeline]
    ...
    result = subprocess.run(cmd_parts)
```

**Pros:**
1. ✅ Reuses exact CLI output formatting (Rich panels, tables)
2. ✅ No need to duplicate Rich rendering logic
3. ✅ Guarantees CLI and interactive have identical behavior
4. ✅ Simpler implementation (just build command string)

**Cons:**
1. ❌ Spawns new process for each action (~200ms overhead)
2. ❌ Cannot capture structured results
3. ❌ Harder to test programmatically
4. ❌ Can't handle errors gracefully (only exit code)

### Usage Assessment

**Is interactive mode actively used?**
- No telemetry available
- Likely used for demos and exploration
- Not critical path for automation

**Is it worth refactoring?**
- Current implementation works
- Refactoring would require duplicating Rich rendering
- Low ROI unless interactive becomes primary UX

---

## Recommendation: KEEP with Minor Fixes

### Decision: Keep subprocess pattern

The subprocess pattern is acceptable for a secondary UX mode. Documenting it as intentional is sufficient.

### Required Fixes

#### Fix 1: Remove TIER_VALUES Shim Usage

```python
# menu.py - CHANGE:
# FROM:
from ..console import TIER_VALUES, console

# TO:
from ..console import console, get_tier_values

# AND update usages:
tier = questionary.select(
    "Select tier:",
    choices=get_tier_values(),  # Was: TIER_VALUES
    style=custom_style,
).ask()
```

Same fix needed in `prompts.py`.

#### Fix 2: Add Intent Documentation

Add docstring to `menu.py` explaining the design:

```python
"""
Interactive menu using questionary.

Design Note:
    This module uses subprocess.run() to invoke CLI commands rather than
    calling the command layer directly. This is intentional:
    
    1. Reuses exact CLI output formatting (Rich panels, progress bars)
    2. Ensures CLI and interactive modes have identical behavior
    3. Avoids duplicating Rich rendering logic in interactive
    
    Trade-off: Each action spawns a new process (~200ms overhead).
    This is acceptable for interactive (human-speed) usage.
    
    If structured results are needed (e.g., for TUI), refactor to use
    commands directly and render with Rich.
"""
```

#### Fix 3: Consider Command Layer for Metadata (Optional)

The direct registry imports could be replaced with commands:

```python
# menu.py - CURRENT:
from spine.framework.registry import list_pipelines
all_pipelines = list_pipelines()

# COULD BE:
from market_spine.app.commands.pipelines import ListPipelinesCommand, ListPipelinesRequest
result = ListPipelinesCommand().execute(ListPipelinesRequest())
all_pipelines = [p.name for p in result.pipelines]
```

**Decision:** Optional. Registry access for metadata is low-risk.

---

## What NOT to Do

### ❌ Don't delete interactive module

- It provides value for demos and exploration
- Works correctly
- Low maintenance burden

### ❌ Don't refactor to use commands directly (yet)

- Would require duplicating Rich rendering
- No immediate benefit
- Save for future "interactive 2.0" if needed

### ❌ Don't add more menu options

- Keep interactive scope small
- New features go in CLI/API first

---

## Action Items

| # | Action | Priority | Effort |
|---|--------|----------|--------|
| 1 | Replace TIER_VALUES with get_tier_values() | HIGH | 10 min |
| 2 | Add design intent docstring | MEDIUM | 5 min |
| 3 | Replace registry imports with commands | LOW | 30 min |

---

## Future Considerations

### If interactive becomes primary UX

Refactor to use commands directly:

```python
def run_pipeline_interactive():
    # Prompt for inputs...
    
    # Execute via command
    command = RunPipelineCommand()
    result = command.execute(RunPipelineRequest(
        pipeline=pipeline,
        params=params,
        dry_run=dry_run,
    ))
    
    # Render result with Rich
    if result.success:
        render_summary_panel(result.status, result.duration_seconds, ...)
    else:
        render_error_panel(result.error.code, result.error.message)
```

This would:
- Eliminate process spawn overhead
- Enable structured result handling
- Allow testing without subprocess mocking

### If building a full TUI

Consider `textual` library for Rich-native TUI instead of questionary + subprocess.

---

## Checklist

- [ ] Replace `TIER_VALUES` with `get_tier_values()` in menu.py
- [ ] Replace `TIER_VALUES` with `get_tier_values()` in prompts.py
- [ ] Remove `TIER_VALUES` shim from console.py
- [ ] Add design intent docstring to menu.py
- [ ] Test interactive mode manually
