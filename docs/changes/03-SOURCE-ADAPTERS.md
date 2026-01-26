# Source Adapters

This document covers the unified Source protocol for data ingestion.

---

## Overview

The **Source Protocol** provides a common interface for fetching data from:
- Local files (CSV, PSV, JSON, Parquet)
- HTTP APIs (coming in Advanced tier)
- Databases (coming in Advanced tier)
- Cloud storage (S3, SFTP - coming in Full tier)

Key benefits:
- **Consistent API**: Same `fetch()` method for all source types
- **Change detection**: Content hashing to skip unchanged data
- **Streaming**: Handle large files without memory issues
- **Metadata tracking**: Size, duration, row count for every fetch

---

## Core Concepts

### Source Protocol

```python
from typing import Protocol

class Source(Protocol):
    @property
    def name(self) -> str:
        """Unique source identifier."""
        ...
    
    @property
    def source_type(self) -> SourceType:
        """Type classification (file, http, database, etc.)."""
        ...
    
    def fetch(self, params: dict | None = None) -> SourceResult:
        """Fetch all data from the source."""
        ...
```

### SourceResult

Every fetch returns a `SourceResult` containing:
- `data`: List of dictionaries (rows)
- `metadata`: Fetch details (timing, size, hash)
- `success`: Boolean status
- `error`: Error if failed

```python
@dataclass
class SourceResult:
    data: list[dict] | None = None
    metadata: SourceMetadata | None = None
    success: bool = True
    error: SpineError | None = None
```

### SourceMetadata

```python
@dataclass
class SourceMetadata:
    source_name: str
    source_type: SourceType
    fetched_at: datetime
    duration_ms: int | None = None
    
    # Change detection
    content_hash: str | None = None
    etag: str | None = None
    last_modified: str | None = None
    content_changed: bool = True
    
    # Size
    bytes_fetched: int | None = None
    row_count: int | None = None
```

---

## FileSource

The `FileSource` adapter handles local file ingestion.

### Basic Usage

```python
from spine.framework.sources.file import FileSource

# Auto-detect format from extension
source = FileSource(
    name="trades",
    path="/data/trades.csv",
)

result = source.fetch()
if result.success:
    for row in result.data:
        print(row)
```

### Supported Formats

| Extension | Format | Delimiter |
|-----------|--------|-----------|
| `.csv` | CSV | `,` |
| `.psv` | PSV | `\|` |
| `.tsv` | TSV | `\t` |
| `.json` | JSON | N/A |
| `.jsonl`, `.ndjson` | JSON Lines | N/A |
| `.parquet`, `.pq` | Parquet | N/A |

### Format Options

```python
# Explicit format (override auto-detection)
source = FileSource(
    name="finra_data",
    path="/data/finra_otc.txt",
    format="psv",  # Force pipe-separated parsing
)

# Custom delimiter
source = FileSource(
    name="semicolon_file",
    path="/data/european.csv",
    delimiter=";",  # Override default
)

# Custom column names
source = FileSource(
    name="headerless",
    path="/data/legacy.csv",
    column_names=["id", "name", "value"],
)

# Encoding
source = FileSource(
    name="latin1_file",
    path="/data/old_system.csv",
    encoding="latin-1",
)
```

### Change Detection

FileSource tracks content hashes to detect changes:

```python
# First fetch
result1 = source.fetch()
print(result1.metadata.content_hash)  # "abc123..."
print(result1.metadata.content_changed)  # True

# Check if changed before re-fetching
if source.has_changed(last_hash=result1.metadata.content_hash):
    result2 = source.fetch()  # Only fetch if changed
else:
    print("File unchanged, skipping")
```

### Streaming Large Files

For files that don't fit in memory:

```python
# Stream in batches of 1000 rows
for batch in source.stream(batch_size=1000):
    process_batch(batch)
    # Each batch is a list of up to 1000 dicts
```

Streaming is supported for: CSV, PSV, TSV, JSON Lines

---

## Source Registry

The global registry enables source discovery:

```python
from spine.framework.sources import source_registry

# Register a source
source = FileSource(name="finra.weekly", path="/data/finra/*.psv")
source_registry.register(source)

# Get by name
source = source_registry.get("finra.weekly")

# List all sources
names = source_registry.list_sources()

# List by type
file_sources = source_registry.list_by_type(SourceType.FILE)
```

### Lazy Factory Registration

Register sources that are created on-demand:

