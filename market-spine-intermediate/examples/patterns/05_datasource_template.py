"""
Pattern 05: Datasource Template

Use this as a starting point for implementing new data sources.
Covers: API sources, file sources, rate limiting, error handling.

Run: uv run python -m examples.patterns.05_datasource_template
"""

import time
import random
from datetime import datetime, timezone
from typing import Any, Protocol
from dataclasses import dataclass, field
from abc import ABC, abstractmethod


# =============================================================================
# Source Protocol (What all sources must implement)
# =============================================================================

class Source(Protocol):
    """Protocol that all data sources must implement."""
    
    def validate_config(self, config: dict[str, Any]) -> tuple[bool, str | None]:
        """Validate configuration. Returns (is_valid, error_message)."""
        ...
    
    def fetch(self, params: dict[str, Any]) -> tuple[list[dict], list[dict]]:
        """Fetch data. Returns (data, anomalies)."""
        ...


# =============================================================================
# Rate Limiter (Reusable for API sources)
# =============================================================================

class RateLimiter:
    """
    Simple rate limiter for API calls.
    
    Usage:
        limiter = RateLimiter(calls_per_minute=5)
        limiter.wait_if_needed()  # Blocks if rate exceeded
    """
    
    def __init__(self, calls_per_minute: int = 5):
        self.min_interval = 60.0 / calls_per_minute
        self.last_call: float | None = None
    
    def wait_if_needed(self) -> None:
        """Block if we need to wait for rate limit."""
        if self.last_call is not None:
            elapsed = time.time() - self.last_call
            if elapsed < self.min_interval:
                sleep_time = self.min_interval - elapsed
                print(f"    ⏳ Rate limiting: waiting {sleep_time:.1f}s")
                time.sleep(sleep_time)
        self.last_call = time.time()


# =============================================================================
# Anomaly Helper (Standardized error recording)
# =============================================================================

@dataclass
class Anomaly:
    """Standardized anomaly record."""
    domain: str
    stage: str
    severity: str  # DEBUG, INFO, WARN, ERROR, CRITICAL
    category: str  # NETWORK, RATE_LIMIT, DATA_QUALITY, VALIDATION, PARSE
    message: str
    partition_key: str = ""
    metadata: dict = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        return {
            "domain": self.domain,
            "stage": self.stage,
            "severity": self.severity,
            "category": self.category,
            "message": self.message,
            "partition_key": self.partition_key,
            "metadata": self.metadata,
            "detected_at": datetime.now(timezone.utc).isoformat(),
        }


def create_anomaly(
    domain: str,
    stage: str,
    severity: str,
    category: str,
    message: str,
    **metadata,
) -> dict:
    """Create standardized anomaly dict."""
    return Anomaly(
        domain=domain,
        stage=stage,
        severity=severity,
        category=category,
        message=message,
        metadata=metadata,
    ).to_dict()


# =============================================================================
# Base Source Class (Inherit from this)
# =============================================================================

class BaseSource(ABC):
    """
    Base class for data sources.
    
    Provides common functionality:
    - Config validation
    - Anomaly creation helpers
    - Rate limiting support
    """
    
    domain: str = "unknown"
    stage: str = "INGEST"
    
    def __init__(self, config: dict[str, Any]):
        is_valid, error = self.validate_config(config)
        if not is_valid:
            raise ValueError(f"Invalid config: {error}")
        self.config = config
    
    @abstractmethod
    def validate_config(self, config: dict[str, Any]) -> tuple[bool, str | None]:
        """Validate configuration. Override in subclass."""
        pass
    
    @abstractmethod
    def fetch(self, params: dict[str, Any]) -> tuple[list[dict], list[dict]]:
        """Fetch data. Override in subclass."""
        pass
    
    def _create_anomaly(
        self,
        severity: str,
        category: str,
        message: str,
        **metadata,
    ) -> dict:
        """Helper to create anomaly with domain/stage set."""
        return create_anomaly(
            domain=self.domain,
            stage=self.stage,
            severity=severity,
            category=category,
            message=message,
            **metadata,
        )


