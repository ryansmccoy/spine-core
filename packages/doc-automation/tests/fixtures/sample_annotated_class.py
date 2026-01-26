"""
Sample annotated class for testing documentation automation.

This file demonstrates the extended docstring format that the
doc-automation system parses.
"""


class EntityResolver:
    """Resolve any identifier (CIK, ticker, name) to a canonical entity.
    
    Manifesto:
        Entity ≠ Security ≠ Listing is fundamental to EntitySpine.
        A company (entity) can have multiple securities (stocks, bonds),
        and each security can be listed on multiple exchanges. Tickers
        change, companies reorganize, and securities get relisted.
        
        By treating these as separate concepts linked by relationships,
        we can track changes over time and avoid the common mistake of
        equating "AAPL" with "Apple Inc." permanently.
    
    Architecture:
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
    
    Features:
        - Multi-identifier support (CIK, ticker, CUSIP, ISIN, name)
        - Fuzzy name matching with confidence scores
        - Historical ticker resolution (what was AAPL on 2010-01-01?)
        - Batch resolution for efficiency
        - Entity metadata (industry, SIC code, filing status)
    
    Examples:
        >>> resolver = EntityResolver()
        >>> entity = resolver.resolve("AAPL")
        >>> entity.name
        'Apple Inc.'
        >>> entity.cik
        '0000320193'
    
    Performance:
        - Single lookup: <1ms (cached), <10ms (uncached)
        - Batch of 1000: <500ms
        - Storage: ~500MB for full SEC entity universe
    
    Guardrails:
        - Do NOT use ticker as primary key (tickers change!)
          ✅ Use CIK as primary, map tickers via claims
        - Do NOT assume 1:1 ticker-to-entity mapping
          ✅ Handle multiple entities sharing same ticker historically
        - Do NOT mix entity and security identifiers
          ✅ Use separate resolution paths
    
    Context:
        Problem: Most financial systems treat "ticker" as primary key,
        leading to data corruption when tickers change hands. Our
        approach uses SEC's CIK (Central Index Key) as the stable
        identifier and treats all other identifiers as "claims" that
        map to the canonical entity.
    
    ADR:
        - 003-identifier-claims.md: Why we model identifiers as claims
        - 008-resolution-pipeline.md: Resolution algorithm design
    
    Changelog:
        - v0.3.0: Added fuzzy name matching
        - v0.4.0: Added CUSIP/ISIN support
        - v0.5.0: Added historical ticker support
    
    Tags:
        - core_concept
        - entity_resolution
        - identifier_disambiguation
        - claims_based_identity
    
    Doc-Types:
        - MANIFESTO (section: "Core Principles", priority: 10)
        - FEATURES (section: "Entity Resolution", priority: 9)
        - ARCHITECTURE (section: "Data Model", priority: 8)
        - API_REFERENCE (section: "EntitySpine", priority: 7)
    """
    
    def __init__(self, cache_size: int = 10000):
        """Initialize the resolver.
        
        Args:
            cache_size: Maximum number of entities to cache
        """
        self.cache_size = cache_size
        self._cache = {}
    
    def resolve(self, identifier: str, as_of: str | None = None) -> dict | None:
        """Resolve an identifier to a canonical entity.
        
        Manifesto:
            Resolution is the core operation. Given any identifier,
            find the canonical entity it refers to. This must handle
            ambiguity (same ticker, different entities at different times)
            and missing data (identifier not in our system).
        
        Features:
            - Accepts any identifier type
            - Returns None if not found (explicit, not exception)
            - Supports point-in-time resolution
        
        Examples:
            >>> resolver = EntityResolver()
            >>> resolver.resolve("320193")  # CIK
            {'name': 'Apple Inc.', 'cik': '0000320193'}
            >>> resolver.resolve("AAPL", as_of="2010-01-01")
            {'name': 'Apple Inc.', 'cik': '0000320193'}
        
        Args:
            identifier: Any identifier (CIK, ticker, name, CUSIP, ISIN)
            as_of: Point-in-time date string (YYYY-MM-DD)
            
        Returns:
            Entity dict or None if not found
        
        Tags:
            - resolution
            - lookup
            - public_api
        
        Doc-Types:
            - API_REFERENCE (section: "EntityResolver Methods", priority: 10)
        """
        # Normalize identifier
        normalized = self._normalize(identifier)
        
        # Check cache
        cache_key = f"{normalized}:{as_of or 'current'}"
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        # Lookup (mock implementation)
        result = self._lookup(normalized, as_of)
        
        # Cache result
        if result and len(self._cache) < self.cache_size:
            self._cache[cache_key] = result
        
        return result
    
    def _normalize(self, identifier: str) -> str:
        """Normalize an identifier for lookup.
        
        Args:
            identifier: Raw identifier
            
        Returns:
            Normalized identifier
        """
        return identifier.strip().upper()
    
    def _lookup(self, identifier: str, as_of: str | None) -> dict | None:
        """Look up entity by normalized identifier.
        
        Args:
            identifier: Normalized identifier
            as_of: Point-in-time date
            
        Returns:
            Entity dict or None
        """
        # Mock implementation
        mock_data = {
            "AAPL": {"name": "Apple Inc.", "cik": "0000320193"},
            "320193": {"name": "Apple Inc.", "cik": "0000320193"},
            "0000320193": {"name": "Apple Inc.", "cik": "0000320193"},
            "MSFT": {"name": "Microsoft Corporation", "cik": "0000789019"},
            "GOOGL": {"name": "Alphabet Inc.", "cik": "0001652044"},
        }
        return mock_data.get(identifier)


class FeedAdapter:
    """Adapt external data feeds to EntitySpine format.
    
    Manifesto:
        Data comes from many sources in many formats. The FeedAdapter
        provides a consistent interface for ingesting data, normalizing
        it, and loading it into EntitySpine storage.
    
    Architecture:
        ```
        External Feed ──► FeedAdapter ──► Normalized Data ──► Storage
        (CSV, API,         (transform,     (standard         (DuckDB,
         JSON)              validate)       schema)           Parquet)
        ```
    
    Features:
        - Support multiple input formats (CSV, JSON, API)
        - Validate data against schema
        - Handle incremental updates
        - Track data lineage
    
    Examples:
        >>> adapter = FeedAdapter("sec_filings")
        >>> adapter.load_csv("filings.csv")
        >>> adapter.validate()
        True
    
    Guardrails:
        - Do NOT skip validation for "trusted" sources
          ✅ Always validate, trust but verify
        - Do NOT lose source metadata during transformation
          ✅ Preserve lineage in metadata columns
    
    Tags:
        - data_ingestion
        - feed_processing
        - etl
    
    Doc-Types:
        - FEATURES (section: "Data Feeds", priority: 7)
        - ARCHITECTURE (section: "Data Pipeline", priority: 6)
    """
    
    def __init__(self, feed_name: str):
        """Initialize the adapter.
        
        Args:
            feed_name: Name of the feed
        """
        self.feed_name = feed_name
        self.data = []
    
    def load_csv(self, path: str) -> int:
        """Load data from CSV file.
        
        Args:
            path: Path to CSV file
            
        Returns:
            Number of records loaded
        """
        # Mock implementation
        self.data = [{"id": 1}, {"id": 2}]
        return len(self.data)
    
    def validate(self) -> bool:
        """Validate loaded data.
        
        Returns:
            True if valid
        """
        return len(self.data) > 0
