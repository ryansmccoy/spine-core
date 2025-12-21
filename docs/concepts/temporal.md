# spine-core — Temporal Provenance

## Why Temporal Matters

Financial operations move data through multiple handoffs. The same observation
(e.g. Apple's Q3 EPS of $1.52) can be:

- **Announced** on one date (event occurs in the real world)
- **Published** by a vendor minutes later (source makes it available)
- **Ingested** by our operation hours later (we capture it)
- **Effective** for a reporting period that started months earlier (business validity)

Without separating these timestamps, common bugs arise:

- **Look-ahead bias** — a backtest uses data before it was actually available.
- **Stale-data masking** — a correction arrives but the old value is still served.
- **Source-vendor confusion** — Bloomberg publishes before FactSet; treating them
  identically introduces timing errors in multi-source reconciliation.

---

## Definitions

### Valid Time (business axis)

> "When was this fact true in the real world?"

Valid time tracks the period during which a fact is the ground truth —
independent of when our system recorded it. Examples:

- A stock ticker `FB` was valid from IPO until 2022-06-08, then `META` took over.
- An EPS figure is valid for Q3 2025 (the reporting period), not the announcement date.

### Transaction Time (system axis)

> "When did our system record this version?"

Transaction time is set by the database / operation, never by the source.
It enables point-in-time audit queries: "What did our system believe on Jan 15?"

---

## The Four-Timestamp Model (`TemporalEnvelope`)

For operations where vendor timing matters, spine-core provides four timestamps:

| Timestamp | Axis | Question answered |
|---|---|---|
| `event_time` | real world | When did the event happen? |
| `publish_time` | source | When did the source release it? |
| `ingest_time` | system | When did we capture it? |
| `effective_time` | business | When should consumers treat it as valid? (defaults to `event_time`) |

```python
from spine.core.temporal_envelope import TemporalEnvelope

env = TemporalEnvelope(
    event_time=announcement_dt,
    publish_time=vendor_release_dt,
    ingest_time=utc_now(),
    payload={"symbol": "AAPL", "eps": 1.52},
)

# PIT query helpers
env.known_as_of(cutoff)      # was ingest_time <= cutoff?
env.effective_as_of(cutoff)  # was effective_time <= cutoff?
env.published_as_of(cutoff)  # was publish_time <= cutoff?
```

**Evidence:** [`src/spine/core/temporal_envelope.py`](../src/spine/core/temporal_envelope.py) — `class TemporalEnvelope`, docstring

---

## Bi-Temporal Records (`BiTemporalRecord`)

For durable fact tables that need full audit history:

```python
BiTemporalRecord:
  record_id: str          # globally unique
  entity_key: str         # e.g. "AAPL"
  valid_from:  datetime   # business axis start (inclusive)
  valid_to:    datetime   # business axis end   (exclusive, None = current)
  system_from: datetime   # system axis start
  system_to:   datetime   # system axis end     (None = latest version)
  payload: dict
```

Two time axes = four "zones" in time:

```
                     system_from → system_to
                         ↑               ↑
valid_from ──────────────────────────────────────── valid_to
              (V1 recorded)    (V2 corrected)
```

- `valid_to is None` → currently valid in the real world
- `system_to is None` → this is the latest system recording

**Evidence:** [`src/spine/core/temporal_envelope.py`](../src/spine/core/temporal_envelope.py) — `class BiTemporalRecord`

---

## Temporal Diagram

```
Time axis →

Real world:
──────────────────┬─────────────────────────┬────────────────────
                  │ Event happens (Q3 EPS)  │
                  │ event_time              │
                  │                         │ Source publishes
                  │                         │ publish_time
                  │                         │
                  │                         │       We ingest
                  │                         │       ingest_time
                  │                         │
                  │←──── valid_from ──────►│ valid_to (or ∞)
                  │           VALID TIME AXIS               │
                  │                                         │
System:           │  system_from ──────────────────────────► system_to (or ∞)
                  │          TRANSACTION TIME AXIS
```

---

## Four Query Patterns

### 1. As-of Transaction Time ("What did we believe on date X?")

Answer: filter `system_from <= X < system_to` (or `system_to IS NULL` for current).

```sql
SELECT * FROM fact_eps
WHERE entity_key = 'AAPL'
  AND system_from  <= '2025-11-01'
  AND (system_to IS NULL OR system_to > '2025-11-01')
ORDER BY valid_from DESC
LIMIT 1;
```

Useful for: backtesting, audit, compliance ("what did our model see?").

---

### 2. As-of Valid Time ("What was the last reported value as-of period P?")

Answer: filter `valid_from <= P < valid_to`.

```sql
SELECT * FROM fact_eps
WHERE entity_key = 'AAPL'
  AND valid_from  <= '2025-09-30'
  AND (valid_to IS NULL OR valid_to > '2025-09-30')
  AND system_to IS NULL   -- latest recorded version
ORDER BY valid_from DESC
LIMIT 1;
```

Useful for: computing period-end values, financial ratios.

---

### 3. Both Axes ("What did we know on system date S about business period P?")

Answer: combine both axis filters (full bi-temporal PIT query).

```sql
SELECT * FROM fact_eps
WHERE entity_key = 'AAPL'
  AND valid_from  <= '2025-09-30'
  AND (valid_to IS NULL OR valid_to > '2025-09-30')
  AND system_from <= '2025-11-01'
  AND (system_to IS NULL OR system_to > '2025-11-01');
```

Useful for: regulatory reporting ("what was our position, as we knew it, at quarter end?").

---

### 4. Latest ("What is the current best value?")

Answer: both `valid_to IS NULL` and `system_to IS NULL`.

```sql
SELECT * FROM fact_eps
WHERE entity_key = 'AAPL'
  AND valid_to   IS NULL
  AND system_to  IS NULL;
```

Useful for: dashboards, enrichment, entity resolution.

---

## Third Time Axis — When to Add It

Two axes cover ~95 % of use cases. Consider adding a **third axis** only when you
need to model a time dimension that is neither business validity nor when-your-system-
recorded:

| Scenario | Suggested third axis name | Definition |
|---|---|---|
| Multi-scenario forecasting | `scenario_time` | "As-of this forecast run / scenario" |
| Regulatory snapshots | `report_time` | "As of the regulatory reporting date" |
| Multi-vendor reconciliation | `publish_time` | "When the upstream vendor released it" |
| Operation backfill tracking | `process_time` | "When the operation processed the batch" |

**Guidance:** if you already have `TemporalEnvelope` (which includes `publish_time`),
that fourth timestamp can act as a third business axis without adding a full tritemporal
schema. Add a true DB-level third axis only if you need independent query patterns
against it.

**What to call it:** match the consumer's language. Financial services use
`report_date` or `snapshot_date`. Event operations use `process_time`. Keep names
orthogonal: do not name the third axis `created_at` (which implies system time).

---

## `WeekEnding` — Validated Business Calendar

For weekly financial workflows (e.g. FINRA OTC data published every Friday):

```python
from spine.core.temporal import WeekEnding

week = WeekEnding("2025-12-26")        # ✅ Friday
week = WeekEnding("2025-12-25")        # ❌ ValueError (Thursday)
week = WeekEnding.from_any_date(date.today())  # always returns nearest Friday

for w in week.window(6):               # last 6 Fridays
    process_week(w)
```

`WeekEnding` is a frozen dataclass — safe for use as dict key, set element,
or partition column.

**Evidence:** [`src/spine/core/temporal.py`](../src/spine/core/temporal.py) — `class WeekEnding`, manifesto section

---

## Related Modules

| Module | Role |
|---|---|
| `spine.core.temporal_envelope` | `TemporalEnvelope`, `BiTemporalRecord` |
| `spine.core.temporal` | `WeekEnding` for weekly workflows |
| `spine.core.watermarks` | "How far have I read?" cursor tracking |
| `spine.core.backfill` | Gap-fill planning when watermarks reveal holes |
| `spine.core.finance.corrections` | Why did a value change? |
| `spine.core.finance.adjustments` | Corporate-action math (splits, dividends) |
