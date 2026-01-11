# CLI Modernization Implementation Plan

## Executive Summary

This document outlines the complete redesign of the `spine` CLI to address usability issues and create a modern, intuitive command-line experience using Typer, Rich, and Questionary.

## Current Problems

### 1. Confusing Parameter Passing
- ❌ `--week-ending 2025-12-05 --tier OTC` fails
- ❌ `week_ending=2025-12-05 tier=OTC` fails  
- ✅ Only `-p key=value` works (awkward)

### 2. Tier Enum Mismatch
- CLI offers: `Tier1`, `Tier2`, `OTC`
- DB contains: `NMS_TIER_1`, `NMS_TIER_2`, `OTC`
- Result: Queries fail or return no data

### 3. PowerShell stderr Issues
- Logs go to stderr → PowerShell treats as errors
- Shows confusing `NativeCommandError` messages

### 4. Duplicated Help Text
- `spine run --help` shows repeated "Options:" blocks

---

## Proposed Solution

### Technology Stack
- **Typer** (>= 0.9.0) - Modern Click-based CLI framework
- **Rich** (already present) - Beautiful terminal output
- **Questionary** (>= 2.0.0) - Interactive prompts and menus

### Core Principles
1. **Three ways to pass parameters** (all work!)
2. **Aligned tier enums** (match actual DB values)
3. **Dual-channel output** (Rich UI to stdout, logs configurable)
4. **Interactive mode** when no args provided
5. **Phase-based progress** (not percentages)

---

## New CLI Command Examples

### Version & Help
```bash
$ uv run spine --version
spine, version 0.1.0

$ uv run spine --help
# Clean, organized help with command groups
```

### List Pipelines
```bash
# All pipelines
$ uv run spine list

# Filter by prefix
$ uv run spine list --prefix finra.otc
```

### Run Pipelines - THREE WAYS!

**Way 1: Friendly Options (NEW!)**
```bash
$ uv run spine run finra.otc_transparency.normalize_week \
    --week-ending 2025-12-05 \
    --tier OTC
```

**Way 2: key=value Args (NEW!)**
```bash
$ uv run spine run finra.otc_transparency.normalize_week \
    week_ending=2025-12-05 tier=OTC
```

**Way 3: -p Flag (EXISTING - still works!)**
```bash
$ uv run spine run finra.otc_transparency.normalize_week \
    -p week_ending=2025-12-05 \
    -p tier=OTC
```

**Additional Run Options:**
```bash
# Show parameter help
$ uv run spine run finra.otc_transparency.ingest_week --help-params

# Dry run (show what would execute)
$ uv run spine run finra.otc_transparency.normalize_week \
    --week-ending 2025-12-05 --tier OTC --dry-run

# Quiet mode (only show summary)
$ uv run spine run finra.otc_transparency.normalize_week \
    --week-ending 2025-12-05 --tier OTC --quiet

# JSON logs for machines
$ uv run spine run finra.otc_transparency.normalize_week \
    --week-ending 2025-12-05 --tier OTC --log-format json

# Debug mode
$ uv run spine run finra.otc_transparency.normalize_week \
    --week-ending 2025-12-05 --tier OTC --log-level debug
```

### Query Commands - FIXED TIER ENUM!

```bash
# List all weeks
$ uv run spine query weeks

# Query symbols with ACTUAL tier values
$ uv run spine query symbols --week 2025-12-19 --tier NMS_TIER_1 --top 10

# Now accepts: OTC, NMS_TIER_1, NMS_TIER_2 ✅
```

### Database Commands

```bash
# Initialize
$ uv run spine db init

# Reset with confirmation
$ uv run spine db reset

# Reset without confirmation
$ uv run spine db reset --yes
```

### Verify Commands

```bash
$ uv run spine verify tables
$ uv run spine verify data
```

### Interactive Mode (NEW!)

```bash
# Run with no args to open interactive menu
$ uv run spine

# Or explicitly
$ uv run spine ui
```

**Interactive Menu:**
```
? What would you like to do?
  ❯ Run pipeline
    Query data
    Verify database
    Initialize/reset database
    Show pipelines
    Exit
```

