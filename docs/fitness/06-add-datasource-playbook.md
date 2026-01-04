# 06 — Add Datasource Playbook

> **Registry-based extensibility for Sources and Periods**

---

## Status

✅ **Implemented with Registry Pattern** — Sources and Periods use symmetric registries.

### Implementation Files

| File | Purpose |
|------|---------|
| [sources.py](../../packages/spine-domains/src/spine/domains/finra/otc_transparency/sources.py) | `SOURCE_REGISTRY`, `PERIOD_REGISTRY`, `FileSource`, `APISource`, `WeeklyPeriod`, `MonthlyPeriod` |
| [test_sources.py](../../market-spine-basic/tests/test_sources.py) | 32 tests for sources and extensibility |
| [source-period-symmetry.md](../../docs/design/source-period-symmetry.md) | Design note explaining the pattern |

### Test Coverage (verified: 32 tests)

Test classes:
- `TestSourceFactory` — Factory validation (5 tests)
- `TestFileSource` — File source behavior (5 tests)
- `TestAPISource` — API source with mock (3 tests)
- `TestIdempotentRerun` — Skip already-ingested (2 tests)
- `TestCaptureReplay` — Distinct capture_ids (2 tests)
- `TestOfflineAPIIngest` — API with mock content (2 tests)
- `TestSourceRegistryExtensibility` — Source registry guarantees (4 tests)
- `TestPeriodRegistryExtensibility` — Period registry guarantees (5 tests)
- `TestBackwardCompatibility` — Backward compat (4 tests)

---

## Key Principle: No Pipeline Branching

Pipelines **must not** branch on extensibility axes:

```python
# ❌ BAD - requires edit when adding S3 source
if source_type == "file":
    return FileSource(...)
elif source_type == "api":
    return APISource(...)
elif source_type == "s3":  # NEW: must edit factory!
    return S3Source(...)

# ✅ GOOD - uses registry lookup
source = resolve_source(source_type, **params)  # No if/else
```

---

## 1. Source Registry Pattern

### Registration via Decorator

```python
from spine.domains.finra.otc_transparency.sources import (
    IngestionSource,
    register_source,
)

@register_source("s3")
class S3Source(IngestionSource):
    """AWS S3 ingestion source."""
    
    def __init__(self, bucket: str, key: str, **kwargs):
        self.bucket = bucket
        self.key = key
    
    @property
    def source_type(self) -> str:
        return "s3"
    
    def fetch(self) -> Payload:
        # S3 fetch logic
        ...
```

### Resolution via Registry

```python
from spine.domains.finra.otc_transparency.sources import resolve_source

# Pipeline code - never changes when new sources added
source = resolve_source(
    source_type=params.get("source_type", "file"),
    file_path=params.get("file_path"),
    bucket=params.get("bucket"),
    # ... other params passed through
)
payload = source.fetch()
```

---

## 2. Period Registry Pattern

### Built-in Periods

| Period | Description | Example |
|--------|-------------|---------|
| `weekly` | FINRA weekly data (default) | Mon publish → Fri week_ending |
| `monthly` | FINRA monthly data | 1st of month → last day prev month |

### Adding a New Period

```python
from spine.domains.finra.otc_transparency.sources import (
    PeriodStrategy,
    register_period,
)

@register_period("quarterly")
class QuarterlyPeriod(PeriodStrategy):
    """Quarterly reporting period."""
    
    @property
    def period_type(self) -> str:
        return "quarterly"
    
    def derive_period_end(self, publish_date: date) -> date:
        # Derive quarter end from publish date
        month = ((publish_date.month - 1) // 3) * 3 + 3
        return date(publish_date.year, month, 30)
    
    def validate_date(self, period_end: date) -> bool:
        return period_end.month in (3, 6, 9, 12)
    
    def format_for_filename(self, period_end: date) -> str:
        return f"Q{(period_end.month - 1) // 3 + 1}-{period_end.year}"
    
    def format_for_display(self, period_end: date) -> str:
        return f"Q{(period_end.month - 1) // 3 + 1} {period_end.year}"
```

### Resolution via Registry

```python
from spine.domains.finra.otc_transparency.sources import resolve_period

period = resolve_period(params.get("period_type", "weekly"))
period_end = period.derive_period_end(publish_date)
```

---

## 3. Adding a New Source: Checklist