# =============================================================================
# Example: API Source Template
# =============================================================================

class ExampleAPISource(BaseSource):
    """
    Template for API-based data sources.
    
    Features:
    - API key authentication
    - Rate limiting
    - Error handling with anomaly recording
    - Retry-able vs non-retryable error distinction
    
    Config:
        api_key: Required API key
        base_url: Optional base URL (has default)
        timeout: Optional timeout in seconds (default: 30)
    """
    
    domain = "example"
    stage = "INGEST"
    
    DEFAULT_BASE_URL = "https://api.example.com/v1"
    
    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self.api_key = config["api_key"]
        self.base_url = config.get("base_url", self.DEFAULT_BASE_URL)
        self.timeout = config.get("timeout", 30)
        self._rate_limiter = RateLimiter(calls_per_minute=5)
    
    def validate_config(self, config: dict[str, Any]) -> tuple[bool, str | None]:
        """Validate API source configuration."""
        if "api_key" not in config:
            return False, "Missing required config: api_key"
        if not config["api_key"]:
            return False, "api_key cannot be empty"
        return True, None
    
    def fetch(self, params: dict[str, Any]) -> tuple[list[dict], list[dict]]:
        """
        Fetch data from API.
        
        Args:
            params: Request parameters (symbol, date, etc.)
        
        Returns:
            (data, anomalies) tuple
        """
        self._rate_limiter.wait_if_needed()
        
        try:
            # Simulate API call (replace with real httpx/requests call)
            response = self._make_request(params)
            data = self._parse_response(response, params)
            return data, []
            
        except TimeoutError as e:
            # Transient error - can retry
            return [], [self._create_anomaly(
                severity="ERROR",
                category="NETWORK",
                message=f"Request timeout: {e}",
                retryable=True,
            )]
            
        except ConnectionError as e:
            # Transient error - can retry
            return [], [self._create_anomaly(
                severity="ERROR",
                category="NETWORK",
                message=f"Connection failed: {e}",
                retryable=True,
            )]
            
        except ValueError as e:
            # Parse error - likely not retryable
            return [], [self._create_anomaly(
                severity="ERROR",
                category="PARSE",
                message=f"Failed to parse response: {e}",
                retryable=False,
            )]
    
    def _make_request(self, params: dict[str, Any]) -> dict:
        """
        Make API request. Override for real implementation.
        
        In real code:
            response = httpx.get(
                f"{self.base_url}/data",
                params=params,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=self.timeout,
            )
            response.raise_for_status()
            return response.json()
        """
        # Simulated response
        symbol = params.get("symbol", "AAPL")
        return {
            "symbol": symbol,
            "prices": [
                {"date": "2025-01-09", "close": 150.0},
                {"date": "2025-01-10", "close": 152.5},
            ],
            "meta": {"source": "example_api"},
        }
    
    def _parse_response(self, response: dict, params: dict) -> list[dict]:
        """Parse API response into standardized records."""
        symbol = response.get("symbol")
        records = []
        
        for price in response.get("prices", []):
            records.append({
                "symbol": symbol,
                "date": price["date"],
                "close": price["close"],
                "source": "example_api",
            })
        
        return records


# =============================================================================
# Example: File Source Template
# =============================================================================