### Bonus Commands

```bash
# Health check
$ uv run spine doctor

# Show configuration
$ uv run spine config
```

---

## Expected Output Examples

### Running a Pipeline

```
$ uv run spine run finra.otc_transparency.normalize_week --week-ending 2025-12-05 --tier OTC

╭─ Pipeline Execution ─────────────────────────────────────╮
│ Pipeline: finra.otc_transparency.normalize_week          │
│ Week: 2025-12-05 | Tier: OTC                            │
╰──────────────────────────────────────────────────────────╯

⠹ Phase 1/4: Validating inputs...                      [0.1s]
✓ Phase 1/4: Validated                                 [0.2s]
⠹ Phase 2/4: Loading raw data...                       [0.3s]
✓ Phase 2/4: Loaded 50 rows                            [0.5s]
⠹ Phase 3/4: Normalizing records...                    [0.6s]
✓ Phase 3/4: Validated 50 records                      [0.8s]
⠹ Phase 4/4: Persisting results...                     [1.0s]
✓ Phase 4/4: Complete                                  [1.2s]

╭─ Summary ────────────────────────────────────────────────╮
│ Status: ✓ Completed                                      │
│ Duration: 1.2s                                           │
│ Capture ID: finra.otc_transparency:OTC:2025-12-05:2c6b0a │
│                                                          │
│ Metrics:                                                 │
│   • Accepted: 50                                         │
│   • Rejected: 0                                          │
╰──────────────────────────────────────────────────────────╯
```

### Error Output (User Friendly)

```
$ uv run spine run finra.otc_transparency.normalize_week --week-ending 2025-12-05

╭─ Error ──────────────────────────────────────────────────╮
│ Invalid parameters                                       │
│                                                          │
│ Missing required parameters:                             │
│   • tier                                                 │
│                                                          │
│ Run with --help-params to see all parameters            │
╰──────────────────────────────────────────────────────────╯
```

### Dry Run Output

```
$ uv run spine run finra.otc_transparency.normalize_week \
    --week-ending 2025-12-05 --tier OTC --dry-run

╭─ Dry Run ────────────────────────────────────────────────╮
│ Pipeline: finra.otc_transparency.normalize_week          │
│                                                          │
│ Resolved Parameters:                                     │
│   • week_ending: 2025-12-05                              │
│   • tier: OTC                                            │
│                                                          │
│ Would execute with these parameters.                     │
│ (Use without --dry-run to actually run)                  │
╰──────────────────────────────────────────────────────────╯
```

---

## File Structure

### New CLI Module Organization

```
market-spine-basic/src/market_spine/
├── cli/
│   ├── __init__.py           # Main CLI app, version, callback
│   ├── params.py             # Parameter parsing utilities
│   ├── ui.py                 # Rich UI components (panels, progress, etc.)
│   ├── commands/
│   │   ├── __init__.py
│   │   ├── run.py           # Pipeline execution
│   │   ├── query.py         # Query commands (weeks, symbols)
│   │   ├── db.py            # Database commands
│   │   ├── verify.py        # Verification commands
│   │   └── doctor.py        # Health check command
│   └── interactive/
│       ├── __init__.py
│       ├── menu.py          # Main interactive menu
│       └── prompts.py       # Parameter prompts
├── cli.py                    # DEPRECATED - will import from cli/ for compatibility
└── ...existing files...
```

---

## Dependencies to Add

### pyproject.toml Changes

```toml
dependencies = [
    "click>=8.1.0",           # Keep for now (Typer uses Click)
    "typer>=0.9.0",           # NEW - Modern CLI framework
    "questionary>=2.0.0",     # NEW - Interactive prompts
    "pydantic>=2.0.0",
    "pydantic-settings>=2.0.0",
    "python-dotenv>=1.0.0",
    "structlog>=24.0.0",
    "rich>=13.0.0",           # Already present
    "spine-core",
    "spine-domains",
]
```

---

## Implementation Plan (Ordered Checklist)

### Phase 1: Dependencies & Structure
- [ ] 1.1 Update `pyproject.toml` with new dependencies
- [ ] 1.2 Create `src/market_spine/cli/` package structure
- [ ] 1.3 Create empty module files with docstrings