- [ ] Create source class inheriting from `IngestionSource`
- [ ] Add `@register_source("name")` decorator
- [ ] Implement `source_type` property
- [ ] Implement `fetch()` returning `Payload`
- [ ] Accept `**kwargs` in `__init__` for registry compatibility
- [ ] Add unit tests
- [ ] **NO CHANGES to `resolve_source()` or pipeline code**

### Example: S3 Source

```python
@register_source("s3")
class S3Source(IngestionSource):
    def __init__(
        self,
        bucket: str | None = None,
        key: str | None = None,
        period_type: str = "weekly",
        **kwargs,
    ):
        if not bucket:
            raise ValueError("bucket is required for S3Source")
        if not key:
            raise ValueError("key is required for S3Source")
        self.bucket = bucket
        self.key = key
        self.period_strategy = resolve_period(period_type)
    
    @property
    def source_type(self) -> str:
        return "s3"
    
    def fetch(self) -> Payload:
        # Fetch from S3 (using boto3 or similar)
        content = self._fetch_s3_object()
        
        return Payload(
            content=content,
            metadata=IngestionMetadata(
                week_ending=self._determine_period_end(),
                file_date=date.today(),
                source_type="s3",
                source_name=f"s3://{self.bucket}/{self.key}",
                period_type=self.period_strategy.period_type,
            ),
        )
```

---

## 4. Adding a New Period: Checklist

- [ ] Create period class inheriting from `PeriodStrategy`
- [ ] Add `@register_period("name")` decorator
- [ ] Implement `period_type` property
- [ ] Implement `derive_period_end(publish_date) -> date`
- [ ] Implement `validate_date(period_end) -> bool`
- [ ] Implement `format_for_filename(period_end) -> str`
- [ ] Implement `format_for_display(period_end) -> str`
- [ ] Add unit tests
- [ ] **NO CHANGES to `resolve_period()` or pipeline code**

---

## 5. Extensibility Guarantees

These guarantees are **enforced by tests** in `test_sources.py`:

| Guarantee | Test |
|-----------|------|
| Adding source requires no factory edit | `test_adding_source_requires_no_factory_edit` |
| Adding period requires no factory edit | `test_adding_period_requires_no_factory_edit` |
| Unknown source raises helpful error | `test_resolve_source_unknown_raises_helpful_error` |
| Weekly is default period | `test_resolve_period_defaults_to_weekly` |
| Backward compat: create_source works | `test_create_source_still_works` |
| Backward compat: derive_week_ending works | `test_derive_week_ending_from_publish_date_still_works` |
    """HTTP API source."""
    
    def __init__(self, base_url: str, session: requests.Session | None = None):
        self.base_url = base_url
        self.session = session or requests.Session()
    
    def fetch(self, endpoint: str, **params) -> Payload:
        url = f"{self.base_url}/{endpoint}"
        response = self.session.get(url, params=params)
        response.raise_for_status()
        
        return Payload(
            content=response.content,
            metadata=SourceMetadata(
                source_type="api",
                source_uri=response.url,
                fetched_at=datetime.now(UTC),
                etag=response.headers.get("ETag"),
                last_modified=parse_http_date(response.headers.get("Last-Modified")),
                content_hash=hashlib.sha256(response.content).hexdigest(),
            ),
        )
```

---

## 2. Playbook: Adding a New Source

### Step 1: Define Source Class

```python
# sources.py

class S3Source:
    """AWS S3 source."""
    
    def __init__(self, bucket: str, client: boto3.client | None = None):
        self.bucket = bucket
        self.client = client or boto3.client("s3")
    
    def fetch(self, key: str) -> Payload:
        response = self.client.get_object(Bucket=self.bucket, Key=key)
        content = response["Body"].read()
        
        return Payload(
            content=content,
            metadata=SourceMetadata(
                source_type="s3",
                source_uri=f"s3://{self.bucket}/{key}",
                fetched_at=datetime.now(UTC),
                etag=response.get("ETag"),
                last_modified=response.get("LastModified"),
                content_hash=hashlib.sha256(content).hexdigest(),
            ),
        )