class ExampleFileSource(BaseSource):
    """
    Template for file-based data sources.
    
    Features:
    - File path validation
    - Format detection (CSV, JSON, PSV)
    - Error handling for missing/corrupt files
    
    Config:
        data_dir: Directory containing data files
        file_format: Optional format hint (csv, json, psv)
    """
    
    domain = "example"
    stage = "INGEST"
    
    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self.data_dir = config["data_dir"]
        self.file_format = config.get("file_format", "csv")
    
    def validate_config(self, config: dict[str, Any]) -> tuple[bool, str | None]:
        """Validate file source configuration."""
        if "data_dir" not in config:
            return False, "Missing required config: data_dir"
        # In real code, check if directory exists
        return True, None
    
    def fetch(self, params: dict[str, Any]) -> tuple[list[dict], list[dict]]:
        """
        Fetch data from file.
        
        Args:
            params: Should include 'filename' or date to construct path
        
        Returns:
            (data, anomalies) tuple
        """
        filename = params.get("filename", "data.csv")
        filepath = f"{self.data_dir}/{filename}"
        
        try:
            # Simulate file read
            data = self._read_file(filepath)
            validated, anomalies = self._validate_data(data)
            return validated, anomalies
            
        except FileNotFoundError:
            return [], [self._create_anomaly(
                severity="ERROR",
                category="NETWORK",  # File not found treated like network error
                message=f"File not found: {filepath}",
                filepath=filepath,
            )]
            
        except PermissionError:
            return [], [self._create_anomaly(
                severity="ERROR",
                category="NETWORK",
                message=f"Permission denied: {filepath}",
                filepath=filepath,
            )]
    
    def _read_file(self, filepath: str) -> list[dict]:
        """Read and parse file. Override for real implementation."""
        # Simulated file contents
        return [
            {"symbol": "AAPL", "volume": 1000000, "date": "2025-01-09"},
            {"symbol": "TSLA", "volume": 500000, "date": "2025-01-09"},
            {"symbol": "MSFT", "volume": None, "date": "2025-01-09"},  # Bad record
        ]
    
    def _validate_data(self, data: list[dict]) -> tuple[list[dict], list[dict]]:
        """Validate records, return (valid_data, anomalies)."""
        valid = []
        anomalies = []
        
        for i, record in enumerate(data):
            # Check for null values in required fields
            if record.get("volume") is None:
                anomalies.append(self._create_anomaly(
                    severity="WARN",
                    category="DATA_QUALITY",
                    message=f"Null volume in record {i}",
                    record_index=i,
                    symbol=record.get("symbol"),
                ))
                continue  # Skip invalid record
            
            valid.append(record)
        
        return valid, anomalies


# =============================================================================
# Example: HTTP Endpoint Source Template
# =============================================================================

