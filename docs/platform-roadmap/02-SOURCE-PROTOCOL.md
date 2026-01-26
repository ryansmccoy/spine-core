# Unified Source Protocol

> **Purpose:** Define a common interface for all data sources (files, APIs, databases).
> **Tier:** Basic (spine-core)
> **Module:** `spine.framework.sources`
> **Last Updated:** 2026-01-11

---

## Overview

Every data pipeline needs to fetch data from somewhere. Currently, each domain implements its own source abstraction:

- FINRA: `IngestionSource`, `FileSource`, `APISource`
- Market Data: `PriceSource`, `AlphaVantageSource`
- Reference: `IngestionSource`, `JsonSource`

This creates duplicate code, inconsistent error handling, and makes testing harder.

The **Unified Source Protocol** provides:
- Common interface for all sources
- Consistent result envelope
- Error categorization for retry decisions
- Streaming support for large datasets
- Composable wrappers (retry, rate limit, cache)

---

## Design Principles

1. **Protocol-Based** - Use `typing.Protocol` for duck typing (Principle #2)
2. **Result Envelope** - Always return `SourceResult`, never raise for data issues (Principle #7)
3. **Streaming First** - Support both batch and streaming modes
4. **Composable** - Wrappers can add behavior (retry, cache, rate limit) (Principle #4)
5. **Registry-Driven** - Sources register with `@register_source` (Principle #3)

> **Design Principles Applied:**
> - **Write Once (#1):** Adding a new source type (e.g., S3, Kafka) requires only a new file
> - **Protocol-First (#2):** `Source` protocol defines contract before implementations
> - **Errors as Values (#7):** `SourceResult.errors` instead of raising exceptions

---

## Core Types

### SourceResult

```python
# spine/framework/sources/result.py
from dataclasses import dataclass, field
from typing import Any, Iterator
from datetime import datetime

@dataclass(frozen=True)  # Principle #5: Immutability by Default
class SourceMetadata:
    """Metadata about the source fetch."""
    source_type: str              # "file", "http", "database"
    source_name: str              # Identifier (path, URL, table)
    fetched_at: datetime          # When fetch completed
    record_count: int             # Number of records
    byte_count: int | None = None # Size in bytes (if known)
    content_hash: str | None = None  # For change detection
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class SourceResult:
    """
    Result from fetching data from a source.
    
    This is the universal envelope returned by all sources.
    Errors are captured in the `errors` list, not raised.
    """
    records: list[dict[str, Any]]
    metadata: SourceMetadata
    errors: list[str] = field(default_factory=list)
    
    @property
    def success(self) -> bool:
        """True if no errors occurred."""
        return len(self.errors) == 0
    
    @property
    def record_count(self) -> int:
        """Number of records fetched."""
        return len(self.records)
    
    @classmethod
    def empty(cls, source_type: str, source_name: str) -> "SourceResult":
        """Create an empty result."""
        return cls(
            records=[],
            metadata=SourceMetadata(
                source_type=source_type,
                source_name=source_name,
                fetched_at=datetime.utcnow(),
                record_count=0,
            ),
        )
    
    @classmethod
    def error(cls, source_type: str, source_name: str, error: str) -> "SourceResult":
        """Create an error result."""
        return cls(
            records=[],
            metadata=SourceMetadata(
                source_type=source_type,
                source_name=source_name,
                fetched_at=datetime.utcnow(),
                record_count=0,
            ),
            errors=[error],
        )
```

### Source Protocol

```python
# spine/framework/sources/protocol.py
from typing import Protocol, Iterator, Any, runtime_checkable

@runtime_checkable
class Source(Protocol):
    """
    Protocol for all data sources.
    
    Sources fetch data from external systems (files, APIs, databases).
    They return a SourceResult with records and metadata.
    
    Example:
        source = FileSource(path="data/finra.psv", format="psv")
        result = source.fetch({"tier": "NMS_TIER_1"})
        
        if result.success:
            for record in result.records:
                process(record)
        else:
            for error in result.errors:
                log.error(error)
    """
    
    @property
    def source_type(self) -> str:
        """Source type identifier (e.g., 'file', 'http', 'database')."""
        ...
    
    @property
    def source_name(self) -> str:
        """Source name for logging (e.g., file path, URL, table name)."""
        ...
    
    def fetch(self, params: dict[str, Any] | None = None) -> SourceResult:
        """
        Fetch all records from source.
        
        Args:
            params: Optional parameters for the fetch
            
        Returns:
            SourceResult with records and metadata
        """
        ...
    
    def stream(self, params: dict[str, Any] | None = None) -> Iterator[dict[str, Any]]:
        """
        Stream records from source (for large datasets).
        
        Default implementation calls fetch() and yields records.
        Override for true streaming (e.g., database cursors).
        
        Args:
            params: Optional parameters for the fetch
            
        Yields:
            Individual records
        """
        result = self.fetch(params)
        yield from result.records
    
    def validate(self) -> list[str]:
        """
        Validate source configuration.
        
        Returns:
            List of validation errors (empty if valid)
        """
        return []
```

---

## Source Implementations

### FileSource

```python
# spine/framework/sources/file.py
import csv
import json
from pathlib import Path
from dataclasses import dataclass
from typing import Any, Iterator
from datetime import datetime

from spine.core.errors import SourceError
from spine.framework.sources.protocol import Source
from spine.framework.sources.result import SourceResult, SourceMetadata


@dataclass
class FileSource:
    """
    Read records from local files.
    
    Supports: CSV, PSV, JSON, JSONL, Parquet
    
    Example:
        source = FileSource(path="data/finra.psv", format="psv")
        result = source.fetch()
    """
    path: str | Path
    format: str = "auto"  # csv, psv, json, jsonl, parquet, auto
    encoding: str = "utf-8"
    delimiter: str | None = None  # Auto-detect if None
    
    # CSV options
    has_header: bool = True
    skip_rows: int = 0
    
    @property
    def source_type(self) -> str:
        return "file"
    
    @property
    def source_name(self) -> str:
        return str(self.path)
    
    def fetch(self, params: dict[str, Any] | None = None) -> SourceResult:
        """Read all records from file."""
        path = Path(self.path)
        
        # Validate file exists
        if not path.exists():
            return SourceResult.error(
                self.source_type,
                self.source_name,
                f"File not found: {path}",
            )
        
        # Detect format
        file_format = self._detect_format(path)
        
        try:
            if file_format in ("csv", "psv", "tsv"):
                records = self._read_delimited(path, file_format)
            elif file_format == "json":
                records = self._read_json(path)
            elif file_format == "jsonl":
                records = self._read_jsonl(path)
            elif file_format == "parquet":
                records = self._read_parquet(path)
            else:
                return SourceResult.error(
                    self.source_type,
                    self.source_name,
                    f"Unsupported format: {file_format}",
                )
            
            return SourceResult(
                records=records,
                metadata=SourceMetadata(
                    source_type=self.source_type,
                    source_name=self.source_name,
                    fetched_at=datetime.utcnow(),
                    record_count=len(records),
                    byte_count=path.stat().st_size,
                ),
            )
            
        except Exception as e:
            return SourceResult.error(
                self.source_type,
                self.source_name,
                f"Error reading file: {e}",
            )
    
    def stream(self, params: dict[str, Any] | None = None) -> Iterator[dict[str, Any]]:
        """Stream records from file (memory efficient)."""
        path = Path(self.path)
        file_format = self._detect_format(path)
        
        if file_format in ("csv", "psv", "tsv"):
            yield from self._stream_delimited(path, file_format)
        elif file_format == "jsonl":
            yield from self._stream_jsonl(path)
        else:
            # Fall back to batch for formats that don't stream well
            result = self.fetch(params)
            yield from result.records
    
    def _detect_format(self, path: Path) -> str:
        """Detect file format from extension or explicit setting."""
        if self.format != "auto":
            return self.format
        
        suffix = path.suffix.lower()
        formats = {
            ".csv": "csv",
            ".psv": "psv",
            ".tsv": "tsv",
            ".json": "json",
            ".jsonl": "jsonl",
            ".parquet": "parquet",
            ".pq": "parquet",
        }
        return formats.get(suffix, "csv")
    
    def _get_delimiter(self, file_format: str) -> str:
        """Get delimiter for format."""
        if self.delimiter:
            return self.delimiter
        delimiters = {"csv": ",", "psv": "|", "tsv": "\t"}
        return delimiters.get(file_format, ",")
    
    def _read_delimited(self, path: Path, file_format: str) -> list[dict]:
        """Read delimited file."""
        delimiter = self._get_delimiter(file_format)
        records = []
        
        with open(path, "r", encoding=self.encoding) as f:
            # Skip rows
            for _ in range(self.skip_rows):
                next(f, None)
            
            if self.has_header:
                reader = csv.DictReader(f, delimiter=delimiter)
            else:
                # Generate column names
                first_line = f.readline()
                f.seek(0)
                for _ in range(self.skip_rows):
                    next(f, None)
                num_cols = len(first_line.split(delimiter))
                fieldnames = [f"col_{i}" for i in range(num_cols)]
                reader = csv.DictReader(f, fieldnames=fieldnames, delimiter=delimiter)
            
            records = list(reader)
        
        return records
    
    def _stream_delimited(self, path: Path, file_format: str) -> Iterator[dict]:
        """Stream delimited file."""
        delimiter = self._get_delimiter(file_format)
        
        with open(path, "r", encoding=self.encoding) as f:
            for _ in range(self.skip_rows):
                next(f, None)
            
            reader = csv.DictReader(f, delimiter=delimiter)
            yield from reader
    
    def _read_json(self, path: Path) -> list[dict]:
        """Read JSON file (array or object)."""
        with open(path, "r", encoding=self.encoding) as f:
            data = json.load(f)
        
        if isinstance(data, list):
            return data
        elif isinstance(data, dict):
            return [data]
        else:
            return []
    
    def _read_jsonl(self, path: Path) -> list[dict]:
        """Read JSON Lines file."""
        records = []
        with open(path, "r", encoding=self.encoding) as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
        return records
    
    def _stream_jsonl(self, path: Path) -> Iterator[dict]:
        """Stream JSON Lines file."""
        with open(path, "r", encoding=self.encoding) as f:
            for line in f:
                line = line.strip()
                if line:
                    yield json.loads(line)
    
    def _read_parquet(self, path: Path) -> list[dict]:
        """Read Parquet file."""
        try:
            import pyarrow.parquet as pq
            table = pq.read_table(path)
            return table.to_pylist()
        except ImportError:
            raise SourceError("pyarrow required for Parquet support")
    
    def validate(self) -> list[str]:
        """Validate file source configuration."""
        errors = []
        path = Path(self.path)
        
        if not path.exists():
            errors.append(f"File not found: {path}")
        elif not path.is_file():
            errors.append(f"Not a file: {path}")
        
        return errors
```

### HttpSource

```python
# spine/framework/sources/http.py
import json
from dataclasses import dataclass, field
from typing import Any, Iterator
from datetime import datetime
from urllib.parse import urljoin

from spine.core.errors import SourceError, TransientError
from spine.framework.sources.protocol import Source
from spine.framework.sources.result import SourceResult, SourceMetadata


@dataclass
class HttpSource:
    """
    Fetch records from HTTP/REST APIs.
    
    Supports:
    - GET/POST requests
    - Authentication (API key, Bearer token, Basic auth)
    - Pagination (offset, cursor, link header)
    - Response parsing (JSON, JSON array, nested path)
    
    Example:
        source = HttpSource(
            url="https://api.example.com/data",
            auth={"type": "api_key", "header": "X-API-Key", "value": "secret"},
        )
        result = source.fetch({"page": 1})
    """
    url: str
    method: str = "GET"
    headers: dict[str, str] = field(default_factory=dict)
    auth: dict[str, str] | None = None  # type, header, value
    timeout: int = 30
    
    # Response parsing
    data_path: str | None = None  # JSON path to records (e.g., "data.items")
    
    # Pagination
    pagination: dict[str, Any] | None = None  # type, param, per_page
    
    @property
    def source_type(self) -> str:
        return "http"
    
    @property
    def source_name(self) -> str:
        return self.url
    
    def fetch(self, params: dict[str, Any] | None = None) -> SourceResult:
        """Fetch all records from API (handles pagination)."""
        try:
            import requests
        except ImportError:
            return SourceResult.error(
                self.source_type,
                self.source_name,
                "requests library required for HTTP sources",
            )
        
        all_records = []
        page_params = dict(params or {})
        
        try:
            while True:
                # Build request
                headers = self._build_headers()
                
                if self.method.upper() == "GET":
                    response = requests.get(
                        self.url,
                        headers=headers,
                        params=page_params,
                        timeout=self.timeout,
                    )
                else:
                    response = requests.post(
                        self.url,
                        headers=headers,
                        json=page_params,
                        timeout=self.timeout,
                    )
                
                # Check for errors
                if response.status_code >= 500:
                    raise TransientError(f"Server error: {response.status_code}")
                elif response.status_code >= 400:
                    raise SourceError(f"Client error: {response.status_code}")
                
                # Parse response
                data = response.json()
                records = self._extract_records(data)
                all_records.extend(records)
                
                # Check pagination
                if not self.pagination:
                    break
                
                next_page = self._get_next_page(data, page_params, response)
                if next_page is None:
                    break
                page_params = next_page
            
            return SourceResult(
                records=all_records,
                metadata=SourceMetadata(
                    source_type=self.source_type,
                    source_name=self.source_name,
                    fetched_at=datetime.utcnow(),
                    record_count=len(all_records),
                ),
            )
            
        except TransientError as e:
            return SourceResult.error(self.source_type, self.source_name, str(e))
        except Exception as e:
            return SourceResult.error(
                self.source_type,
                self.source_name,
                f"HTTP error: {e}",
            )
    
    def _build_headers(self) -> dict[str, str]:
        """Build request headers with auth."""
        headers = dict(self.headers)
        
        if self.auth:
            auth_type = self.auth.get("type", "api_key")
            if auth_type == "api_key":
                header = self.auth.get("header", "X-API-Key")
                headers[header] = self.auth["value"]
            elif auth_type == "bearer":
                headers["Authorization"] = f"Bearer {self.auth['value']}"
            elif auth_type == "basic":
                import base64
                creds = f"{self.auth['user']}:{self.auth['password']}"
                encoded = base64.b64encode(creds.encode()).decode()
                headers["Authorization"] = f"Basic {encoded}"
        
        return headers
    
    def _extract_records(self, data: Any) -> list[dict]:
        """Extract records from response using data_path."""
        if self.data_path is None:
            if isinstance(data, list):
                return data
            return [data]
        
        # Navigate to nested path
        result = data
        for key in self.data_path.split("."):
            if isinstance(result, dict):
                result = result.get(key, [])
            else:
                return []
        
        if isinstance(result, list):
            return result
        return [result]
    
    def _get_next_page(
        self,
        data: Any,
        current_params: dict,
        response: Any,
    ) -> dict | None:
        """Get parameters for next page, or None if done."""
        if not self.pagination:
            return None
        
        pag_type = self.pagination.get("type", "offset")
        
        if pag_type == "offset":
            offset_param = self.pagination.get("offset_param", "offset")
            limit_param = self.pagination.get("limit_param", "limit")
            per_page = self.pagination.get("per_page", 100)
            
            current_offset = current_params.get(offset_param, 0)
            records = self._extract_records(data)
            
            if len(records) < per_page:
                return None  # Last page
            
            next_params = dict(current_params)
            next_params[offset_param] = current_offset + per_page
            next_params[limit_param] = per_page
            return next_params
        
        elif pag_type == "cursor":
            cursor_param = self.pagination.get("cursor_param", "cursor")
            cursor_path = self.pagination.get("cursor_path", "next_cursor")
            
            # Extract cursor from response
            cursor = data
            for key in cursor_path.split("."):
                if isinstance(cursor, dict):
                    cursor = cursor.get(key)
                else:
                    cursor = None
                    break
            
            if not cursor:
                return None
            
            next_params = dict(current_params)
            next_params[cursor_param] = cursor
            return next_params
        
        return None
    
    def validate(self) -> list[str]:
        """Validate HTTP source configuration."""
        errors = []
        
        if not self.url:
            errors.append("URL is required")
        elif not self.url.startswith(("http://", "https://")):
            errors.append("URL must start with http:// or https://")
        
        if self.auth:
            auth_type = self.auth.get("type", "api_key")
            if auth_type == "api_key" and "value" not in self.auth:
                errors.append("API key auth requires 'value'")
            elif auth_type == "bearer" and "value" not in self.auth:
                errors.append("Bearer auth requires 'value'")
            elif auth_type == "basic" and ("user" not in self.auth or "password" not in self.auth):
                errors.append("Basic auth requires 'user' and 'password'")
        
        return errors
```

### DatabaseSource

```python
# spine/framework/sources/database.py
from dataclasses import dataclass, field
from typing import Any, Iterator
from datetime import datetime

from spine.core.storage import get_adapter
from spine.framework.sources.protocol import Source
from spine.framework.sources.result import SourceResult, SourceMetadata


@dataclass
class DatabaseSource:
    """
    Read records from database tables.
    
    Supports: SQLite, PostgreSQL, DB2
    
    Example:
        source = DatabaseSource(
            query="SELECT * FROM trades WHERE week_ending = :week",
            params={"week": "2026-01-03"},
        )
        result = source.fetch()
    """
    query: str
    params: dict[str, Any] = field(default_factory=dict)
    database: str | None = None  # Connection name or DSN
    batch_size: int = 1000  # For streaming
    
    @property
    def source_type(self) -> str:
        return "database"
    
    @property
    def source_name(self) -> str:
        # Truncate query for logging
        return self.query[:50] + "..." if len(self.query) > 50 else self.query
    
    def fetch(self, params: dict[str, Any] | None = None) -> SourceResult:
        """Execute query and return all records."""
        try:
            adapter = get_adapter(self.database)
            merged_params = {**self.params, **(params or {})}
            
            cursor = adapter.execute(self.query, merged_params)
            
            # Get column names
            columns = [desc[0] for desc in cursor.description]
            
            # Fetch all rows
            records = []
            for row in cursor.fetchall():
                records.append(dict(zip(columns, row)))
            
            return SourceResult(
                records=records,
                metadata=SourceMetadata(
                    source_type=self.source_type,
                    source_name=self.source_name,
                    fetched_at=datetime.utcnow(),
                    record_count=len(records),
                ),
            )
            
        except Exception as e:
            return SourceResult.error(
                self.source_type,
                self.source_name,
                f"Database error: {e}",
            )
    
    def stream(self, params: dict[str, Any] | None = None) -> Iterator[dict[str, Any]]:
        """Stream records from database (server-side cursor)."""
        adapter = get_adapter(self.database)
        merged_params = {**self.params, **(params or {})}
        
        cursor = adapter.execute(self.query, merged_params)
        columns = [desc[0] for desc in cursor.description]
        
        while True:
            rows = cursor.fetchmany(self.batch_size)
            if not rows:
                break
            for row in rows:
                yield dict(zip(columns, row))
    
    def validate(self) -> list[str]:
        """Validate database source configuration."""
        errors = []
        
        if not self.query:
            errors.append("Query is required")
        elif not self.query.strip().upper().startswith("SELECT"):
            errors.append("Only SELECT queries are allowed")
        
        return errors
```

---

## Source Registry

```python
# spine/framework/sources/__init__.py
from typing import Type
from spine.framework.sources.protocol import Source
from spine.framework.sources.result import SourceResult, SourceMetadata
from spine.framework.sources.file import FileSource
from spine.framework.sources.http import HttpSource
from spine.framework.sources.database import DatabaseSource

# Source registry
_SOURCE_REGISTRY: dict[str, Type[Source]] = {}


def register_source(name: str):
    """Decorator to register a source class."""
    def decorator(cls: Type[Source]) -> Type[Source]:
        _SOURCE_REGISTRY[name] = cls
        return cls
    return decorator


def get_source(name: str) -> Type[Source]:
    """Get source class by name."""
    if name not in _SOURCE_REGISTRY:
        raise ValueError(f"Unknown source: {name}")
    return _SOURCE_REGISTRY[name]


def list_sources() -> list[str]:
    """List registered source names."""
    return list(_SOURCE_REGISTRY.keys())


# Register built-in sources
register_source("file")(FileSource)
register_source("http")(HttpSource)
register_source("database")(DatabaseSource)


__all__ = [
    # Protocol
    "Source",
    "SourceResult",
    "SourceMetadata",
    # Implementations
    "FileSource",
    "HttpSource",
    "DatabaseSource",
    # Registry
    "register_source",
    "get_source",
    "list_sources",
]
```

---

## Usage Examples

### FINRA File Source

```python
from spine.framework.sources import FileSource

# Create source
source = FileSource(
    path="data/finra/week_2026-01-03.psv",
    format="psv",
)

# Fetch all records
result = source.fetch()

if result.success:
    print(f"Fetched {result.record_count} records")
    for record in result.records:
        print(record)
else:
    for error in result.errors:
        print(f"Error: {error}")
```

### Alpha Vantage API Source

```python
from spine.framework.sources import HttpSource
import os

source = HttpSource(
    url="https://www.alphavantage.co/query",
    auth={
        "type": "api_key",
        "header": "X-API-Key",
        "value": os.environ["ALPHA_VANTAGE_KEY"],
    },
    data_path="Time Series (Daily)",
)

result = source.fetch({
    "function": "TIME_SERIES_DAILY",
    "symbol": "AAPL",
})
```

### Database Cross-Reference

```python
from spine.framework.sources import DatabaseSource

source = DatabaseSource(
    query="""
        SELECT t.symbol, t.volume, c.sector
        FROM trades t
        JOIN companies c ON t.symbol = c.symbol
        WHERE t.week_ending = :week
    """,
    params={"week": "2026-01-03"},
)

result = source.fetch()
```

---

## Integration with Pipelines

```python
# spine/domains/finra/otc_transparency/pipelines.py
from spine.framework.pipelines import Pipeline, PipelineResult
from spine.framework.sources import FileSource, SourceResult
from spine.framework.registry import register_pipeline


@register_pipeline("finra.otc_transparency.ingest_week")
class IngestWeekPipeline(Pipeline):
    """Ingest FINRA OTC data using unified source protocol."""
    
    def run(self) -> PipelineResult:
        # Create source from params
        source = FileSource(
            path=self.params["file_path"],
            format="psv",
        )
        
        # Validate source
        errors = source.validate()
        if errors:
            return PipelineResult.failed(errors[0])
        
        # Fetch data
        result: SourceResult = source.fetch()
        
        if not result.success:
            return PipelineResult.failed(result.errors[0])
        
        # Process records
        for record in result.records:
            self._process_record(record)
        
        return PipelineResult.completed(
            metrics={
                "record_count": result.record_count,
                "source": result.metadata.source_name,
            }
        )
```

---

## Testing

```python
# tests/framework/sources/test_file_source.py
import pytest
from pathlib import Path
from spine.framework.sources import FileSource

class TestFileSource:
    def test_read_csv(self, tmp_path):
        # Create test file
        csv_file = tmp_path / "test.csv"
        csv_file.write_text("name,value\nalice,100\nbob,200")
        
        source = FileSource(path=csv_file)
        result = source.fetch()
        
        assert result.success
        assert result.record_count == 2
        assert result.records[0]["name"] == "alice"
    
    def test_read_psv(self, tmp_path):
        psv_file = tmp_path / "test.psv"
        psv_file.write_text("symbol|volume\nAAPL|1000\nMSFT|2000")
        
        source = FileSource(path=psv_file, format="psv")
        result = source.fetch()
        
        assert result.success
        assert result.record_count == 2
        assert result.records[0]["symbol"] == "AAPL"
    
    def test_file_not_found(self):
        source = FileSource(path="/nonexistent/file.csv")
        result = source.fetch()
        
        assert not result.success
        assert "not found" in result.errors[0].lower()
    
    def test_streaming(self, tmp_path):
        csv_file = tmp_path / "large.csv"
        csv_file.write_text("id\n" + "\n".join(str(i) for i in range(1000)))
        
        source = FileSource(path=csv_file)
        count = sum(1 for _ in source.stream())
        
        assert count == 1000
```

---

## Next Steps

1. Implement database adapters: [04-DATABASE-ADAPTERS.md](./04-DATABASE-ADAPTERS.md)
2. Add error types: [03-ERROR-FRAMEWORK.md](./03-ERROR-FRAMEWORK.md)
3. Migrate FINRA sources: [10-FINRA-EXAMPLE.md](./10-FINRA-EXAMPLE.md)