```python
source_registry.register_factory(
    name="finra.weekly",
    source_class=FileSource,
    config={
        "path": "/data/finra/weekly.psv",
        "format": "psv",
    },
)

# Source is created when first accessed
source = source_registry.get("finra.weekly")
```

---

## Using in Pipelines

Sources integrate with the existing pipeline framework:

```python
from spine.core import pipeline, capture
from spine.framework.sources import source_registry

@pipeline("finra.otc.ingest")
def ingest_pipeline(params: dict):
    # Get registered source
    source = source_registry.get("finra.otc.weekly")
    
    # Fetch data
    result = source.fetch()
    if not result.success:
        raise result.error
    
    # Process and capture
    processed = transform(result.data)
    
    return capture(
        data=processed,
        name="finra_otc_weekly",
        metadata={
            "source_hash": result.metadata.content_hash,
            "row_count": result.metadata.row_count,
        },
    )
```

---

## SQL Schema

Source operations are tracked in the database:

### `core_sources` - Source Registry

```sql
CREATE TABLE core_sources (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    source_type TEXT NOT NULL,
    config_json TEXT NOT NULL,
    domain TEXT,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

### `core_source_fetches` - Fetch History

```sql
CREATE TABLE core_source_fetches (
    id TEXT PRIMARY KEY,
    source_id TEXT,
    source_name TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_locator TEXT NOT NULL,
    status TEXT NOT NULL,
    record_count INTEGER,
    byte_count INTEGER,
    content_hash TEXT,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    duration_ms INTEGER,
    error TEXT,
    capture_id TEXT
);
```

### `core_source_cache` - Content Cache

```sql
CREATE TABLE core_source_cache (
    cache_key TEXT PRIMARY KEY,
    source_id TEXT,
    content_hash TEXT NOT NULL,
    content_size INTEGER NOT NULL,
    fetched_at TEXT NOT NULL,
    expires_at TEXT,
    etag TEXT,
    last_modified TEXT
);
```

---

## Extending: Custom Sources

To create a custom source:

```python
from spine.framework.sources.protocol import BaseSource, SourceResult, SourceType

class S3Source(BaseSource):
    def __init__(
        self,
        name: str,
        bucket: str,
        key: str,
        **kwargs,
    ):
        super().__init__(name=name, source_type=SourceType.S3, **kwargs)
        self._bucket = bucket
        self._key = key
    
    def fetch(self, params: dict | None = None) -> SourceResult:
        import boto3
        
        start = datetime.now()
        try:
            s3 = boto3.client("s3")
            response = s3.get_object(Bucket=self._bucket, Key=self._key)
            data = json.loads(response["Body"].read())
            
            metadata = self._create_metadata(
                params=params,
                bytes_fetched=response["ContentLength"],
                etag=response.get("ETag"),
            )
            
            return SourceResult.ok(data, metadata)
            
        except Exception as e:
            error = self._wrap_error(e, f"Failed to fetch s3://{self._bucket}/{self._key}")
            return SourceResult.fail(error)
```

---

## Future Sources (Roadmap)

| Source | Tier | Status |
|--------|------|--------|
| `FileSource` | Basic | ✅ Complete |
| `HttpSource` | Advanced | 🚧 Planned |
| `DatabaseSource` | Advanced | 🚧 Planned |
| `S3Source` | Full | 🚧 Planned |
| `SFTPSource` | Full | 🚧 Planned |

---

## Best Practices

### 1. Use the Registry

```python
# ❌ Creating sources everywhere
source = FileSource(name="trades", path="/data/trades.csv")
result = source.fetch()

# ✅ Register once, use via registry
# At startup:
source_registry.register(FileSource(name="trades", path="/data/trades.csv"))

# In pipelines:
source = source_registry.get("trades")
```

### 2. Check for Changes

```python
# ❌ Always re-fetch
result = source.fetch()

# ✅ Skip if unchanged
if source.has_changed(last_hash=previous_hash):
    result = source.fetch()
else:
    log.info("Source unchanged, using cached data")
```

### 3. Stream Large Files

```python
# ❌ Loading entire file
result = source.fetch()  # 10 million rows = OOM

# ✅ Stream in batches
for batch in source.stream(batch_size=10000):
    process_batch(batch)
```

### 4. Handle Errors

```python
result = source.fetch()
if not result.success:
    if is_retryable(result.error):
        schedule_retry()
    else:
        send_alert(result.error)
        raise result.error
```