class HTTPEndpointSource(BaseSource):
    """
    Template for fetching data from HTTP REST endpoints.
    
    Features:
    - Configurable base URL and endpoints
    - Authentication (Bearer token, API key, Basic)
    - Retry logic with exponential backoff
    - Response parsing (JSON)
    - Rate limiting
    
    Config:
        base_url: Base URL for the API (required)
        auth_type: "bearer", "api_key", "basic", or None
        auth_token: Token for bearer auth
        api_key: Key for api_key auth
        username/password: For basic auth
        timeout: Request timeout in seconds (default: 30)
        max_retries: Max retry attempts (default: 3)
    
    Example:
        source = HTTPEndpointSource({
            "base_url": "https://api.example.com",
            "auth_type": "bearer",
            "auth_token": "your-token-here",
            "timeout": 30,
        })
        data, anomalies = source.fetch({"endpoint": "/v1/prices", "symbol": "AAPL"})
    """
    
    domain = "http"
    stage = "INGEST"
    
    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self.base_url = config["base_url"].rstrip("/")
        self.auth_type = config.get("auth_type")  # bearer, api_key, basic, None
        self.auth_token = config.get("auth_token")
        self.api_key = config.get("api_key")
        self.api_key_header = config.get("api_key_header", "X-API-Key")
        self.username = config.get("username")
        self.password = config.get("password")
        self.timeout = config.get("timeout", 30)
        self.max_retries = config.get("max_retries", 3)
        self._rate_limiter = RateLimiter(
            calls_per_minute=config.get("calls_per_minute", 300)  # 5 req/sec default
        )
    
    def validate_config(self, config: dict[str, Any]) -> tuple[bool, str | None]:
        """Validate HTTP source configuration."""
        if "base_url" not in config:
            return False, "Missing required config: base_url"
        
        base_url = config["base_url"]
        if not base_url.startswith(("http://", "https://")):
            return False, f"Invalid base_url: must start with http:// or https://"
        
        auth_type = config.get("auth_type")
        if auth_type == "bearer" and not config.get("auth_token"):
            return False, "auth_type='bearer' requires auth_token"
        if auth_type == "api_key" and not config.get("api_key"):
            return False, "auth_type='api_key' requires api_key"
        if auth_type == "basic" and not (config.get("username") and config.get("password")):
            return False, "auth_type='basic' requires username and password"
        
        return True, None
    
    def fetch(self, params: dict[str, Any]) -> tuple[list[dict], list[dict]]:
        """
        Fetch data from HTTP endpoint.
        
        Args:
            params: Request parameters
                - endpoint: Path to append to base_url (e.g., "/v1/prices")
                - method: HTTP method (default: "GET")
                - query_params: Dict of query parameters
                - body: Request body for POST/PUT
                - headers: Additional headers
        
        Returns:
            (data, anomalies) tuple
        """
        self._rate_limiter.wait_if_needed()
        
        endpoint = params.get("endpoint", "/")
        method = params.get("method", "GET").upper()
        query_params = params.get("query_params", {})
        body = params.get("body")
        extra_headers = params.get("headers", {})
        
        url = f"{self.base_url}{endpoint}"
        headers = self._build_headers(extra_headers)
        
        last_error = None
        for attempt in range(self.max_retries):
            try:
                response = self._make_http_request(
                    method=method,
                    url=url,
                    headers=headers,
                    query_params=query_params,
                    body=body,
                )
                
                # Parse response
                data = self._parse_response(response, params)
                return data, []
                
            except TimeoutError as e:
                last_error = e
                wait_time = 2 ** attempt  # Exponential backoff
                self._wait(wait_time)
                continue
                
            except ConnectionError as e:
                last_error = e
                wait_time = 2 ** attempt
                self._wait(wait_time)
                continue
                
            except ValueError as e:
                # Parse error - not retryable
                return [], [self._create_anomaly(
                    severity="ERROR",
                    category="PARSE",
                    message=f"Failed to parse response from {url}: {e}",
                    url=url,
                    retryable=False,
                )]
        
        # All retries exhausted
        return [], [self._create_anomaly(
            severity="ERROR",
            category="NETWORK",
            message=f"Failed after {self.max_retries} retries: {last_error}",
            url=url,
            retryable=True,
        )]
    
    def _build_headers(self, extra_headers: dict) -> dict:
        """Build request headers with authentication."""
        headers = {
            "Accept": "application/json",
            "User-Agent": "spine-core/1.0",
            **extra_headers,
        }
        
        if self.auth_type == "bearer":
            headers["Authorization"] = f"Bearer {self.auth_token}"
        elif self.auth_type == "api_key":
            headers[self.api_key_header] = self.api_key
        elif self.auth_type == "basic":
            import base64
            credentials = base64.b64encode(
                f"{self.username}:{self.password}".encode()
            ).decode()
            headers["Authorization"] = f"Basic {credentials}"
        
        return headers
    
    def _make_http_request(
        self,
        method: str,
        url: str,
        headers: dict,
        query_params: dict,
        body: Any,
    ) -> dict:
        """
        Make HTTP request. Override for real implementation.
        
        In production, use httpx or requests:
        
            import httpx
            
            with httpx.Client(timeout=self.timeout) as client:
                if method == "GET":
                    response = client.get(url, headers=headers, params=query_params)
                elif method == "POST":
                    response = client.post(url, headers=headers, json=body)
                # etc.
                
                response.raise_for_status()
                return response.json()
        """
        # Simulated response for demo
        return {
            "status": "success",
            "data": [
                {"symbol": "AAPL", "price": 150.25, "timestamp": "2025-01-10T10:00:00Z"},
                {"symbol": "AAPL", "price": 150.50, "timestamp": "2025-01-10T11:00:00Z"},
            ],
            "meta": {
                "source": url,
                "request_id": "req-12345",
            }
        }
    
    def _parse_response(self, response: dict, params: dict) -> list[dict]:
        """
        Parse HTTP response into standardized records.
        
        Override this method to handle specific API response formats.
        """
        # Handle common response shapes
        if "data" in response:
            return response["data"]
        elif "results" in response:
            return response["results"]
        elif "items" in response:
            return response["items"]
        elif isinstance(response, list):
            return response
        else:
            # Wrap single object in list
            return [response]
    
    def _wait(self, seconds: float):
        """Wait for retry backoff. Override for testing."""
        import time
        time.sleep(seconds)


