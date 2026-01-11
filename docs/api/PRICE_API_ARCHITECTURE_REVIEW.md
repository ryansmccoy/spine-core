# Price API Architecture Review

> Created: 2026-01-04  
> Status: **NEEDS DECISION**  
> Context: Phase 2 implementation added `/v1/data/prices/` endpoints

---

## 1. Summary

During Phase 2 (Alpha Vantage integration), we created price endpoints that may not align with the documented API architecture. This document outlines the gap and options for resolution.

---

## 2. Current API Patterns in Documentation

### Pattern A: Domain-Scoped Routes (OTC Design)

**Source:** `docs/otc/06-api.md`

```
/api/v1/otc/weekly/symbols
/api/v1/otc/weekly/symbols/{symbol}
/api/v1/otc/weekly/symbols/{symbol}/venues
/api/v1/otc/weekly/venues/{mpid}
```

**Characteristics:**
- Domain prefix in URL (`/otc/`)
- Resource-oriented (symbols, venues)
- Temporal qualifier in path (`/weekly/`)
- Domain-specific query params (tier, week_ending)

### Pattern B: Generic Data Plane (Basic API Design)

**Source:** `docs/api/02-basic-api-surface.md`

```
/v1/data/domains           # List domains
/v1/data/calcs             # List calculations  
/v1/data/calcs/{calc_name} # Query a specific calc
/v1/data/weeks             # Available weeks (current)
/v1/data/symbols           # Top symbols (current)
```

**Characteristics:**
- Generic `/v1/data/` prefix
- Calc-centric (calcs are versioned, documented entities)
- Domain passed as query parameter
- Supports `capture_id` for point-in-time queries

---

## 3. What We Implemented for Prices

**Location:** `market-spine-basic/src/market_spine/api/routes/v1/prices.py`

```
GET /v1/data/prices/{symbol}         # Price history (OHLCV)
GET /v1/data/prices/{symbol}/latest  # Latest price
```

**Characteristics:**
- Under generic `/v1/data/` prefix ✓
- Resource-oriented (like OTC pattern)
- Symbol in path (like OTC pattern)
- No calc versioning (unlike Basic API design)
- Has `capture_id` in response ✓

---

## 4. The Architectural Gap

| Aspect | Basic API Design | OTC Design | Our Prices |
|--------|------------------|------------|------------|
| Path prefix | `/v1/data/` | `/api/v1/otc/` | `/v1/data/` |
| Resource style | Calc-centric | Resource-centric | Resource-centric |
| Versioning | In calc name (`_v1`) | N/A | None |
| Domain in URL | No (query param) | Yes (`/otc/`) | Implied (`/prices/`) |

**Key Question:** Our prices endpoint uses the `/v1/data/` prefix but follows OTC's resource-oriented pattern rather than the calc-centric pattern documented for `/v1/data/`.

---

## 5. Options

### Option A: Keep As-Is, Document as Pattern for External Data

**Rationale:**
- External market data (Alpha Vantage, Polygon) is fundamentally different from ingested FINRA data
- No tier/week partitioning complexity
- Simple symbol + date access pattern
- `/v1/data/prices/` is intuitive for API consumers

**Changes Required:**
- Update `docs/api/02-basic-api-surface.md` to document prices endpoints
- Add section explaining when resource-style endpoints are appropriate
- Update LLM prompts to reflect this pattern

**Pros:**
- Already implemented and working
- Simple, intuitive API
- Follows REST best practices for resource access

**Cons:**
- Two patterns under `/v1/data/` (calcs vs resources)
- May cause confusion about when to use which

---

### Option B: Move to Domain Prefix (Match OTC Pattern)

**New Endpoints:**
```
GET /v1/market_data/prices/{symbol}
GET /v1/market_data/prices/{symbol}/latest
```

**Changes Required:**
- Move routes from `/v1/data/prices/` to `/v1/market_data/`
- Update frontend client
- Update tests
- Document pattern

**Pros:**
- Consistent with OTC domain-scoped pattern
- Clear separation: `/v1/data/` for calcs, `/v1/{domain}/` for resources

**Cons:**
- Breaking change (routes move)
- OTC pattern uses `/api/v1/` not `/v1/` (another inconsistency)
- More work

---

### Option C: Convert to Calc Pattern

**New Endpoints:**
```
GET /v1/data/calcs/daily_ohlcv_v1?symbol=AAPL&days=30
GET /v1/data/calcs/latest_price_v1?symbol=AAPL
```

**Changes Required:**
- Register prices as "calcs" in calc registry
- Refactor endpoint to match calc response envelope
- Update frontend to use calc pattern

**Pros:**
- Matches documented Basic API design exactly
- Consistent with other `/v1/data/` endpoints
- Gets versioning for free

**Cons:**
- Awkward for simple lookups (`calcs/daily_ohlcv_v1?symbol=X` vs `prices/X`)
- Prices aren't really "calculations" - they're raw data
- More complex implementation

---

## 6. Questions for Decision

### Q1: Is `/v1/data/prices/` acceptable as a hybrid pattern?

External market data (prices, quotes) doesn't fit neatly into either:
- **Calcs** (derived, versioned computations) 
- **Domain resources** (like OTC symbols/venues)

Should we define a third category: **External Data Resources** under `/v1/data/`?

### Q2: Should OTC also move to `/v1/data/` or stay at `/api/v1/otc/`?

The OTC API design doc uses `/api/v1/otc/` but it was never implemented. Basic currently has `/v1/data/weeks` and `/v1/data/symbols` for OTC data. Should we:
- Implement OTC at `/api/v1/otc/` as designed?
- Keep everything under `/v1/data/` for simplicity?

### Q3: What about future external data sources?

If we add:
- Polygon.io (real-time quotes)
- Yahoo Finance (fundamentals)
- IEX Cloud (institutional data)

Should each get its own path?
```
/v1/data/prices/{symbol}      # Any price source
/v1/data/quotes/{symbol}      # Real-time quotes
/v1/data/fundamentals/{symbol} # Company data
```

Or be source-specific?
```
/v1/polygon/quotes/{symbol}
/v1/iex/fundamentals/{symbol}
```

### Q4: Is the capture_id pattern appropriate for external data?

Our prices table has `capture_id` for lineage, but external API data is:
- Fetched on-demand or cached
- Not batch-ingested like FINRA
- Has different freshness semantics

Should external data use the same capture semantics?

---

## 7. Recommendation

**I lean toward Option A (keep as-is, document as pattern)** because:

1. **Pragmatic**: Already working, tests pass, frontend integrated
2. **Intuitive**: `/v1/data/prices/AAPL` is clear and RESTful
3. **Appropriate**: External data resources differ from calc-based analytics
4. **Extensible**: Pattern works for quotes, fundamentals, etc.

**Suggested Documentation Update:**

Add to `02-basic-api-surface.md`:

```markdown
### External Data Resources

For external market data that doesn't go through the full 
ingest→normalize→calculate pipeline, we use resource-style 
endpoints under `/v1/data/`:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/data/prices/{symbol}` | GET | Daily OHLCV history |
| `/v1/data/prices/{symbol}/latest` | GET | Latest price |

These differ from calcs in that:
- No calc versioning (data is what the source provides)
- Symbol in path (resource-oriented, not query param)
- May have different freshness/caching semantics
```

---

## 8. Next Steps

Please review and decide:

- [ ] **Accept Option A** — Document current pattern, update API docs
- [ ] **Choose Option B** — Refactor to domain-scoped routes
- [ ] **Choose Option C** — Refactor to calc pattern
- [ ] **Other** — Different approach

Once decided, I'll update the relevant documentation and code.