### Phase 2: Core Infrastructure
- [ ] 2.1 Build parameter parsing layer (`params.py`)
  - Parse `-p key=value`
  - Parse `key=value` args
  - Parse friendly options (`--week-ending`, `--tier`, `--file`)
  - Validate types and required params
- [ ] 2.2 Build Rich UI components (`ui.py`)
  - Phase progress spinner/tracker
  - Summary panel generator
  - Error panel formatter
- [ ] 2.3 Create tier enum that matches DB values
  - `OTC`, `NMS_TIER_1`, `NMS_TIER_2`

### Phase 3: Command Implementation
- [ ] 3.1 Implement `cli/__init__.py` (main app)
  - Typer app setup
  - Version command
  - Default callback (interactive mode trigger)
- [ ] 3.2 Implement `commands/run.py`
  - Accept pipeline name
  - Parse parameters (all three ways)
  - `--help-params` flag
  - `--dry-run` flag
  - `--quiet` flag
  - `--log-format` and `--log-level`
  - Call dispatcher with phase-based UI
- [ ] 3.3 Implement `commands/query.py`
  - `query weeks` command
  - `query symbols` command with fixed tier enum
- [ ] 3.4 Implement `commands/db.py`
  - `db init` command
  - `db reset` command with confirmation
- [ ] 3.5 Implement `commands/verify.py`
  - `verify tables` command
  - `verify data` command
- [ ] 3.6 Implement `commands/doctor.py`
  - Check Python version
  - Check dependencies
  - Check DB access
  - Check schema present

### Phase 4: Interactive Mode
- [ ] 4.1 Build main menu (`interactive/menu.py`)
  - Menu options (run, query, verify, etc.)
- [ ] 4.2 Build parameter prompts (`interactive/prompts.py`)
  - Week-ending date picker with validation
  - Tier selector
  - File path picker
  - Pipeline fuzzy search

### Phase 5: Logging & Output
- [ ] 5.1 Configure dual-channel logging
  - Rich UI to stdout
  - Structured logs to stdout by default (not stderr)
  - `--log-to stderr` option for unix pipelines
- [ ] 5.2 Fix exception mapping
  - Clear distinction between param errors, pipeline not found, execution errors

### Phase 6: Migration & Compatibility
- [ ] 6.1 Update `cli.py` to import from new `cli/` module
- [ ] 6.2 Ensure backward compatibility with existing `-p` syntax
- [ ] 6.3 Update entry point in `pyproject.toml` if needed

### Phase 7: Testing
- [ ] 7.1 Write parameter parsing tests
  - Test `-p key=value`
  - Test `key=value` args
  - Test friendly options
  - Test validation errors
- [ ] 7.2 Write tier enum tests
  - Verify accepted values
  - Test query filtering
- [ ] 7.3 Write help text tests
  - Ensure no duplication
  - Validate structure
- [ ] 7.4 Write integration tests
  - Test full command execution
  - Verify output format

### Phase 8: Documentation & Verification
- [ ] 8.1 Update README with new CLI examples
- [ ] 8.2 Add migration guide for existing users
- [ ] 8.3 Run all deliverable commands:
  - `uv run spine --version`
  - `uv run spine list`
  - `uv run spine db init`
  - `uv run spine run finra.otc_transparency.ingest_week --file ... --tier OTC`
  - `uv run spine query weeks`
  - `uv run spine query symbols --week ... --tier NMS_TIER_1 --top 10`

---

## Key Implementation Details

### Parameter Parsing Architecture

```python
# params.py
class ParamParser:
    """Parse parameters from multiple sources and validate."""
    
    def parse(
        self,
        param_flags: list[str],      # from -p key=value
        extra_args: list[str],         # positional key=value
        week_ending: str | None,       # from --week-ending
        tier: str | None,              # from --tier
        file: str | None,              # from --file
        **other_options                # other friendly options
    ) -> dict[str, Any]:
        """Merge and validate all parameter sources."""
        
    def validate_required(self, pipeline_name: str, params: dict):
        """Check required params are present."""
        
    def validate_types(self, params: dict):
        """Validate parameter types (dates, enums, paths)."""
```

