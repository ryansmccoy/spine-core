# FINRA OTC Data Source Specification

## File Format

FINRA OTC weekly transparency files are **pipe-delimited** (`|`) with a header row.

```
tierDescription|issueSymbolIdentifier|issueName|marketParticipantName|MPID|totalWeeklyShareQuantity|totalWeeklyTradeCount|lastUpdateDate
NMS Tier 2|AAOI|Applied Optoelectronics, Inc. Common Stock|EBXL LEVEL ATS|EBXL|639234|7396|2025-12-29
NMS Tier 2|AAOI|Applied Optoelectronics, Inc. Common Stock|INCR INTELLIGENT CROSS LLC|INCR|526088|8467|2025-12-29
NMS Tier 2|AAOI|Applied Optoelectronics, Inc. Common Stock|UBSA UBS ATS|UBSA|576612|8303|2025-12-29
```

**File naming:**
- `finra_otc_weekly_tier1.csv` - T1 ATS data
- `finra_otc_weekly_tier2.csv` - T2 ATS data
- `finra_otc_weekly_otc.csv` - Non-ATS OTC volume

---

## Field Definitions

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `tierDescription` | STRING | NMS tier | "NMS Tier 1", "NMS Tier 2" |
| `issueSymbolIdentifier` | STRING | Ticker symbol | "AAPL", "AAOI" |
| `issueName` | STRING | Full security name | "Apple Inc. Common Stock" |
| `marketParticipantName` | STRING | Full ATS venue name | "SGMT SIGMA X2" |
| `MPID` | STRING(4) | Market Participant ID | "SGMT", "INCR", "UBSA" |
| `totalWeeklyShareQuantity` | INTEGER | Total shares traded | 15234567 |
| `totalWeeklyTradeCount` | INTEGER | Number of trades | 45230 |
| `lastUpdateDate` | DATE | Week-ending date | "2025-12-29" |

**Important notes:**
- `lastUpdateDate` is the **week-ending date**, not publication date
- `MPID` is the stable 4-character identifier (use for joins)
- `marketParticipantName` may change over time
- One row = one symbol + one venue + one week

---

## Known ATS Venues (MPIDs)

| MPID | Venue Name | Operator |
|------|------------|----------|
| SGMT | SIGMA X2 | Goldman Sachs |
| INCR | Intelligent Cross | Imperative Execution |
| UBSA | UBS ATS | UBS |
| JPMX | JPM-X | JP Morgan |
| JPBX | JPB-X | JP Morgan |
| MLIX | INSTINCT X | Nomura (Instinet) |
| EBXL | LEVEL ATS | Level ATS |
| LATS | THE BARCLAYS ATS | Barclays |
| MSPL | MS POOL (ATS-4) | Morgan Stanley |
| IATS | IBKR ATS | Interactive Brokers |
| BIDS | BIDS ATS | BIDS Trading |
| CGXS | ONECHRONOS | OneChronos |
| ICBX | CBX | Citigroup |
| KCGM | VIRTU MATCHIT ATS | Virtu |

---

## Data Behaviors

| Behavior | Description | Handling |
|----------|-------------|----------|
| **Pipe delimiter** | Files use `\|` not `,` | Set delimiter in CSV reader |
| **Empty weeks** | Some symbols have no activity | Absence ≠ zero volume |
| **Corrections** | FINRA may republish files | Compare checksums |
| **Holiday weeks** | Reduced volume | Don't treat as anomaly |
| **Delayed publication** | May be 1-2 days late | Implement retry |

---

## FINRA API (Optional)

If using the API instead of file downloads:

**Base URL:** `https://api.finra.org/data/group/otcMarket/name/weeklySummary`

**Parameters:**
| Parameter | Required | Description |
|-----------|----------|-------------|
| `weekStartDate` | Yes | Monday of reporting week (YYYY-MM-DD) |
| `tier` | Yes | "T1" or "T2" |
| `limit` | No | Max records (default 5000) |
| `offset` | No | Pagination offset |

**Rate limits:** 10 req/sec, 10,000 req/day
