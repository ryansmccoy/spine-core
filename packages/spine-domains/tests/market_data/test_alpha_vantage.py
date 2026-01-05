"""
Unit tests for Alpha Vantage source.

Tests cover:
- FetchResult and SourceMetadata dataclass structure
- Content hash determinism
- Retry logic with exponential backoff
- Error handling and anomaly recording
"""

import json
import hashlib
from datetime import datetime, UTC
from typing import Any
from unittest.mock import Mock, patch
import pytest

from spine.domains.market_data.sources.alpha_vantage import (
    AlphaVantageSource,
    FetchResult,
    SourceMetadata,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_api_response() -> dict[str, Any]:
    """Standard Alpha Vantage API response."""
    return {
        "Meta Data": {
            "1. Information": "Daily Prices",
            "2. Symbol": "AAPL",
            "3. Last Refreshed": "2024-01-15",
        },
        "Time Series (Daily)": {
            "2024-01-15": {
                "1. open": "150.00",
                "2. high": "152.50",
                "3. low": "149.25",
                "4. close": "151.75",
                "5. volume": "10000000",
            },
            "2024-01-14": {
                "1. open": "148.00",
                "2. high": "150.50",
                "3. low": "147.25",
                "4. close": "149.75",
                "5. volume": "9500000",
            },
        },
    }


@pytest.fixture
def mock_http_client(mock_api_response):
    """Mock HTTP client that returns standard response."""
    client = Mock()
    response = Mock()
    response.status_code = 200
    response.text = json.dumps(mock_api_response)
    response.json.return_value = mock_api_response
    client.get.return_value = response
    return client


@pytest.fixture
def source_with_mock_client(mock_http_client):
    """AlphaVantageSource with injected mock client."""
    return AlphaVantageSource(api_key="test_key", http_client=mock_http_client)


# =============================================================================
# FetchResult and SourceMetadata Tests
# =============================================================================

class TestFetchResult:
    """Tests for FetchResult dataclass."""
    
    def test_fetch_result_structure(self):
        """FetchResult has expected fields."""
        result = FetchResult(
            data=[{"date": "2024-01-15", "close": 151.75}],
            anomalies=[],
            metadata=None,
            success=True,
        )
        
        assert result.data == [{"date": "2024-01-15", "close": 151.75}]
        assert result.anomalies == []
        assert result.metadata is None
        assert result.success is True
    
    def test_fetch_result_with_anomalies(self):
        """FetchResult captures anomalies."""
        result = FetchResult(
            data=[],
            anomalies=[{"category": "api_error", "message": "Rate limit exceeded"}],
            metadata=None,
            success=False,
        )
        
        assert len(result.anomalies) == 1
        assert result.anomalies[0]["category"] == "api_error"
        assert result.success is False


class TestSourceMetadata:
    """Tests for SourceMetadata dataclass."""
    
    def test_source_metadata_structure(self):
        """SourceMetadata has expected fields."""
        now = datetime.now(UTC)
        meta = SourceMetadata(
            source_type="alpha_vantage",
            source_uri="https://www.alphavantage.co/query",
            fetched_at=now,
            content_hash="abc123",
            etag=None,
            last_modified=None,
            response_size_bytes=1024,
            request_params_hash="params123",
        )
        
        assert meta.source_type == "alpha_vantage"
        assert meta.content_hash == "abc123"
        assert meta.response_size_bytes == 1024


# =============================================================================
# Content Hash Tests
# =============================================================================

class TestContentHash:
    """Tests for content hash computation."""
    
    def test_content_hash_determinism(self, source_with_mock_client):
        """Same response produces same content hash."""
        result1 = source_with_mock_client.fetch({"symbol": "AAPL"})
        result2 = source_with_mock_client.fetch({"symbol": "AAPL"})
        
        assert result1.metadata.content_hash == result2.metadata.content_hash
    
    def test_content_hash_is_sha256(self, source_with_mock_client):
        """Content hash is valid SHA-256."""
        result = source_with_mock_client.fetch({"symbol": "AAPL"})
        
        # SHA-256 produces 64 hex characters
        assert len(result.metadata.content_hash) == 64
        assert all(c in "0123456789abcdef" for c in result.metadata.content_hash)
    
    def test_content_hash_changes_with_data(self, mock_http_client):
        """Different data produces different content hash."""
        source = AlphaVantageSource(api_key="test_key", http_client=mock_http_client)
        result1 = source.fetch({"symbol": "AAPL"})
        
        # Modify response
        different_response = {
            "Time Series (Daily)": {
                "2024-01-15": {
                    "1. open": "999.00",  # Different value
                    "2. high": "999.00",
                    "3. low": "999.00",
                    "4. close": "999.00",
                    "5. volume": "1",
                },
            },
        }
        mock_http_client.get.return_value.json.return_value = different_response
        mock_http_client.get.return_value.text = json.dumps(different_response)
        
        result2 = source.fetch({"symbol": "AAPL"})
        
        assert result1.metadata.content_hash != result2.metadata.content_hash


# =============================================================================
# Retry Logic Tests
# =============================================================================

class TestRetryLogic:
    """Tests for retry with exponential backoff."""
    
    def test_retry_on_rate_limit(self):
        """Retries on 429 rate limit response."""
        client = Mock()
        
        # First two calls return 429, third succeeds
        rate_limit_response = Mock(status_code=429, text="Rate limit")
        success_response = Mock(
            status_code=200,
            text='{"Time Series (Daily)": {}}',
        )
        success_response.json.return_value = {"Time Series (Daily)": {}}
        
        client.get.side_effect = [rate_limit_response, rate_limit_response, success_response]
        
        source = AlphaVantageSource(api_key="test_key", http_client=client)
        
        with patch("time.sleep"):  # Skip actual delays
            result = source.fetch({"symbol": "AAPL"})
        
        assert result.success is True
        assert client.get.call_count == 3
    
    def test_retry_exhaustion(self):
        """Returns failure after max retries."""
        client = Mock()
        rate_limit_response = Mock(status_code=429, text="Rate limit")
        client.get.return_value = rate_limit_response
        
        source = AlphaVantageSource(api_key="test_key", http_client=client)
        
        with patch("time.sleep"):  # Skip actual delays
            result = source.fetch({"symbol": "AAPL"})
        
        assert result.success is False
        assert len(result.anomalies) > 0
        assert "rate_limit" in result.anomalies[0]["category"]
    
    def test_no_retry_on_client_error(self):
        """No retry on 4xx client errors (except 429)."""
        client = Mock()
        bad_request_response = Mock(status_code=400, text="Bad request")
        client.get.return_value = bad_request_response
        
        source = AlphaVantageSource(api_key="test_key", http_client=client)
        result = source.fetch({"symbol": ""})  # Invalid symbol
        
        assert result.success is False
        assert client.get.call_count == 1  # No retries


# =============================================================================
# Error Handling Tests
# =============================================================================

class TestErrorHandling:
    """Tests for error handling and anomaly recording."""
    
    def test_api_error_response(self):
        """Handles Alpha Vantage API error message."""
        client = Mock()
        error_response = Mock(status_code=200)
        error_response.text = json.dumps({
            "Error Message": "Invalid API call. Please retry or visit the documentation."
        })
        error_response.json.return_value = {"Error Message": "Invalid API call"}
        client.get.return_value = error_response
        
        source = AlphaVantageSource(api_key="test_key", http_client=client)
        result = source.fetch({"symbol": "INVALID"})
        
        assert result.success is False
        assert len(result.anomalies) == 1
        assert result.anomalies[0]["category"] == "api_error"
    
    def test_network_error(self):
        """Handles network errors gracefully."""
        client = Mock()
        client.get.side_effect = ConnectionError("Network unreachable")
        
        source = AlphaVantageSource(api_key="test_key", http_client=client)
        result = source.fetch({"symbol": "AAPL"})
        
        assert result.success is False
        assert len(result.anomalies) == 1
        assert "network" in result.anomalies[0]["category"].lower() or "error" in result.anomalies[0]["message"].lower()
    
    def test_empty_data_handling(self):
        """Handles empty time series gracefully."""
        client = Mock()
        empty_response = Mock(status_code=200)
        empty_response.text = json.dumps({"Time Series (Daily)": {}})
        empty_response.json.return_value = {"Time Series (Daily)": {}}
        client.get.return_value = empty_response
        
        source = AlphaVantageSource(api_key="test_key", http_client=client)
        result = source.fetch({"symbol": "AAPL"})
        
        # Empty data should succeed but with empty list
        assert result.success is True
        assert result.data == []


# =============================================================================
# Parameter Handling Tests
# =============================================================================

class TestParameterHandling:
    """Tests for request parameter handling."""
    
    def test_default_parameters(self, mock_http_client):
        """Default parameters are applied correctly."""
        source = AlphaVantageSource(api_key="test_key", http_client=mock_http_client)
        source.fetch({"symbol": "AAPL"})
        
        # Verify the call was made with expected params
        mock_http_client.get.assert_called_once()
        call_args = mock_http_client.get.call_args
        params = call_args.kwargs.get("params", call_args.args[1] if len(call_args.args) > 1 else {})
        
        assert params.get("symbol") == "AAPL"
        assert params.get("apikey") == "test_key"
    
    def test_outputsize_parameter(self, mock_http_client):
        """Outputsize parameter is passed correctly."""
        source = AlphaVantageSource(api_key="test_key", http_client=mock_http_client)
        source.fetch({"symbol": "AAPL", "outputsize": "full"})
        
        call_args = mock_http_client.get.call_args
        params = call_args.kwargs.get("params", call_args.args[1] if len(call_args.args) > 1 else {})
        
        assert params.get("outputsize") == "full"


# =============================================================================
# Integration Test (requires API key)
# =============================================================================

@pytest.mark.skip(reason="Requires ALPHA_VANTAGE_API_KEY environment variable")
class TestAlphaVantageIntegration:
    """Integration tests against real Alpha Vantage API."""
    
    def test_real_fetch(self):
        """Fetch real data from Alpha Vantage."""
        import os
        api_key = os.environ.get("ALPHA_VANTAGE_API_KEY")
        if not api_key:
            pytest.skip("ALPHA_VANTAGE_API_KEY not set")
        
        source = AlphaVantageSource(api_key=api_key)
        result = source.fetch({"symbol": "AAPL", "outputsize": "compact"})
        
        assert result.success is True
        assert len(result.data) > 0
        assert result.metadata.content_hash is not None
