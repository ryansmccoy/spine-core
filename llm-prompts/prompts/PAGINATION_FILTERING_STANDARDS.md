# Pagination & Filtering Standards

> Canonical patterns for pagination and filtering in spine-core APIs. Reference this when implementing list endpoints.

## Pagination

### Offset-Based (Default)

Use for most list endpoints:

```
GET /v1/data/prices/AAPL?offset=0&limit=100
```

**Request Parameters:**

| Parameter | Type | Default | Max | Description |
|-----------|------|---------|-----|-------------|
| `offset` | int | 0 | — | Starting position (0-based) |
| `limit` | int | 100 | 1000 | Page size |

**Response Structure:**

```json
{
  "data": [...],
  "pagination": {
    "offset": 0,
    "limit": 100,
    "total": 1234,
    "has_more": true
  }
}
```

### Implementation

```python
@dataclass
class QueryCommand:
    offset: int = 0
    limit: int = 100
    
    MAX_LIMIT: ClassVar[int] = 1000
    
    def __post_init__(self):
        if self.offset < 0:
            raise ValueError("offset must be >= 0")
        self.limit = min(self.limit, self.MAX_LIMIT)


def paginate(query: str, offset: int, limit: int) -> str:
    return f"{query} LIMIT {limit} OFFSET {offset}"


def count_total(conn, table: str, where: str = "") -> int:
    query = f"SELECT COUNT(*) FROM {table}"
    if where:
        query += f" WHERE {where}"
    return conn.execute(query).fetchone()[0]
```

### Cursor-Based (Optional)

For very large datasets or real-time feeds:

```
GET /v1/data/prices/AAPL?cursor=eyJkYXRlIjoiMjAyNC0wMS0xNSJ9
```

**When to use:**
- Dataset changes frequently (insertions)
- Offset would skip/duplicate items
- Need stable iteration

**Response:**

```json
{
  "data": [...],
  "pagination": {
    "next_cursor": "eyJkYXRlIjoiMjAyNC0wMS0xMCJ9",
    "has_more": true
  }
}
```

---

## Filtering

### Date Range Filtering

```
GET /v1/data/prices/AAPL?start_date=2024-01-01&end_date=2024-01-31
```

**Parameters:**

| Parameter | Format | Description |
|-----------|--------|-------------|
| `start_date` | YYYY-MM-DD | Include dates >= this |
| `end_date` | YYYY-MM-DD | Include dates <= this |

**Implementation:**

```python
@dataclass
class DateRangeFilter:
    start_date: str | None = None
    end_date: str | None = None
    
    MAX_DAYS: ClassVar[int] = 365
    
    def __post_init__(self):
        if self.start_date and self.end_date:
            start = datetime.fromisoformat(self.start_date)
            end = datetime.fromisoformat(self.end_date)
            if (end - start).days > self.MAX_DAYS:
                raise ValueError(f"Date range exceeds {self.MAX_DAYS} days")
    
    def to_sql(self) -> tuple[str, list]:
        conditions = []
        params = []
        
        if self.start_date:
            conditions.append("date >= ?")
            params.append(self.start_date)
        if self.end_date:
            conditions.append("date <= ?")
            params.append(self.end_date)
        
        return " AND ".join(conditions), params
```

### Capture ID Filtering (As-Of)

```
GET /v1/data/prices/AAPL?capture_id=market_data.prices.AAPL.20240115T120000Z.abc12345
```

**Purpose:** Return data exactly as captured at a specific point in time.

**Implementation:**

```python
def filter_by_capture(query: str, capture_id: str | None) -> tuple[str, list]:
    if not capture_id:
        # Return latest capture
        return query + " AND capture_id = (SELECT MAX(capture_id) FROM ...)", []
    
    return query + " AND capture_id = ?", [capture_id]
```

---

## Sorting

### Default Sort Order

Always define a deterministic default sort:

```
GET /v1/data/prices/AAPL
# Default: ORDER BY date DESC, id ASC
```

### Explicit Sorting

```
GET /v1/data/prices/AAPL?sort=date&order=asc
```

**Parameters:**

| Parameter | Values | Description |
|-----------|--------|-------------|
| `sort` | Field name | Column to sort by |
| `order` | `asc`, `desc` | Sort direction |

**Allowed sort fields (whitelist):**

```python
ALLOWED_SORT_FIELDS = {"date", "close", "volume", "captured_at"}

def validate_sort(field: str) -> str:
    if field not in ALLOWED_SORT_FIELDS:
        raise ValueError(f"Invalid sort field: {field}")
    return field
```

---

## Field Selection (Optional)

For bandwidth optimization:

```
GET /v1/data/prices/AAPL?fields=date,close,volume
```

**Implementation:**

```python
DEFAULT_FIELDS = ["symbol", "date", "open", "high", "low", "close", "volume"]
ALLOWED_FIELDS = DEFAULT_FIELDS + ["change", "change_percent", "capture_id"]

def select_fields(requested: str | None) -> list[str]:
    if not requested:
        return DEFAULT_FIELDS
    
    fields = [f.strip() for f in requested.split(",")]
    invalid = set(fields) - set(ALLOWED_FIELDS)
    if invalid:
        raise ValueError(f"Invalid fields: {invalid}")
    
    return fields
```

---

## Guardrails

### Limits and Bounds

```python
# Maximum page size
MAX_LIMIT = 1000

# Maximum date range
MAX_DAYS = 365

# Maximum symbols per batch query
MAX_SYMBOLS = 100
```

### SQL Injection Prevention

**NEVER:**
```python
query = f"SELECT * FROM prices WHERE symbol = '{symbol}'"  # DANGEROUS
```

**ALWAYS:**
```python
query = "SELECT * FROM prices WHERE symbol = ?"
cursor.execute(query, (symbol,))
```

### Empty Result Handling

Return empty array, not null:

```json
{
  "data": [],
  "pagination": {
    "offset": 0,
    "limit": 100,
    "total": 0,
    "has_more": false
  }
}
```

---

## Performance Guidelines

### Index Requirements

For pagination to be efficient:

```sql
-- Support ORDER BY date DESC with pagination
CREATE INDEX idx_prices_date ON prices(symbol, date DESC);

-- Support as-of queries
CREATE INDEX idx_prices_capture ON prices(capture_id, symbol, date DESC);
```

### Count Optimization

For large tables, consider approximate counts:

```python
def get_total(conn, table: str, exact: bool = True) -> int:
    if exact:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    else:
        # SQLite: use ANALYZE statistics
        return conn.execute(
            "SELECT stat FROM sqlite_stat1 WHERE tbl = ?", (table,)
        ).fetchone()[0]
```

---

## Guardrails for LLMs

When implementing pagination/filtering:

1. ✅ Always include pagination for list endpoints
2. ✅ Validate and cap `limit` parameter
3. ✅ Use parameterized queries (never string interpolation)
4. ✅ Return empty array for no results (not null)
5. ✅ Include `has_more` flag for client-side pagination
6. ✅ Add indexes for sort/filter columns
7. ❌ Don't allow unbounded queries
8. ❌ Don't expose internal row IDs
9. ❌ Don't allow arbitrary sort fields (use whitelist)
10. ❌ Don't return total count if too expensive to compute

---

## Checklist

Before submitting list endpoint:

- [ ] Pagination parameters defined (offset, limit)
- [ ] Maximum limit enforced (1000)
- [ ] Response includes pagination metadata
- [ ] Empty results return empty array
- [ ] Date filtering uses ISO format
- [ ] Sort fields are whitelisted
- [ ] Queries use parameterized statements
- [ ] Appropriate indexes exist
- [ ] has_more correctly computed
