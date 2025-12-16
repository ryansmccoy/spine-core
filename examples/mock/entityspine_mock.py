"""Mock EntitySpine API for spine-core examples.

Provides realistic EntitySpine behavior without requiring
the entityspine package or database connections.
"""
from __future__ import annotations

from .base import MockAPIBase, MockResponse
from .fixtures import MOCK_COMPANIES, MOCK_FILINGS, MOCK_IDENTIFIER_CLAIMS


class MockEntitySpine(MockAPIBase):
    """Mock EntitySpine that mimics real resolution behavior.
    
    Use this in spine-core examples to demonstrate integration
    with EntitySpine without requiring the actual package.
    
    Example:
        >>> api = MockEntitySpine()
        >>> result = await api.resolve_by_cik("0000320193")
        >>> result.data["name"]
        'Apple Inc.'
    """
    
    async def resolve_by_cik(self, cik: str) -> MockResponse:
        """Resolve company by SEC CIK number.
        
        Args:
            cik: 10-digit SEC Central Index Key
            
        Returns:
            MockResponse with company data or error
        """
        await self._simulate_latency()
        
        if self._should_fail():
            return MockResponse(data=None, success=False, error="Service unavailable")
        
        company = MOCK_COMPANIES.get(cik)
        if company:
            return MockResponse(data=company, success=True)
        return MockResponse(data=None, success=False, error=f"CIK not found: {cik}")
    
    async def resolve_by_ticker(self, ticker: str) -> MockResponse:
        """Resolve company by stock ticker symbol.
        
        Args:
            ticker: Stock ticker (e.g., "AAPL")
            
        Returns:
            MockResponse with company data or error
        """
        await self._simulate_latency()
        
        if self._should_fail():
            return MockResponse(data=None, success=False, error="Service unavailable")
        
        ticker_upper = ticker.upper()
        for cik, company in MOCK_COMPANIES.items():
            if company.get("ticker") == ticker_upper:
                return MockResponse(data=company, success=True)
        
        return MockResponse(data=None, success=False, error=f"Ticker not found: {ticker}")
    
    async def resolve_by_name(self, name: str) -> MockResponse:
        """Resolve company by name (fuzzy match).
        
        Args:
            name: Company name or partial name
            
        Returns:
            MockResponse with list of matching companies
        """
        await self._simulate_latency()
        
        if self._should_fail():
            return MockResponse(data=None, success=False, error="Service unavailable")
        
        name_lower = name.lower()
        matches = [
            company for company in MOCK_COMPANIES.values()
            if name_lower in company["name"].lower()
        ]
        
        return MockResponse(data=matches, success=True)
    
    async def get_filings(
        self, 
        cik: str, 
        form_type: str | None = None,
        limit: int = 10,
    ) -> MockResponse:
        """Get SEC filings for a company.
        
        Args:
            cik: SEC CIK number
            form_type: Filter by form type (e.g., "10-K")
            limit: Maximum number of filings to return
            
        Returns:
            MockResponse with list of filings
        """
        await self._simulate_latency()
        
        if self._should_fail():
            return MockResponse(data=None, success=False, error="Service unavailable")
        
        filings = MOCK_FILINGS.get(cik, [])
        
        if form_type:
            filings = [f for f in filings if f.get("form") == form_type]
        
        return MockResponse(data=filings[:limit], success=True)
    
    async def get_identifiers(self, cik: str) -> MockResponse:
        """Get all identifiers for a company.
        
        Args:
            cik: SEC CIK number
            
        Returns:
            MockResponse with identifier claims
        """
        await self._simulate_latency()
        
        identifiers = MOCK_IDENTIFIER_CLAIMS.get(cik, {})
        return MockResponse(data=identifiers, success=True)
    
    async def search(self, query: str, limit: int = 5) -> MockResponse:
        """Search for entities by any identifier or name.
        
        Args:
            query: Search query (CIK, ticker, or name)
            limit: Maximum results
            
        Returns:
            MockResponse with matching companies
        """
        await self._simulate_latency()
        
        if self._should_fail():
            return MockResponse(data=None, success=False, error="Service unavailable")
        
        results = []
        query_upper = query.upper()
        query_lower = query.lower()
        
        for cik, company in MOCK_COMPANIES.items():
            # Match by CIK
            if query == cik:
                results.append({"match_type": "cik", "score": 1.0, **company})
                continue
            
            # Match by ticker
            if company.get("ticker") == query_upper:
                results.append({"match_type": "ticker", "score": 1.0, **company})
                continue
            
            # Match by name (partial)
            if query_lower in company["name"].lower():
                score = len(query) / len(company["name"])
                results.append({"match_type": "name", "score": score, **company})
        
        # Sort by score descending
        results.sort(key=lambda x: x["score"], reverse=True)
        
        return MockResponse(data=results[:limit], success=True)
