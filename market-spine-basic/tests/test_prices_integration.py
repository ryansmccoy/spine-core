"""
Integration tests for Prices API.

Tests cover:
- Pagination (offset/limit/has_more)
- As-of queries (capture_id parameter)
- Latest price endpoint
- Metadata endpoint
- Error handling
"""

import json
import pytest
from datetime import datetime, UTC
from unittest.mock import Mock, patch

# Attempt FastAPI TestClient import
try:
    from fastapi.testclient import TestClient
    from market_spine.api.app import create_app
    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False
    TestClient = None


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def sample_price_data():
    """Sample price data for testing."""
    return [
        {
            "symbol": "AAPL",
            "date": "2024-01-15",
            "open": 150.0,
            "high": 152.5,
            "low": 149.25,
            "close": 151.75,
            "volume": 10000000,
            "change": 2.0,
            "change_percent": 0.0134,
            "source": "alpha_vantage",
            "capture_id": "market_data.prices.AAPL.20240115T120000Z.abc12345",
            "captured_at": "2024-01-15T12:00:00Z",
        },
        {
            "symbol": "AAPL",
            "date": "2024-01-14",
            "open": 148.0,
            "high": 150.5,
            "low": 147.25,
            "close": 149.75,
            "volume": 9500000,
            "change": 1.5,
            "change_percent": 0.0101,
            "source": "alpha_vantage",
            "capture_id": "market_data.prices.AAPL.20240115T120000Z.abc12345",
            "captured_at": "2024-01-15T12:00:00Z",
        },
    ]


@pytest.fixture
def mock_db(sample_price_data):
    """Mock database with sample data."""
    data = sample_price_data.copy()
    
    class MockCursor:
        def __init__(self):
            self.results = []
        
        def execute(self, query, params=None):
            # Parse query to determine what to return
            if "COUNT(*)" in query:
                self.results = [(len(data),)]
            elif "DISTINCT capture_id" in query:
                self.results = [(d["capture_id"],) for d in data[:1]]
            elif "symbol" in query.lower() and "date" in query.lower():
                symbol = params[0] if params else "AAPL"
                filtered = [d for d in data if d["symbol"] == symbol]
                self.results = [
                    (d["symbol"], d["date"], d["open"], d["high"], d["low"], 
                     d["close"], d["volume"], d["change"], d["change_percent"],
                     d["source"], d["capture_id"], d["captured_at"])
                    for d in filtered
                ]
        
        def fetchall(self):
            return self.results
        
        def fetchone(self):
            return self.results[0] if self.results else None
    
    class MockConnection:
        def cursor(self):
            return MockCursor()
    
    return MockConnection()


@pytest.fixture
def client(mock_db):
    """FastAPI test client with mocked database."""
    if not HAS_FASTAPI:
        pytest.skip("FastAPI not installed")
    
    with patch("market_spine.app.commands.prices.get_connection", return_value=mock_db):
        app = create_app()
        yield TestClient(app)


# =============================================================================
# Pagination Tests
# =============================================================================

@pytest.mark.skipif(not HAS_FASTAPI, reason="FastAPI not installed")
class TestPagination:
    """Tests for pagination behavior."""
    
    def test_default_pagination(self, client):
        """Default pagination returns first page."""
        response = client.get("/v1/data/prices/AAPL")
        
        assert response.status_code == 200
        data = response.json()
        
        assert "data" in data
        assert "pagination" in data
        assert data["pagination"]["offset"] == 0
    
    def test_explicit_pagination(self, client):
        """Explicit offset/limit are respected."""
        response = client.get("/v1/data/prices/AAPL?offset=10&limit=5")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["pagination"]["offset"] == 10
        assert data["pagination"]["limit"] == 5
    
    def test_max_limit_enforcement(self, client):
        """Limit is capped at MAX_LIMIT."""
        response = client.get("/v1/data/prices/AAPL?limit=5000")
        
        assert response.status_code == 200
        data = response.json()
        
        # Should be capped at MAX_LIMIT (1000)
        assert data["pagination"]["limit"] <= 1000
    
    def test_has_more_flag(self, client, sample_price_data):
        """has_more flag indicates more data available."""
        response = client.get("/v1/data/prices/AAPL?limit=1")
        
        assert response.status_code == 200
        data = response.json()
        
        # With sample data of 2 rows and limit of 1
        if data["pagination"]["total"] > 1:
            assert data["pagination"]["has_more"] is True


# =============================================================================
# As-Of Query Tests
# =============================================================================

