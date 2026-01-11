# Design Note: Source + Period Symmetry

> **Removing pipeline branching for extensibility axes**

---

## Problem Statement

The ingest pipeline currently has two extensibility violations:

### 1. Source Branching (in `sources.py`)

```python
# create_source() factory - if/else on source_type
if source_type == "file":
    return FileSource(...)
elif source_type == "api":
    return APISource(...)
else:
    raise ValueError(f"Unknown source: {source_type}")
```

**Why this is problematic:**
- Adding S3 source requires editing `create_source()` 
- Factory becomes a god function knowing all source types
- Violates Open-Closed Principle

### 2. Weekly Semantics Hardcoded (in `connector.py`)

```python
def derive_week_ending_from_publish_date(publish_date: date) -> date:
    """
    Rule: week_ending = file_date - 3 days (for Monday publication)
    """
    days_since_friday = (publish_date.weekday() - 4) % 7
    ...
```

**Why this is problematic:**
- Monthly FINRA data would require different derivation logic
- "Friday" and "Monday" are FINRA-weekly-specific
- Pipeline parameter is called `week_ending` but concept is "period_ending"

---

## Solution: Symmetric Registries

### Source Registry (already exists, needs registry pattern)

```python
SOURCE_REGISTRY: dict[str, type[IngestionSource]] = {
    "file": FileSource,
    "api": APISource,
}

def register_source(name: str):
    """Decorator to register a source type."""
    def decorator(cls: type[IngestionSource]) -> type[IngestionSource]:
        SOURCE_REGISTRY[name] = cls
        return cls
    return decorator

def resolve_source(source_type: str, **params) -> IngestionSource:
    """Resolve source by type from registry."""
    if source_type not in SOURCE_REGISTRY:
        raise ValueError(f"Unknown source: {source_type}. Known: {list(SOURCE_REGISTRY.keys())}")
    return SOURCE_REGISTRY[source_type](**params)
```

### Period Registry (new)

```python
PERIOD_REGISTRY: dict[str, type[PeriodStrategy]] = {
    "weekly": WeeklyPeriod,
    "monthly": MonthlyPeriod,
}

def register_period(name: str):
    """Decorator to register a period strategy."""
    def decorator(cls: type[PeriodStrategy]) -> type[PeriodStrategy]:
        PERIOD_REGISTRY[name] = cls
        return cls
    return decorator

def resolve_period(period_type: str, **params) -> PeriodStrategy:
    """Resolve period by type from registry."""
    if period_type not in PERIOD_REGISTRY:
        raise ValueError(f"Unknown period: {period_type}. Known: {list(PERIOD_REGISTRY.keys())}")
    return PERIOD_REGISTRY[period_type](**params)
```

---

## Period Strategy Protocol

```python
class PeriodStrategy(Protocol):
    """Strategy for temporal period semantics."""
    
    @property
    def period_type(self) -> str:
        """Return period type identifier (weekly, monthly, etc.)."""
        ...
    
    def derive_period_end(self, publish_date: date) -> date:
        """Derive period end date from publication date."""
        ...
    
    def validate_date(self, period_end: date) -> bool:
        """Validate that date is a valid period end."""
        ...
    
    def format_for_filename(self, period_end: date) -> str:
        """Format period end for filename construction."""
        ...
    
    def format_for_display(self, period_end: date) -> str:
        """Human-readable period identifier."""
        ...
```

### WeeklyPeriod Implementation

```python
@register_period("weekly")
class WeeklyPeriod(PeriodStrategy):
    """FINRA weekly data semantics (Mon publish → Fri period end)."""
    
    period_type = "weekly"
    
    def derive_period_end(self, publish_date: date) -> date:
        """Derive Friday from Monday publication date."""
        days_since_friday = (publish_date.weekday() - 4) % 7
        if days_since_friday == 0:
            days_since_friday = 7
        return publish_date - timedelta(days=days_since_friday)
    
    def validate_date(self, period_end: date) -> bool:
        """Week ending must be Friday."""
        return period_end.weekday() == 4  # Friday
    
    def format_for_filename(self, period_end: date) -> str:
        return period_end.isoformat()
    
    def format_for_display(self, period_end: date) -> str:
        return f"Week ending {period_end.isoformat()}"
```

### MonthlyPeriod Implementation

```python
@register_period("monthly")
class MonthlyPeriod(PeriodStrategy):
    """FINRA monthly data semantics (1st of month publish → last day prev month)."""
    
    period_type = "monthly"
    
    def derive_period_end(self, publish_date: date) -> date:
        """Derive month end from publication date."""
        # Monthly data published ~1st of month for previous month
        first_of_current = publish_date.replace(day=1)
        last_of_prev = first_of_current - timedelta(days=1)
        return last_of_prev
    
    def validate_date(self, period_end: date) -> bool:
        """Month ending must be last day of month."""
        next_day = period_end + timedelta(days=1)
        return next_day.day == 1
    
    def format_for_filename(self, period_end: date) -> str:
        return period_end.strftime("%Y-%m")
    
    def format_for_display(self, period_end: date) -> str:
        return f"Month ending {period_end.strftime('%B %Y')}"
```

---

## Refactored Pipeline Shape

```python
def run(self) -> PipelineResult:
    # Resolve strategies via registries (no branching)
    source = resolve_source(
        self.params.get("source_type", "file"),
        **self._source_params()
    )
    period = resolve_period(
        self.params.get("period_type", "weekly"),
        **self._period_params()
    )
    
    # Fetch content (source-agnostic)
    payload = source.fetch()
    
    # Derive period end from source metadata (period-agnostic)
    period_end = period.derive_period_end(payload.metadata.publish_date)
    
    # Parse and write (unchanged)
    records = parse_finra_content(payload.content)
    ...
```

---

## Symmetry Summary

| Axis | Abstraction | Registry | Factory |
|------|-------------|----------|---------|
| **Source** | `IngestionSource` | `SOURCE_REGISTRY` | `resolve_source()` |
| **Period** | `PeriodStrategy` | `PERIOD_REGISTRY` | `resolve_period()` |

Both follow identical patterns:
1. Protocol/ABC defines interface
2. Registry holds implementations
3. Decorator for registration
4. Resolver function for lookup

---

## Extensibility Guarantees

After this refactor:

| Scenario | Before | After |
|----------|--------|-------|
| Add S3 source | Edit `create_source()` | Add `@register_source("s3")` class |
| Add monthly period | Edit connector + pipeline | Add `@register_period("monthly")` class |
| Change weekly logic | Edit `derive_week_ending_from_publish_date()` | Edit `WeeklyPeriod.derive_period_end()` |

**Pipeline code remains unchanged for all extensibility scenarios.**

---

## Assumptions Made

1. **Period is single-valued**: Each ingestion has one period type (not mixed weekly+monthly)
2. **FINRA-specific logic stays in domain**: Period derivation rules are FINRA business logic
3. **Backward compatibility**: `week_ending` parameter still works for weekly (aliased to `period_end`)
4. **Default is weekly**: If `period_type` not specified, assume weekly (current behavior)