# =============================================================================
# Source Factory Pattern
# =============================================================================

# Registry of available sources
_SOURCE_REGISTRY: dict[str, type[BaseSource]] = {
    "example_api": ExampleAPISource,
    "example_file": ExampleFileSource,
    "http_endpoint": HTTPEndpointSource,
}


def register_source(name: str):
    """Decorator to register a source class."""
    def decorator(cls: type[BaseSource]) -> type[BaseSource]:
        _SOURCE_REGISTRY[name] = cls
        return cls
    return decorator


def create_source(source_type: str | None = None, **config) -> BaseSource:
    """
    Factory to create source from type or auto-detect.
    
    Usage:
        # Explicit type
        source = create_source("example_api", api_key="...")
        
        # Auto-detect from environment (in real code)
        source = create_source()  # Reads EXAMPLE_API_KEY env var
    """
    if source_type:
        if source_type not in _SOURCE_REGISTRY:
            available = ", ".join(_SOURCE_REGISTRY.keys())
            raise ValueError(f"Unknown source: {source_type}. Available: {available}")
        return _SOURCE_REGISTRY[source_type](config)
    
    # Auto-detect logic (simplified for demo)
    # In real code, check environment variables
    if config.get("api_key"):
        return ExampleAPISource(config)
    elif config.get("data_dir"):
        return ExampleFileSource(config)
    else:
        raise ValueError("Cannot auto-detect source type. Provide source_type or config.")


# =============================================================================
# Demo
# =============================================================================

def main():
    print("=" * 70)
    print("Pattern 05: Datasource Template")
    print("=" * 70)
    
    # Demo 1: API Source
    print("\n📡 API Source Demo:")
    print("-" * 50)
    
    api_source = create_source("example_api", api_key="demo_key_123")
    data, anomalies = api_source.fetch({"symbol": "AAPL"})
    
    print(f"  Records fetched: {len(data)}")
    for record in data:
        print(f"    {record}")
    print(f"  Anomalies: {len(anomalies)}")
    
    # Demo 2: File Source
    print("\n📁 File Source Demo:")
    print("-" * 50)
    
    file_source = create_source("example_file", data_dir="/data/finra")
    data, anomalies = file_source.fetch({"filename": "otc_data.csv"})
    
    print(f"  Valid records: {len(data)}")
    for record in data:
        print(f"    {record}")
    print(f"  Anomalies: {len(anomalies)}")
    for anomaly in anomalies:
        print(f"    ⚠️  [{anomaly['severity']}] {anomaly['message']}")
    
    # Demo 3: HTTP Endpoint Source
    print("\n🌐 HTTP Endpoint Source Demo:")
    print("-" * 50)
    
    http_source = create_source(
        "http_endpoint",
        base_url="https://api.example.com",
        auth_type="bearer",
        auth_token="demo-token-xyz",
        timeout=30,
    )
    
    data, anomalies = http_source.fetch({
        "endpoint": "/v1/prices",
        "query_params": {"symbol": "AAPL", "interval": "1h"},
    })
    
    print(f"  Records fetched: {len(data)}")
    for record in data:
        print(f"    {record}")
    print(f"  Anomalies: {len(anomalies)}")
    
    # Demo 4: Config Validation
    print("\n🔐 Config Validation Demo:")
    print("-" * 50)
    
    try:
        bad_source = create_source("example_api", api_key="")  # Empty key
    except ValueError as e:
        print(f"  ✅ Correctly rejected invalid config: {e}")
    
    try:
        bad_http = create_source(
            "http_endpoint",
            base_url="https://api.example.com",
            auth_type="bearer",
            # Missing auth_token!
        )
    except ValueError as e:
        print(f"  ✅ Correctly rejected missing auth_token: {e}")
    
    print("\n✅ Demo complete!")


if __name__ == "__main__":
    main()
