# Data Dictionary

This document defines all fields in the FINRA OTC Transparency domain.

## Source Fields (from FINRA)

These fields come directly from FINRA's published PSV files.

| Field | Type | Description |
|-------|------|-------------|
| `tierDescription` | string | Security tier: "NMS Tier 1", "NMS Tier 2", or "OTC" |
| `issueSymbolIdentifier` | string | Stock ticker symbol (e.g., "AAPL", "TSLA") |
| `issueName` | string | Company name (e.g., "Apple Inc.") |
| `marketParticipantName` | string | Venue/broker-dealer name |
| `MPID` | string | Market Participant Identifier (4-char code) |
| `totalWeeklyShareQuantity` | integer | Total shares traded this week at this venue |
| `totalWeeklyTradeCount` | integer | Total trades executed this week at this venue |
| `lastUpdateDate` | date | When FINRA last updated this row |

## Normalized Fields (our schema)

### Common Fields (all tables)

| Field | Type | Description |
|-------|------|-------------|
| `week_ending` | date | Friday of the trading week (Clock 1) |
| `tier` | enum | `NMS_TIER_1`, `NMS_TIER_2`, or `OTC` |
| `symbol` | string | Uppercase ticker symbol |
| `captured_at` | timestamp | When we ingested this data (Clock 3) |
| `capture_id` | string | Unique identifier for this capture batch |
| `execution_id` | string | Pipeline execution UUID |
| `batch_id` | string | Processing batch identifier |

### otc_raw (Bronze Layer)

Raw records as parsed from source files.

| Field | Type | Description |
|-------|------|-------------|
| `mpid` | string | Market participant ID |
| `total_shares` | integer | Weekly share volume |
| `total_trades` | integer | Weekly trade count |
| `issue_name` | string | Company name (may be empty) |
| `venue_name` | string | Venue/broker name (may be empty) |
| `source_file` | string | Path to source PSV file |
| `source_last_update_date` | date | FINRA's lastUpdateDate (Clock 2) |
| `record_hash` | string | SHA256 hash for deduplication |
| `ingested_at` | timestamp | When this row was inserted |

### otc_venue_volume (Silver Layer)

Validated and normalized per-venue volumes.

| Field | Type | Description |
|-------|------|-------------|
| `mpid` | string | Market participant ID |
| `total_shares` | integer | Weekly share volume |
| `total_trades` | integer | Weekly trade count |
| `avg_trade_size` | decimal | `total_shares / total_trades` |
| `record_hash` | string | Hash from source record |
| `normalized_at` | timestamp | When normalization occurred |

### otc_symbol_summary (Gold Layer)

Symbol-level aggregates across all venues.

| Field | Type | Description |
|-------|------|-------------|
| `total_volume` | integer | Sum of shares across all venues |
| `total_trades` | integer | Sum of trades across all venues |
| `venue_count` | integer | Number of distinct MPIDs |
| `avg_trade_size` | decimal | `total_volume / total_trades` |
| `calculated_at` | timestamp | When aggregation occurred |

### otc_rolling (Gold Layer)

Rolling window metrics for trend analysis.

| Field | Type | Description |
|-------|------|-------------|
| `avg_volume` | decimal | Average weekly volume over window |
| `avg_trades` | decimal | Average weekly trades over window |
| `min_volume` | integer | Minimum weekly volume in window |
| `max_volume` | integer | Maximum weekly volume in window |
| `trend_direction` | string | `UP`, `DOWN`, or `FLAT` |
| `trend_pct` | decimal | Percentage change first-to-last week |
| `weeks_in_window` | integer | Number of weeks with data |
| `is_complete` | boolean | True if window is fully populated |

## Tier Enumeration

```python
class Tier(str, Enum):
    NMS_TIER_1 = "NMS_TIER_1"  # S&P 500, Russell 1000
    NMS_TIER_2 = "NMS_TIER_2"  # Other NMS stocks
    OTC = "OTC"                 # OTC equity securities
```

## MPID Examples

Market Participant IDs are 4-character codes assigned by FINRA:

| MPID | Venue |
|------|-------|
| `CDRG` | Citadel Securities |
| `VIRX` | Virtu Americas |
| `GSCO` | Goldman Sachs |
| `NITE` | Knight Capital (historical) |
| `ARCA` | NYSE Arca |

## Date Formats

All dates use ISO 8601 format:
- Date: `YYYY-MM-DD` (e.g., `2025-12-19`)
- Timestamp: `YYYY-MM-DDTHH:MM:SS.sssZ` (ISO 8601 with timezone)

## Null Handling

| Field | Null Meaning |
|-------|--------------|
| `source_last_update_date` | Date not available in source file |
| `avg_trade_size` | Zero trades (division by zero) |
| `trend_pct` | Insufficient data for trend calculation |

## Validation Rules

Records are rejected during normalization if:

1. **Invalid tier**: Tier string doesn't map to known tier
2. **Empty symbol**: Symbol is blank or only whitespace
3. **Empty MPID**: MPID is blank or only whitespace
4. **Negative counts**: `total_shares < 0` or `total_trades < 0`
5. **Zero volume**: Both `total_shares = 0` AND `total_trades = 0`

Rejected records are stored in `core_rejects` with rejection reasons.