@pytest.mark.skipif(not HAS_FASTAPI, reason="FastAPI not installed")
class TestAsOfQueries:
    """Tests for as-of (point-in-time) queries."""
    
    def test_as_of_with_capture_id(self, client, sample_price_data):
        """Filtering by capture_id returns only that capture's data."""
        capture_id = sample_price_data[0]["capture_id"]
        response = client.get(f"/v1/data/prices/AAPL?capture_id={capture_id}")
        
        assert response.status_code == 200
        data = response.json()
        
        assert "capture" in data
        assert data["capture"]["capture_id"] == capture_id
    
    def test_invalid_capture_id(self, client):
        """Invalid capture_id returns 404 or empty data."""
        response = client.get("/v1/data/prices/AAPL?capture_id=nonexistent.capture.id")
        
        # Should either return 404 or empty data
        assert response.status_code in [200, 404]


# =============================================================================
# Latest Price Tests
# =============================================================================

@pytest.mark.skipif(not HAS_FASTAPI, reason="FastAPI not installed")
class TestLatestPrice:
    """Tests for latest price endpoint."""
    
    def test_latest_price_endpoint(self, client):
        """GET /v1/data/prices/{symbol}/latest returns most recent price."""
        response = client.get("/v1/data/prices/AAPL/latest")
        
        assert response.status_code == 200
        data = response.json()
        
        assert "symbol" in data
        assert data["symbol"] == "AAPL"
        assert "date" in data
        assert "close" in data
    
    def test_latest_price_unknown_symbol(self, client):
        """Unknown symbol returns 404."""
        with patch("market_spine.app.commands.prices.get_connection") as mock:
            cursor = Mock()
            cursor.fetchone.return_value = None
            mock.return_value.cursor.return_value = cursor
            
            response = client.get("/v1/data/prices/UNKNOWN/latest")
        
        assert response.status_code == 404


# =============================================================================
# Metadata Tests
# =============================================================================

@pytest.mark.skipif(not HAS_FASTAPI, reason="FastAPI not installed")
class TestMetadata:
    """Tests for metadata endpoint."""
    
    def test_metadata_endpoint(self, client):
        """GET /v1/data/prices/metadata returns available captures."""
        response = client.get("/v1/data/prices/metadata")
        
        assert response.status_code == 200
        data = response.json()
        
        assert "captures" in data
        assert isinstance(data["captures"], list)
    
    def test_metadata_with_symbol_filter(self, client):
        """Metadata can be filtered by symbol."""
        response = client.get("/v1/data/prices/metadata?symbol=AAPL")
        
        assert response.status_code == 200
        data = response.json()
        
        assert "captures" in data


# =============================================================================
# Error Handling Tests
# =============================================================================

@pytest.mark.skipif(not HAS_FASTAPI, reason="FastAPI not installed")
class TestErrorHandling:
    """Tests for error handling."""
    
    def test_invalid_date_range(self, client):
        """Invalid date range returns 400."""
        response = client.get("/v1/data/prices/AAPL?start_date=invalid")
        
        assert response.status_code in [400, 422]
    
    def test_negative_offset(self, client):
        """Negative offset returns 422."""
        response = client.get("/v1/data/prices/AAPL?offset=-1")
        
        assert response.status_code == 422
    
    def test_negative_limit(self, client):
        """Negative limit returns 422."""
        response = client.get("/v1/data/prices/AAPL?limit=-1")
        
        assert response.status_code == 422


# =============================================================================
# Response Format Tests
# =============================================================================

@pytest.mark.skipif(not HAS_FASTAPI, reason="FastAPI not installed")
class TestResponseFormat:
    """Tests for response format consistency."""
    
    def test_response_structure(self, client):
        """Response has consistent structure."""
        response = client.get("/v1/data/prices/AAPL")
        
        assert response.status_code == 200
        data = response.json()
        
        # Required top-level keys
        assert "data" in data
        assert "pagination" in data
        
        # Pagination structure
        pagination = data["pagination"]
        assert "offset" in pagination
        assert "limit" in pagination
        assert "total" in pagination
        assert "has_more" in pagination
    
    def test_price_data_structure(self, client):
        """Price data has required fields."""
        response = client.get("/v1/data/prices/AAPL")
        
        assert response.status_code == 200
        data = response.json()
        
        if data["data"]:
            price = data["data"][0]
            required_fields = ["symbol", "date", "open", "high", "low", "close", "volume"]
            for field in required_fields:
                assert field in price, f"Missing field: {field}"