### Rich UI Components

```python
# ui.py
class PipelineProgress:
    """Phase-based progress tracker."""
    
    def start_phase(self, phase: int, total: int, description: str):
        """Start a new phase with spinner."""
        
    def complete_phase(self, phase: int, total: int, message: str):
        """Mark phase complete."""
        
class SummaryPanel:
    """Generate summary panel."""
    
    def render(self, status: str, duration: float, metrics: dict) -> Panel:
        """Render summary panel."""
```

### Tier Enum Alignment

```python
# In relevant modules, use actual DB values
TIER_CHOICES = ["OTC", "NMS_TIER_1", "NMS_TIER_2"]

# Typer will auto-generate from this
TierEnum = Enum("TierEnum", {tier: tier for tier in TIER_CHOICES})
```

---

## Migration Path

### For Existing Users

**Old command:**
```bash
spine run finra.otc_transparency.normalize_week -p week_ending=2025-12-05 -p tier=OTC
```

**Still works! Plus new options:**
```bash
# More ergonomic
spine run finra.otc_transparency.normalize_week --week-ending 2025-12-05 --tier OTC

# Even simpler
spine run finra.otc_transparency.normalize_week week_ending=2025-12-05 tier=OTC
```

**Tier values updated:**
- Old: `--tier Tier1` (didn't work anyway)
- New: `--tier NMS_TIER_1` (matches DB!)

---

## Testing Strategy

### Unit Tests
- `test_cli_params.py` - Parameter parsing logic
- `test_cli_ui.py` - UI component rendering
- `test_tier_enum.py` - Tier enum validation

### Integration Tests
- `test_cli_run.py` - Pipeline execution commands
- `test_cli_query.py` - Query commands
- `test_cli_interactive.py` - Interactive mode (if feasible)

### Manual Verification
- All commands from deliverables list
- PowerShell output (ensure no stderr errors)
- Interactive mode usability

---

## Success Criteria

### Must Have
- ✅ All three parameter passing methods work
- ✅ Tier enum matches DB values exactly
- ✅ PowerShell shows no false errors
- ✅ Help text is clean and non-duplicated
- ✅ Interactive mode is functional
- ✅ Backward compatibility maintained

### Nice to Have
- ✅ `doctor` command works
- ✅ `config` command works
- ✅ Shell completion installable
- ✅ All tests passing

---

## Timeline Estimate

- **Phase 1-2**: 2-3 hours (dependencies, structure, infrastructure)
- **Phase 3**: 4-5 hours (command implementation)
- **Phase 4**: 2-3 hours (interactive mode)
- **Phase 5**: 1-2 hours (logging/output)
- **Phase 6**: 1 hour (migration)
- **Phase 7**: 2-3 hours (testing)
- **Phase 8**: 1-2 hours (docs & verification)

**Total: 13-19 hours of development work**

---

## Risks & Mitigation

### Risk 1: Breaking Existing Users
**Mitigation:** Maintain full backward compatibility with `-p` syntax

### Risk 2: Typer Learning Curve
**Mitigation:** Typer is well-documented and similar to Click

### Risk 3: Interactive Mode Complexity
**Mitigation:** Start with basic menu, enhance later

### Risk 4: Testing Interactive Features
**Mitigation:** Focus on unit testing components, manual test interactive flow

---

## Next Steps

1. **Review this plan** - Confirm approach and scope
2. **Install dependencies** - `uv add typer questionary`
3. **Begin Phase 1** - Create module structure
4. **Iterate through phases** - Build, test, verify
5. **Document changes** - Update README with examples
6. **Release** - Tag version with breaking changes noted

---

## Questions for Review

1. Is the scope acceptable (13-19 hours)?
2. Should we implement all bonus features (doctor, config, completion)?
3. Any specific UX preferences for interactive mode?
4. Should we maintain the old `cli.py` or fully migrate?
5. Any additional commands needed?

---

*Document Version: 1.0*  
*Created: January 3, 2026*  
*Status: Ready for Review*
