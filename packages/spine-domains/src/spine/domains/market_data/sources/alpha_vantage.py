"""
Alpha Vantage market data source.

Fetches daily OHLCV price data from the Alpha Vantage API.

Usage:
    source = AlphaVantageSource({
        "api_key": "YOUR_KEY",
        "base_url": "https://www.alphavantage.co/query",  # optional
        "timeout": 30,  # optional
    })
    result = source.fetch({"symbol": "AAPL", "outputsize": "compact"})
    data, anomalies, metadata = result.data, result.anomalies, result.metadata

Rate Limits:
    - Free tier: 25 requests/day, 5 requests/minute
    - Premium tiers available with higher limits

See: https://www.alphavantage.co/documentation/
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
import hashlib
import json
import time

# Try to import httpx for async-capable HTTP, fall back to urllib
try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    import urllib.request
    import urllib.error
    import json as json_lib
    HAS_HTTPX = False


# =============================================================================
# Source Metadata (per spine patterns)
# =============================================================================

@dataclass
class SourceMetadata:
    """
    Metadata about a fetch operation, following spine patterns.
    
    Used for:
    - Lineage tracking (source_type, source_uri)
    - Audit (fetched_at)
    - Caching/dedup (content_hash, etag, last_modified)
    """
    source_type: str
    source_uri: str
    fetched_at: str  # ISO timestamp
    content_hash: str  # SHA-256 of response data
    etag: str | None = None
    last_modified: str | None = None
    response_size_bytes: int = 0
    request_params_hash: str | None = None


@dataclass
class FetchResult:
    """Result of a fetch operation."""
    data: list[dict] = field(default_factory=list)
    anomalies: list[dict] = field(default_factory=list)
    metadata: SourceMetadata | None = None
    success: bool = True


# =============================================================================
# Source Base Class (local implementation to avoid spine-core dependency)
# =============================================================================

class Source(ABC):
    """Base class for data sources."""
    
    @abstractmethod
    def fetch(self, params: dict) -> FetchResult:
        """
        Fetch data for given parameters.
        
        Returns:
            FetchResult containing data, anomalies, and metadata
        """
        ...
    
    @abstractmethod
    def validate_config(self, config: dict) -> None:
        """Validate configuration, raise ValueError if invalid."""
        ...


# =============================================================================
# Source Registry (local implementation)
# =============================================================================

SOURCES: dict[str, type[Source]] = {}


def register_source(name: str):
    """Decorator to register a source in the registry."""
    def decorator(cls: type[Source]) -> type[Source]:
        SOURCES[name] = cls
        return cls
    return decorator


# =============================================================================
# Alpha Vantage Source Implementation
# =============================================================================

@dataclass
class RateLimiter:
    """Simple rate limiter for API calls."""
    
    calls_per_minute: int = 5
    calls_per_day: int = 25
    
    _minute_calls: list = None
    _day_calls: list = None
    
    def __post_init__(self):
        self._minute_calls = []
        self._day_calls = []
    
    def check_and_record(self) -> tuple[bool, str | None]:
        """
        Check if we can make a call, record it if yes.
        
        Returns:
            (can_proceed, error_message)
        """
        now = time.time()
        minute_ago = now - 60
        day_ago = now - 86400
        
        # Clean old entries
        self._minute_calls = [t for t in self._minute_calls if t > minute_ago]
        self._day_calls = [t for t in self._day_calls if t > day_ago]
        
        # Check limits
        if len(self._minute_calls) >= self.calls_per_minute:
            return False, f"Rate limit: {self.calls_per_minute} calls/minute exceeded"
        
        if len(self._day_calls) >= self.calls_per_day:
            return False, f"Rate limit: {self.calls_per_day} calls/day exceeded"
        
        # Record call
        self._minute_calls.append(now)
        self._day_calls.append(now)
        
        return True, None


@register_source("alpha_vantage")
class AlphaVantageSource(Source):
    """
    Fetches daily OHLCV price data from Alpha Vantage.
    
    Config:
        api_key: API key for authentication (required)
        base_url: Base URL (optional, default: https://www.alphavantage.co/query)
        timeout: Request timeout in seconds (default: 30)
        calls_per_minute: Rate limit per minute (default: 5)
        calls_per_day: Rate limit per day (default: 25)
        max_retries: Maximum retry attempts (default: 3)
        retry_backoff_base: Base backoff in seconds (default: 1.0)
    
    Params:
        symbol: Stock ticker symbol (e.g., "AAPL")
        outputsize: "compact" (100 days) or "full" (20+ years)
    """
    
    DEFAULT_BASE_URL = "https://www.alphavantage.co/query"
    DOMAIN = "market_data"
    
    def __init__(self, config: dict, http_client=None):
        """
        Initialize source with config.
        
        Args:
            config: Configuration dict
            http_client: Optional HTTP client for testing (mock injection)
        """
        self.validate_config(config)
        self.api_key = config["api_key"]
        self.base_url = config.get("base_url", self.DEFAULT_BASE_URL)
        self.timeout = config.get("timeout", 30)
        self.max_retries = config.get("max_retries", 3)
        self.retry_backoff_base = config.get("retry_backoff_base", 1.0)
        self.rate_limiter = RateLimiter(
            calls_per_minute=config.get("calls_per_minute", 5),
            calls_per_day=config.get("calls_per_day", 25),
        )
        self._http_client = http_client  # For testing
    
    def validate_config(self, config: dict) -> None:
        """Validate required config fields."""
        required = ["api_key"]
        missing = [f for f in required if f not in config or not config[f]]
        if missing:
            raise ValueError(f"Missing required config: {missing}")
    
    def fetch(self, params: dict) -> FetchResult:
        """
        Fetch daily price data for a symbol with retry support.
        
        Args:
            params: Dict with:
                - symbol: Stock ticker (required)
                - outputsize: "compact" or "full" (default: "compact")
        
        Returns:
            FetchResult with data, anomalies, and metadata
        """
        symbol = params.get("symbol")
        if not symbol:
            return FetchResult(
                success=False,
                anomalies=[self._create_anomaly("VALIDATION", "Missing required param: symbol", params)],
            )
        
        symbol = symbol.upper()
        outputsize = params.get("outputsize", "compact")
        fetched_at = datetime.utcnow().isoformat() + "Z"
        
        # Check rate limit
        can_proceed, rate_error = self.rate_limiter.check_and_record()
        if not can_proceed:
            return FetchResult(
                success=False,
                anomalies=[self._create_anomaly("RATE_LIMIT", rate_error, params, severity="WARN")],
            )
        
        # Build request URL (without API key for logging)
        request_params = {
            "function": "TIME_SERIES_DAILY",
            "symbol": symbol,
            "outputsize": outputsize,
        }
        request_params_hash = self._hash_params(request_params)
        
        url = (
            f"{self.base_url}"
            f"?function=TIME_SERIES_DAILY"
            f"&symbol={symbol}"
            f"&outputsize={outputsize}"
            f"&apikey={self.api_key}"
        )
        
        # Retry loop with exponential backoff
        last_error = None
        response_data = None
        response_size = 0
        
        for attempt in range(self.max_retries):
            try:
                response_data, response_size = self._make_request_with_size(url)
                break  # Success
            except Exception as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    backoff = self.retry_backoff_base * (2 ** attempt)
                    time.sleep(backoff)
                continue
        
        if response_data is None:
            return FetchResult(
                success=False,
                anomalies=[self._create_anomaly(
                    "NETWORK", 
                    f"Failed after {self.max_retries} retries: {last_error}", 
                    params
                )],
            )
        
        # Compute content hash for dedup/lineage
        content_hash = self._compute_content_hash(response_data)
        
        # Build metadata
        metadata = SourceMetadata(
            source_type="alpha_vantage",
            source_uri=f"{self.base_url}?function=TIME_SERIES_DAILY&symbol={symbol}",
            fetched_at=fetched_at,
            content_hash=content_hash,
            response_size_bytes=response_size,
            request_params_hash=request_params_hash,
        )
        
        # Parse response
        try:
            data = self._parse_response(response_data, symbol, params)
            return FetchResult(data=data, metadata=metadata, success=True)
        except ValueError as e:
            return FetchResult(
                success=False,
                anomalies=[self._create_anomaly("DATA_QUALITY", str(e), params)],
                metadata=metadata,
            )
    
    def _compute_content_hash(self, data: dict) -> str:
        """Compute deterministic SHA-256 hash of response data."""
        # Sort keys for determinism
        serialized = json.dumps(data, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(serialized.encode()).hexdigest()
    
    def _hash_params(self, params: dict) -> str:
        """Hash request parameters for tracking."""
        serialized = json.dumps(params, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(serialized.encode()).hexdigest()[:16]
    
    def _make_request_with_size(self, url: str) -> tuple[dict, int]:
        """Make HTTP request and return (JSON response, response size)."""
        # Use injected client if available (for testing)
        if self._http_client is not None:
            response = self._http_client.get(url)
            if hasattr(response, 'raise_for_status'):
                response.raise_for_status()
            data = response.json() if hasattr(response, 'json') else response
            return data, len(json.dumps(data))
        
        if HAS_HTTPX:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.get(url)
                response.raise_for_status()
                content = response.content
                return response.json(), len(content)
        else:
            # Fallback to urllib
            request = urllib.request.Request(url)
            request.add_header("User-Agent", "Market-Spine/1.0")
            
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    content = response.read()
                    return json_lib.loads(content.decode()), len(content)
            except urllib.error.HTTPError as e:
                raise RuntimeError(f"HTTP {e.code}: {e.reason}")
            except urllib.error.URLError as e:
                raise RuntimeError(f"Network error: {e.reason}")
    
    def _parse_response(self, response: dict, symbol: str, params: dict) -> list[dict]:
        """
        Parse Alpha Vantage TIME_SERIES_DAILY response.
        
        Response format:
        {
            "Meta Data": {...},
            "Time Series (Daily)": {
                "2024-01-05": {
                    "1. open": "180.50",
                    "2. high": "181.20",
                    "3. low": "179.30",
                    "4. close": "180.80",
                    "5. volume": "50000000"
                },
                ...
            }
        }
        """
        # Check for API error messages
        if "Error Message" in response:
            raise ValueError(f"API error: {response['Error Message']}")
        
        if "Note" in response:
            # Rate limit message from Alpha Vantage
            raise ValueError(f"API rate limit: {response['Note']}")
        
        time_series = response.get("Time Series (Daily)")
        if not time_series:
            raise ValueError("Missing 'Time Series (Daily)' in response")
        
        records = []
        for date_str, values in time_series.items():
            try:
                record = {
                    "symbol": symbol,
                    "date": date_str,
                    "open": float(values.get("1. open", 0)),
                    "high": float(values.get("2. high", 0)),
                    "low": float(values.get("3. low", 0)),
                    "close": float(values.get("4. close", 0)),
                    "volume": int(float(values.get("5. volume", 0))),
                }
                records.append(record)
            except (ValueError, TypeError) as e:
                # Skip malformed records but continue
                continue
        
        if not records:
            raise ValueError("No valid price records found in response")
        
        # Sort by date descending (most recent first)
        records.sort(key=lambda r: r["date"], reverse=True)
        
        return records
    
    def _create_anomaly(
        self, 
        category: str, 
        message: str, 
        params: dict,
        severity: str = "ERROR"
    ) -> dict:
        """Create a standardized anomaly record."""
        return {
            "domain": self.DOMAIN,
            "stage": "INGEST",
            "partition_key": f"{params.get('symbol', 'UNKNOWN')}|{datetime.utcnow().date().isoformat()}",
            "severity": severity,
            "category": category,
            "message": message,
            "detected_at": datetime.utcnow().isoformat() + "Z",
            "metadata": {
                "source": "alpha_vantage",
                "params": params,
            },
        }


# =============================================================================
# Convenience function
# =============================================================================

def get_alpha_vantage_source(api_key: str, **kwargs) -> AlphaVantageSource:
    """
    Factory function to create an Alpha Vantage source.
    
    Usage:
        source = get_alpha_vantage_source("YOUR_API_KEY")
        data, anomalies = source.fetch({"symbol": "AAPL"})
    """
    config = {"api_key": api_key, **kwargs}
    return AlphaVantageSource(config)
