# Cross-Domain Dependency Fitness Test

> **Scenario**: FINRA OTC depends on Exchange Calendar for `otc_volume_per_trading_day` calculation.

---

## Part 1 — Dependency Modeling

### Domain Dependency Graph

```
┌──────────────────────────┐
│  reference.exchange_     │
│  calendar                │
│  (upstream)              │
│                          │
│  - holidays table        │
│  - trading_days table    │
└────────────┬─────────────┘
             │
             │ depends on
             ▼
┌──────────────────────────┐
│  finra.otc_transparency  │
│  (downstream)            │
│                          │
│  - symbol_summary table  │
│  - volume_per_day calc   │
└──────────────────────────┘
```

### Dependency Contract

| Aspect | Specification |
|--------|---------------|
| **Upstream Domain** | `reference.exchange_calendar` |
| **Downstream Domain** | `finra.otc_transparency` |
| **Dependency Type** | Data dependency (read-only) |
| **Required Tables** | `reference_exchange_calendar_holidays` |
| **Join Key** | `week_ending` → derive trading days in that week |
| **Exchange Assumption** | XNYS (NYSE) — all FINRA OTC data uses NYSE calendar |

### Timing Contract

| Question | Answer |
|----------|--------|
| Must upstream be loaded first? | **Yes** — trading days required for normalization |
| What if upstream is missing? | Calc fails with clear error message |
| Can downstream run independently? | Yes, for non-normalized calcs |
| Backfill order? | Calendar first, then FINRA calcs |

### Dependency Strictness

```
STRICT: volume_per_trading_day requires calendar data
        → Fails if calendar not loaded for that year

OPTIONAL: Other FINRA calcs (rolling, venue_share) 
          → Don't need calendar, work independently
```

### Key Design Decision

**The calculation owns its dependencies, not the pipeline.**

```python
# ❌ BAD - Pipeline hardcodes order
def run_all():
    run_pipeline("reference.exchange_calendar.ingest_year")
    run_pipeline("finra.otc_transparency.compute_volume_per_day")  # Order in code

# ✅ GOOD - Calculation declares dependencies, fails clearly if missing
class VolumePerDayCalc:
    def run(self, week_ending: date):
        holidays = self._load_holidays(week_ending.year)
        if holidays is None:
            raise DependencyMissingError(
                f"Exchange calendar for {week_ending.year} not loaded. "
                f"Run: reference.exchange_calendar.ingest_year --year {week_ending.year}"
            )
        # ... proceed with calculation
```

---

## Part 2 — Execution Ordering Design

### Principle: Declare Dependencies at Calc Level

Each calculation that needs cross-domain data should:
1. **Declare** what it needs (domain, table, key)
2. **Check** if dependency is satisfied
3. **Fail fast** with actionable error if not

### Implementation Approach

```python
@dataclass
class DomainDependency:
    """Declares a dependency on another domain's data."""
    domain: str
    table: str
    key_column: str
    required: bool = True
    error_hint: str = ""

class VolumePerTradingDayCalc:
    """Calc with explicit dependency declaration."""
    
    DEPENDENCIES = [
        DomainDependency(
            domain="reference.exchange_calendar",
            table="reference_exchange_calendar_holidays",
            key_column="year",
            required=True,
            error_hint="Run: spine run reference.exchange_calendar.ingest_year --year {year}",
        ),
    ]
    
    def check_dependencies(self, year: int) -> list[str]:
        """Check if all dependencies are satisfied. Returns list of errors."""
        errors = []
        for dep in self.DEPENDENCIES:
            if not self._has_data(dep, year):
                errors.append(dep.error_hint.format(year=year))
        return errors
```

### Execution Order is NOT Hardcoded

The pipeline for `volume_per_trading_day` does NOT call the calendar pipeline.
Instead:
1. User runs calendar ingest (once per year)
2. User runs FINRA ingest (weekly)
3. User runs volume_per_day calc (checks dependencies, fails if missing)

This keeps pipelines independent while making dependencies explicit.

---

## Part 3 — Replay & Backfill Semantics

### Replay Guarantee

**Re-running FINRA does NOT re-run Exchange Calendar.**

Each domain tracks its own manifest independently:
- `core_manifest` with `domain="finra.otc_transparency"`
- `core_manifest` with `domain="reference.exchange_calendar"`

When FINRA pipeline runs, it only checks/updates FINRA manifest entries.

### Backfill Guarantee

**Backfilling Calendar updates downstream calcs correctly.**

