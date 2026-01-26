# 📊 Market-Spine - Annotation Guide

**Project-Specific Guide for Annotating Market-Spine Classes**

*For use with Documentation Automation Package - February 2026*

---

## 📋 PROJECT CONTEXT

### What is Market-Spine?

**Market-Spine** is a market data and trading analytics package within the Spine ecosystem:

> *"I need market data (prices, quotes, trades), trading analytics, and portfolio management"*

### Status

⚠️ **Early Development** - Limited classes to annotate. Focus on establishing architecture patterns and core primitives.

**When classes are created, reference these patterns from sibling projects:**
- EntitySpine's `Result[T]` (Ok/Err) for error handling
- FeedSpine's storage protocols for backend abstraction
- Capture-Spine's `Container` pattern for dependency injection

### Core Philosophy

**Principle #1: Market Data as Data Archetype**

Market data has unique characteristics:
- **High frequency** - Tick data, quotes, trades (millisecond precision)
- **Time-series** - Temporal queries are primary use case
- **Immutable** - Historical data never changes
- **Volume** - Millions of records per day

Requires specialized storage (TimescaleDB, ClickHouse).

**Principle #2: Separation of Market Data vs Trading Logic**

- **Market Data**: Prices, quotes, trades, fundamentals (read-only)
- **Trading Logic**: Strategies, signals, orders, execution (write)

Different access patterns, different storage, different teams.

**Principle #3: Integration with EntitySpine**

Market data references entities:
- Ticker "AAPL" → Entity resolution → Security
- Security → Listings (NASDAQ, exchanges)
- Entity → Identifiers (ISIN, CUSIP, FIGI)

EntitySpine provides the master data layer.

### Key Concepts

1. **Market Data** - Prices, quotes, trades, fundamentals
2. **Time-Series** - Temporal data with millisecond precision
3. **Symbol Resolution** - Ticker → Entity → Security → Listings
4. **Trading Analytics** - Portfolio, P&L, risk metrics
5. **Real-Time Feed** - WebSocket, streaming data
6. **Historical Data** - Backtesting, research, analysis

---

## 🎯 CLASSES TO ANNOTATE

### **Tier 1 (MUST Annotate - When Classes Exist)**

#### Core Models (When Created)
1. **Market Data Models**: `Price`, `Quote`, `Trade`, `Bar` (OHLCV)
2. **Symbol Resolution**: `Ticker`, `SecurityIdentifier`, `Listing`
3. **Portfolio Models**: `Position`, `Transaction`, `PortfolioSnapshot`
4. **Analytics Models**: `Return`, `Volatility`, `Sharpe`, `PnL`

#### Services (When Created)
5. **Market Data Service**: Fetch, store, query market data
6. **Symbol Resolution Service**: Ticker → Entity → Security
7. **Portfolio Service**: Track positions, calculate P&L
8. **Analytics Service**: Compute metrics, risk measures

### **Recommended Pattern: Reuse from EntitySpine**

When creating Market-Spine classes, reuse these from EntitySpine:

```python
# Error handling - from EntitySpine's domain/workflow.py
from entityspine.domain.workflow import Ok, Err, Result, ExecutionContext

# Entity resolution
from entityspine.services import EntityResolver
from entityspine.domain import Entity, Security, Listing

# Usage in Market-Spine
class MarketDataService:
    """
    Fetches and stores market data with entity resolution.
    
    Manifesto:
        Market data is linked to entities via EntitySpine resolution.
        
        Ticker "AAPL" → EntityResolver → Entity → Security → Listings
        
        This ensures historical queries work correctly even when
        tickers change (FB → META) or companies reorganize.
        
        Uses Result[T] pattern from EntitySpine for error handling:
        - Ok(data) for successful operations
        - Err(message) for failures
        
        No exceptions for expected errors (network timeout, missing data).
    """
```

### **Annotation Priority**

Since Market-Spine is early-stage, prioritize:
1. **Core primitives** (Price, Quote, Trade models)
2. **Storage abstractions** (TimescaleDB integration)
3. **EntitySpine integration** (symbol resolution)
4. **Basic services** (fetch, store, query)

