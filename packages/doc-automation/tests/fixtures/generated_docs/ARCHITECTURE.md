# ARCHITECTURE

**System Design and Structure**

*Auto-generated from code annotations on 2026-02-01*

---

## System Overview

### FeedAdapter

```
```
    External Feed ──► FeedAdapter ──► Normalized Data ──► Storage
    (CSV, API,         (transform,     (standard         (DuckDB,
     JSON)              validate)       schema)           Parquet)
    ```
```

*From [`FeedAdapter`](b:\github\py-sec-edgar\spine-core\packages\doc-automation\tests\fixtures\sample_annotated_class.py#L187)*

### EntityResolver

```
```
    ┌─────────────────────────────────────────────────────────┐
    │                  EntityResolver                         │
    │                                                         │
    │  Input Identifier ──► Normalize ──► Lookup ──► Entity   │
    │  (CIK, ticker,        (clean,       (local    (canonical│
    │   name, CUSIP)         format)       cache)    entity)  │
    │                                        │                │
    │                                        ▼                │
    │                              Fallback: SEC EDGAR API    │
    └─────────────────────────────────────────────────────────┘
    ```
```

*From [`EntityResolver`](b:\github\py-sec-edgar\spine-core\packages\doc-automation\tests\fixtures\sample_annotated_class.py#L9)*


## Data Model

Entity ≠ Security ≠ Listing is fundamental to EntitySpine.
    A company (entity) can have multiple securities (stocks, bonds),
    and each security can be listed on multiple exchanges. Tickers
    change, companies reorganize, and securities get relisted.
    
    By treating these as separate concepts linked by relationships,
    we can track changes over time and avoid the common mistake of
    equating "AAPL" with "Apple Inc." permanently.

*From [`EntityResolver`](b:\github\py-sec-edgar\spine-core\packages\doc-automation\tests\fixtures\sample_annotated_class.py#L9)*

- Multi-identifier support (CIK, ticker, CUSIP, ISIN, name)
    - Fuzzy name matching with confidence scores
    - Historical ticker resolution (what was AAPL on 2010-01-01?)
    - Batch resolution for efficiency
    - Entity metadata (industry, SIC code, filing status)

*From [`EntityResolver`](b:\github\py-sec-edgar\spine-core\packages\doc-automation\tests\fixtures\sample_annotated_class.py#L9)*

- Do NOT use ticker as primary key (tickers change!)
      ✅ Use CIK as primary, map tickers via claims
    - Do NOT assume 1:1 ticker-to-entity mapping
      ✅ Handle multiple entities sharing same ticker historically
    - Do NOT mix entity and security identifiers
      ✅ Use separate resolution paths

*From [`EntityResolver`](b:\github\py-sec-edgar\spine-core\packages\doc-automation\tests\fixtures\sample_annotated_class.py#L9)*

>>> resolver = EntityResolver()
    >>> entity = resolver.resolve("AAPL")
    >>> entity.name
    'Apple Inc.'
    >>> entity.cik
    '0000320193'

*From [`EntityResolver`](b:\github\py-sec-edgar\spine-core\packages\doc-automation\tests\fixtures\sample_annotated_class.py#L9)*

- Single lookup: <1ms (cached), <10ms (uncached)
    - Batch of 1000: <500ms
    - Storage: ~500MB for full SEC entity universe

*From [`EntityResolver`](b:\github\py-sec-edgar\spine-core\packages\doc-automation\tests\fixtures\sample_annotated_class.py#L9)*

Problem: Most financial systems treat "ticker" as primary key,
    leading to data corruption when tickers change hands. Our
    approach uses SEC's CIK (Central Index Key) as the stable
    identifier and treats all other identifiers as "claims" that
    map to the canonical entity.

*From [`EntityResolver`](b:\github\py-sec-edgar\spine-core\packages\doc-automation\tests\fixtures\sample_annotated_class.py#L9)*

- 003-identifier-claims.md: Why we model identifiers as claims
    - 008-resolution-pipeline.md: Resolution algorithm design

*From [`EntityResolver`](b:\github\py-sec-edgar\spine-core\packages\doc-automation\tests\fixtures\sample_annotated_class.py#L9)*

- v0.3.0: Added fuzzy name matching
    - v0.4.0: Added CUSIP/ISIN support
    - v0.5.0: Added historical ticker support

*From [`EntityResolver`](b:\github\py-sec-edgar\spine-core\packages\doc-automation\tests\fixtures\sample_annotated_class.py#L9)*

Resolve any identifier (CIK, ticker, name) to a canonical entity.

*From [`EntityResolver`](b:\github\py-sec-edgar\spine-core\packages\doc-automation\tests\fixtures\sample_annotated_class.py#L9)*

## Data Pipeline

Data comes from many sources in many formats. The FeedAdapter
    provides a consistent interface for ingesting data, normalizing
    it, and loading it into EntitySpine storage.

*From [`FeedAdapter`](b:\github\py-sec-edgar\spine-core\packages\doc-automation\tests\fixtures\sample_annotated_class.py#L187)*

- Support multiple input formats (CSV, JSON, API)
    - Validate data against schema
    - Handle incremental updates
    - Track data lineage

*From [`FeedAdapter`](b:\github\py-sec-edgar\spine-core\packages\doc-automation\tests\fixtures\sample_annotated_class.py#L187)*

- Do NOT skip validation for "trusted" sources
      ✅ Always validate, trust but verify
    - Do NOT lose source metadata during transformation
      ✅ Preserve lineage in metadata columns

*From [`FeedAdapter`](b:\github\py-sec-edgar\spine-core\packages\doc-automation\tests\fixtures\sample_annotated_class.py#L187)*

>>> adapter = FeedAdapter("sec_filings")
    >>> adapter.load_csv("filings.csv")
    >>> adapter.validate()
    True

*From [`FeedAdapter`](b:\github\py-sec-edgar\spine-core\packages\doc-automation\tests\fixtures\sample_annotated_class.py#L187)*

Adapt external data feeds to EntitySpine format.

*From [`FeedAdapter`](b:\github\py-sec-edgar\spine-core\packages\doc-automation\tests\fixtures\sample_annotated_class.py#L187)*


---

*2 diagrams, 2 component sections*

*Generated by [doc-automation](https://github.com/your-org/py-sec-edgar/tree/main/spine-core/packages/doc-automation)*