Scenario:
1. Run FINRA ingest for week 2025-01-10 (calendar exists)
2. Calendar is updated (holiday correction)
3. Re-run FINRA volume_per_day calc → picks up new calendar data

The calc always reads LATEST calendar data, not a snapshotted version.

### Capture ID Semantics

- FINRA `capture_id` reflects FINRA data capture time
- Calendar `capture_id` reflects calendar data capture time
- Cross-domain calc uses FINRA `capture_id` (it's a FINRA output)
- Calc stores `calendar_capture_id` as audit metadata

---

## Part 4 — Findings

### ✅ What Was Easy

1. **Pure calculation pattern scales well**
   
   The cross-domain calculation is a pure function:
   ```python
   def compute_volume_per_trading_day(
       symbol_rows: Sequence[SymbolAggregateRow],  # FINRA data
       holidays: set[date],                         # Calendar data
   ) -> list[VolumePerTradingDayRow]:
   ```
   
   - No database in the function
   - Caller loads dependencies explicitly
   - Easy to test with mock data
   - Deterministic by construction

2. **Dependency checking is straightforward**
   
   A simple `check_calendar_dependency()` function provides:
   - Clear pass/fail check before computation
   - Actionable error messages with remediation steps
   - No magic discovery or reflection

3. **Pipeline isolation works**
   
   - FINRA pipeline doesn't call calendar pipeline
   - Each domain has its own manifest entries
   - Re-running FINRA has no effect on calendar

4. **Testing cross-domain is easy**
   
   Since the calc is pure, tests just pass in data:
   ```python
   results = compute_volume_per_trading_day(symbol_rows, holidays)
   assert results[0].trading_days == 5
   ```

### ⚠️ What Was Awkward

1. **No standard "dependency declaration" pattern**
   
   Each pipeline defines its own `DEPENDENCIES` attribute manually:
   ```python
   DEPENDENCIES = [
       {"domain": "reference.exchange_calendar", "table": "...", "required": True}
   ]
   ```
   
   This works but is ad-hoc. There's no framework enforcement.

2. **Dependency loading is boilerplate**
   
   Every cross-domain pipeline must:
   ```python
   # Step 1: Check dependencies
   errors = check_calendar_dependency(conn, year)
   if errors:
       return PipelineResult(status=FAILED, error=errors[0])
   
   # Step 2: Load dependencies
   holidays = load_holidays_for_year(conn, year)
   
   # Step 3: Do computation
   ...
   ```
   
   This is ~15 lines of boilerplate per cross-domain calc.

3. **Year extraction from week_ending**
   
   The calculation needs to know which year's calendar to use:
   ```python
   year = week_ending.value.year
   holidays = load_holidays_for_year(conn, year)
   ```
   
   For weeks that span year boundaries (Dec 29 → Jan 2), this is ambiguous.
   Current solution: Use the week_ending year. This works for FINRA (week_ending is Friday).

### 🔮 Abstraction Candidates

| Abstraction | Promote? | Notes |
|-------------|----------|-------|
| `DomainDependency` dataclass | Maybe | Standard way to declare dependencies |
| `check_dependency(conn, dep)` | Maybe | Generic dependency checker |
| `DependencyMissingError` | Maybe | Standard error for missing dependencies |
| Dependency loading helpers | No | Too domain-specific |

### 🚫 Should NOT Generalize Yet

| Pattern | Reason to Wait |
|---------|----------------|
| Automatic dependency resolution | Adds magic, hides execution order |
| Pipeline chaining/orchestration | Better to keep explicit in user scripts |
| Cross-domain manifest tracking | Each domain should own its manifest |
| Shared calendar across all domains | Not all domains use NYSE calendar |

### Summary Metrics

| Metric | Value |
|--------|-------|
| New calculation lines | ~100 |
| New pipeline lines | ~150 |
| New test lines | ~350 |
| Cross-domain tests | 17 |
| Total tests passing | 213 |

### Key Insight

**The architecture handles cross-domain dependencies well because:**

1. **Dependencies are data, not orchestration** — The calc receives holidays as a parameter, not by calling another pipeline.

2. **Failure is explicit** — Missing dependencies fail fast with clear messages.

3. **Order is external** — The user/orchestrator decides order, not the pipeline.

4. **Pure functions compose** — `trading_days_between()` is imported and called, not discovered.

**What we did NOT need:**
- Dependency injection framework
- Pipeline orchestration layer
- Graph-based execution engine
- Automatic dependency resolution

**Simple explicit code works.**