---

## 📝 PROJECT-SPECIFIC ANNOTATION GUIDELINES

### Manifesto Section

```python
Manifesto:
    Market data is a specialized data archetype requiring:
    - High-frequency ingestion (millions of ticks/day)
    - Time-series storage (TimescaleDB, ClickHouse)
    - Immutable history (never update historical data)
    - Entity resolution (tickers are ambiguous, use ISINs)
    
    Integration with EntitySpine ensures:
    - Ticker "AAPL" resolves to correct entity
    - Handle ticker changes (Alphabet: GOOGL → GOOG)
    - Support multiple listings (AAPL on NASDAQ, Frankfurt)
    - Link to corporate actions (splits, dividends)
```

### Architecture Section

```python
Architecture:
    ```
    Real-Time Feed (WebSocket)
          ↓
    Market Data Service
          ↓
    ┌─────────────────────────┐
    │  Symbol Resolution:     │
    │  Ticker → EntitySpine   │
    │  → Entity → Security    │
    │  → Listing              │
    └───────────┬─────────────┘
                ↓
    TimescaleDB (time-series storage)
          ↓
    ┌─────────────────────────┐
    │  Indexes:               │
    │  - (symbol, timestamp)  │
    │  - (entity_id, timestamp)│
    │  - Hypertable by time   │
    └─────────────────────────┘
    ```
    
    Storage: TimescaleDB (columnar, time-series optimized)
    Resolution: EntitySpine (ticker → entity mapping)
    Real-Time: WebSocket (Polygon, IEX, Alpaca)
    Historical: REST API, CSV/Parquet files
```

### Tags - Market-Spine Specific

- **Core**: `market_data`, `time_series`, `high_frequency`
- **Data Types**: `price`, `quote`, `trade`, `bar`, `ohlcv`
- **Resolution**: `symbol_resolution`, `ticker`, `entity_integration`
- **Storage**: `timescaledb`, `clickhouse`, `columnar`
- **Trading**: `portfolio`, `position`, `transaction`, `pnl`
- **Analytics**: `returns`, `volatility`, `sharpe`, `risk_metrics`

### Doc-Types

```python
Doc-Types:
    - MANIFESTO (section: "Market Data Archetype", priority: 9)
    - ARCHITECTURE (section: "Time-Series Storage", priority: 9)
    - UNIFIED_DATA_MODEL (section: "Market Data", priority: 10)
      # Link Price → Security → Entity → Identifiers
```

---

## 📚 REFERENCE DOCUMENTS

1. **Spine-Core README**: `spine-core/README.md`
   - Framework primitives, registry architecture

2. **EntitySpine Data Model**: `entityspine/docs/UNIFIED_DATA_MODEL.md`
   - Entity, Security, Listing models

3. **FeedSpine Data Archetypes**: `feedspine/docs/archive/design/DATA_ARCHETYPES_GUIDE.md`
   - Section: "Prices" archetype

---

## ✅ VALIDATION CHECKLIST

### Market-Specific
- [ ] Mentions time-series storage (TimescaleDB)
- [ ] Includes EntitySpine integration for symbol resolution
- [ ] Notes immutability of historical data
- [ ] Explains high-frequency data characteristics
- [ ] References Price/Quote/Trade/Bar models

### Quality
- [ ] At least 3 tags
- [ ] At least 2 doc-types
- [ ] Examples include entity resolution
- [ ] No TODO or placeholder text

---

## 🚀 QUICK START

1. **Read this guide** (5 minutes)
2. **Read EntitySpine data model** (10 minutes) - understand Entity/Security/Listing
3. **Read FeedSpine Price archetype** (10 minutes) - understand market data patterns
4. **Read EXTENDED_ANNOTATION_PROMPT.md** (15 minutes)
5. **Annotate core primitives** (Price, Quote, Trade models)
6. **Focus on EntitySpine integration** (symbol resolution)

---

**Note**: Since Market-Spine is early-stage, establish architecture patterns first before batch-annotating. Focus on:
1. Core data models
2. Storage strategy (TimescaleDB)
3. EntitySpine integration
4. Time-series query patterns