```

### Step 2: Update Pipeline to Use Source

```python
class IngestWeekPipeline(Pipeline):
    def run(self):
        source = self._get_source()
        payload = source.fetch(self._build_filename())
        
        # Parse content
        rows = self._parse_csv(payload.content)
        
        # Include source metadata in capture
        capture_id = payload.metadata.content_hash[:12]
        captured_at = payload.metadata.fetched_at.isoformat()
        
        # Write rows...
    
    def _get_source(self) -> Source:
        source_type = self.params.get("source", "file")
        
        if source_type == "file":
            return FileSource(Path(self.params["data_dir"]))
        elif source_type == "api":
            return APISource(self.params["api_url"])
        elif source_type == "s3":
            return S3Source(self.params["s3_bucket"])
        else:
            raise ValueError(f"Unknown source: {source_type}")
```

### Step 3: Add Tests

```python
# test_sources.py

class TestS3Source:
    def test_fetch_object(self, mock_s3):
        source = S3Source("my-bucket", client=mock_s3)
        payload = source.fetch("data/2025/week-52.csv")
        
        assert payload.content == b"expected,content"
        assert payload.metadata.source_type == "s3"
        assert payload.metadata.source_uri == "s3://my-bucket/data/2025/week-52.csv"
    
    def test_content_hash_computed(self, mock_s3):
        source = S3Source("my-bucket", client=mock_s3)
        payload = source.fetch("data/2025/week-52.csv")
        
        expected_hash = hashlib.sha256(b"expected,content").hexdigest()
        assert payload.metadata.content_hash == expected_hash
    
    def test_missing_object_raises(self, mock_s3):
        mock_s3.configure_404("missing.csv")
        source = S3Source("my-bucket", client=mock_s3)
        
        with pytest.raises(ClientError):
            source.fetch("missing.csv")
```

### Step 4: Add CLI/Config Support

```python
# CLI usage
spine ingest finra.otc_transparency -p source=s3 -p s3_bucket=my-data-bucket

# Config file
sources:
  finra_otc_transparency:
    type: s3
    bucket: my-data-bucket
    prefix: finra/otc/
```

---

## 3. Source Selection Matrix

| Source | Use Case | Pros | Cons |
|--------|----------|------|------|
| `file` | Local dev, testing | Fast, simple | Manual data management |
| `api` | Production ingestion | Always current | Network dependency |
| `s3` | Archived data, backfill | Scalable, versioned | AWS setup required |
| `sftp` | Partner data feeds | Common in finance | Auth complexity |

---

## 4. Offline/Mock Patterns

### Mock Source for Tests

```python
class MockSource:
    """In-memory source for testing."""
    
    def __init__(self, data: dict[str, bytes]):
        self.data = data
        self.fetch_count = 0
    
    def fetch(self, key: str) -> Payload:
        self.fetch_count += 1
        if key not in self.data:
            raise FileNotFoundError(key)
        
        content = self.data[key]
        return Payload(
            content=content,
            metadata=SourceMetadata(
                source_type="mock",
                source_uri=f"mock://{key}",
                fetched_at=datetime.now(UTC),
                content_hash=hashlib.sha256(content).hexdigest(),
            ),
        )
```

### Recording Source for Offline Replay

```python
class RecordingSource:
    """Wraps a source and records fetches for offline replay."""
    
    def __init__(self, source: Source, cache_dir: Path):
        self.source = source
        self.cache_dir = cache_dir
    
    def fetch(self, **params) -> Payload:
        cache_key = self._cache_key(params)
        cache_path = self.cache_dir / cache_key
        
        if cache_path.exists():
            return self._load_cached(cache_path)
        
        payload = self.source.fetch(**params)
        self._save_cached(cache_path, payload)
        return payload
```

---

## 5. Checklist: New Source Implementation

- [ ] Implement `Source` protocol (`fetch` method)
- [ ] Return `Payload` with complete `SourceMetadata`
- [ ] Compute `content_hash` for idempotency
- [ ] Handle errors gracefully (network, auth, not found)
- [ ] Add unit tests with mocked dependencies
- [ ] Add integration tests with real source (if available)
- [ ] Update pipeline to support new source type
- [ ] Document source configuration
- [ ] Add to smoke tests

---

## 6. Future Source Ideas

| Source | Notes |
|--------|-------|
| `sftp` | For partner data feeds |
| `gcs` | Google Cloud Storage |
| `azure_blob` | Azure Blob Storage |
| `kafka` | Streaming ingestion |
| `webhook` | Push-based ingestion |
| `database` | Cross-database sync |

Each follows the same pattern: implement `Source.fetch()`, return `Payload`.
