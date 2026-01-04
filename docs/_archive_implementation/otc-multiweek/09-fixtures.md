# 09: Test Fixtures

> **Purpose**: Provide realistic test data for the 6-week backfill workflow. These fixtures enable golden tests that verify the full pipeline produces correct results.

---

## Fixture Design Goals

1. **Realistic**: Use FINRA-style pipe-delimited format
2. **Small**: 5-10 symbols, 3-5 venues per week (~12-15 records)
3. **Predictable**: Known values for golden test assertions
4. **Edge cases**: Include at least one rejectable record
5. **Temporal**: 6 consecutive Friday dates

---

## Directory Structure

```
data/
└── fixtures/
    └── otc/
        ├── README.md                    # Documentation
        ├── week_2025-11-21.psv          # Week 1
        ├── week_2025-11-28.psv          # Week 2
        ├── week_2025-12-05.psv          # Week 3
        ├── week_2025-12-12.psv          # Week 4
        ├── week_2025-12-19.psv          # Week 5
        └── week_2025-12-26.psv          # Week 6
```

---

## File Format

FINRA OTC transparency files are pipe-delimited (PSV):

```
WeekEnding|Tier|Symbol|MPID|TotalShares|TotalTrades
```

- **WeekEnding**: ISO date (Friday)
- **Tier**: `NMS_TIER_1`, `NMS_TIER_2`, or `OTC`
- **Symbol**: Stock ticker (1-10 chars, starts with letter)
- **MPID**: Market Participant ID (4 alphanumeric chars)
- **TotalShares**: Integer >= 0
- **TotalTrades**: Integer >= 0

---

## Fixture Files

### `data/fixtures/otc/README.md`

```markdown
# OTC Test Fixtures

These fixtures provide realistic test data for the multi-week OTC workflow.

## Symbols (5)
- AAPL: Apple Inc (high volume, stable)
- TSLA: Tesla Inc (high volume, trending up)
- NVDA: Nvidia (high volume, trending down)
- MSFT: Microsoft (medium volume, stable)
- META: Meta Platforms (medium volume, variable)

## Venues (4)
- NITE: Virtu Financial
- CITD: Citadel Securities
- JANE: Jane Street
- VIRT: Virtu Americas

## Weeks (6)
- 2025-11-21: Normal data
- 2025-11-28: Normal data
- 2025-12-05: Contains BAD$YM (invalid symbol) for reject testing
- 2025-12-12: Normal data
- 2025-12-19: Contains negative volume for reject testing
- 2025-12-26: Normal data

## Expected Results After Backfill
- Total raw records: 73 (72 valid + 1 parse error in week 2025-12-05)
- Normalized records: 71 (2 rejected: invalid symbol, negative volume)
- Symbols with complete 6-week rolling: 5
- Rejects table should have 2 entries
```

---

### `data/fixtures/otc/week_2025-11-21.psv`

```
WeekEnding|Tier|Symbol|MPID|TotalShares|TotalTrades
2025-11-21|NMS_TIER_1|AAPL|NITE|1500000|8500
2025-11-21|NMS_TIER_1|AAPL|CITD|1200000|6200
2025-11-21|NMS_TIER_1|AAPL|JANE|800000|4100
2025-11-21|NMS_TIER_1|TSLA|NITE|900000|4500
2025-11-21|NMS_TIER_1|TSLA|VIRT|600000|3200
2025-11-21|NMS_TIER_1|NVDA|NITE|2000000|10000
2025-11-21|NMS_TIER_1|NVDA|CITD|1500000|7500
2025-11-21|NMS_TIER_1|MSFT|JANE|500000|2500
2025-11-21|NMS_TIER_1|MSFT|VIRT|400000|2000
2025-11-21|NMS_TIER_1|META|NITE|700000|3500
2025-11-21|NMS_TIER_1|META|CITD|500000|2500
```

**Totals**: 11 records, all valid

---

### `data/fixtures/otc/week_2025-11-28.psv`

```
WeekEnding|Tier|Symbol|MPID|TotalShares|TotalTrades
2025-11-28|NMS_TIER_1|AAPL|NITE|1550000|8700
2025-11-28|NMS_TIER_1|AAPL|CITD|1250000|6400
2025-11-28|NMS_TIER_1|AAPL|JANE|820000|4200
2025-11-28|NMS_TIER_1|TSLA|NITE|950000|4700
2025-11-28|NMS_TIER_1|TSLA|VIRT|650000|3400
2025-11-28|NMS_TIER_1|NVDA|NITE|1900000|9500
2025-11-28|NMS_TIER_1|NVDA|CITD|1450000|7200
2025-11-28|NMS_TIER_1|MSFT|JANE|520000|2600
2025-11-28|NMS_TIER_1|MSFT|VIRT|420000|2100
2025-11-28|NMS_TIER_1|META|NITE|720000|3600
2025-11-28|NMS_TIER_1|META|CITD|520000|2600
2025-11-28|NMS_TIER_1|META|JANE|300000|1500
```

**Totals**: 12 records, all valid

---

### `data/fixtures/otc/week_2025-12-05.psv`

```
WeekEnding|Tier|Symbol|MPID|TotalShares|TotalTrades
2025-12-05|NMS_TIER_1|AAPL|NITE|1600000|9000
2025-12-05|NMS_TIER_1|AAPL|CITD|1280000|6500
2025-12-05|NMS_TIER_1|AAPL|JANE|850000|4300
2025-12-05|NMS_TIER_1|TSLA|NITE|1000000|5000
2025-12-05|NMS_TIER_1|TSLA|VIRT|700000|3600
2025-12-05|NMS_TIER_1|NVDA|NITE|1850000|9200
2025-12-05|NMS_TIER_1|NVDA|CITD|1400000|7000
2025-12-05|NMS_TIER_1|MSFT|JANE|540000|2700
2025-12-05|NMS_TIER_1|MSFT|VIRT|440000|2200
2025-12-05|NMS_TIER_1|META|NITE|750000|3750
2025-12-05|NMS_TIER_1|META|CITD|540000|2700
2025-12-05|NMS_TIER_1|BAD$YM|NITE|100000|500
```

**Totals**: 12 records, 1 invalid (`BAD$YM` has invalid symbol character `$`)

---

### `data/fixtures/otc/week_2025-12-12.psv`

```
WeekEnding|Tier|Symbol|MPID|TotalShares|TotalTrades
2025-12-12|NMS_TIER_1|AAPL|NITE|1580000|8800
2025-12-12|NMS_TIER_1|AAPL|CITD|1260000|6400
2025-12-12|NMS_TIER_1|AAPL|JANE|830000|4200
2025-12-12|NMS_TIER_1|TSLA|NITE|1050000|5200
2025-12-12|NMS_TIER_1|TSLA|VIRT|720000|3700
2025-12-12|NMS_TIER_1|NVDA|NITE|1800000|9000
2025-12-12|NMS_TIER_1|NVDA|CITD|1350000|6800
2025-12-12|NMS_TIER_1|MSFT|JANE|530000|2650
2025-12-12|NMS_TIER_1|MSFT|VIRT|430000|2150
2025-12-12|NMS_TIER_1|META|NITE|730000|3650
2025-12-12|NMS_TIER_1|META|CITD|530000|2650
2025-12-12|NMS_TIER_1|META|VIRT|250000|1250
```

**Totals**: 12 records, all valid

---

### `data/fixtures/otc/week_2025-12-19.psv`

```
WeekEnding|Tier|Symbol|MPID|TotalShares|TotalTrades
2025-12-19|NMS_TIER_1|AAPL|NITE|1620000|9100
2025-12-19|NMS_TIER_1|AAPL|CITD|1300000|6600
2025-12-19|NMS_TIER_1|AAPL|JANE|870000|4400
2025-12-19|NMS_TIER_1|TSLA|NITE|1100000|5500
2025-12-19|NMS_TIER_1|TSLA|VIRT|750000|3800
2025-12-19|NMS_TIER_1|NVDA|NITE|1750000|8800
2025-12-19|NMS_TIER_1|NVDA|CITD|1300000|6500
2025-12-19|NMS_TIER_1|MSFT|JANE|550000|2750
2025-12-19|NMS_TIER_1|MSFT|VIRT|450000|2250
2025-12-19|NMS_TIER_1|META|NITE|760000|3800
2025-12-19|NMS_TIER_1|META|CITD|550000|2750
2025-12-19|NMS_TIER_1|BADV|NITE|-50000|100
```

**Totals**: 12 records, 1 invalid (`BADV` has negative volume)

---

### `data/fixtures/otc/week_2025-12-26.psv`

```
WeekEnding|Tier|Symbol|MPID|TotalShares|TotalTrades
2025-12-26|NMS_TIER_1|AAPL|NITE|1650000|9200
2025-12-26|NMS_TIER_1|AAPL|CITD|1320000|6700
2025-12-26|NMS_TIER_1|AAPL|JANE|890000|4500
2025-12-26|NMS_TIER_1|TSLA|NITE|1150000|5700
2025-12-26|NMS_TIER_1|TSLA|VIRT|780000|3900
2025-12-26|NMS_TIER_1|NVDA|NITE|1700000|8500
2025-12-26|NMS_TIER_1|NVDA|CITD|1250000|6300
2025-12-26|NMS_TIER_1|MSFT|JANE|560000|2800
2025-12-26|NMS_TIER_1|MSFT|VIRT|460000|2300
2025-12-26|NMS_TIER_1|META|NITE|780000|3900
2025-12-26|NMS_TIER_1|META|CITD|570000|2850
2025-12-26|NMS_TIER_1|META|VIRT|280000|1400
```

**Totals**: 12 records, all valid

---

## Expected Results After Full Backfill

### Manifest (`otc_week_manifest`)

| week_ending | tier | stage | row_count_inserted | row_count_normalized | row_count_rejected |
|-------------|------|-------|-------------------|---------------------|-------------------|
| 2025-11-21 | NMS_TIER_1 | AGGREGATED | 11 | 11 | 0 |
| 2025-11-28 | NMS_TIER_1 | AGGREGATED | 12 | 12 | 0 |
| 2025-12-05 | NMS_TIER_1 | AGGREGATED | 12 | 11 | 1 |
| 2025-12-12 | NMS_TIER_1 | AGGREGATED | 12 | 12 | 0 |
| 2025-12-19 | NMS_TIER_1 | AGGREGATED | 12 | 11 | 1 |
| 2025-12-26 | NMS_TIER_1 | SNAPSHOT | 12 | 12 | 0 |

### Rejects (`otc_rejects`)

| week_ending | stage | reason_code | reason_detail |
|-------------|-------|-------------|---------------|
| 2025-12-05 | NORMALIZE | INVALID_SYMBOL | Invalid symbol format: 'BAD$YM' |
| 2025-12-19 | NORMALIZE | NEGATIVE_VOLUME | total_shares=-50000 |

### Symbol Summary (Week 2025-12-26)

| symbol | total_volume | total_trades | venue_count |
|--------|-------------|--------------|-------------|
| AAPL | 3,860,000 | 20,400 | 3 |
| TSLA | 1,930,000 | 9,600 | 2 |
| NVDA | 2,950,000 | 14,800 | 2 |
| MSFT | 1,020,000 | 5,100 | 2 |
| META | 1,630,000 | 8,150 | 3 |

### Rolling Metrics (Week 2025-12-26)

| symbol | avg_6w_volume | weeks_in_window | is_complete_window | trend_direction |
|--------|---------------|-----------------|-------------------|-----------------|
| AAPL | ~3,600,000 | 6 | 1 | UP |
| TSLA | ~1,700,000 | 6 | 1 | UP |
| NVDA | ~3,300,000 | 6 | 1 | DOWN |
| MSFT | ~950,000 | 6 | 1 | FLAT |
| META | ~1,400,000 | 6 | 1 | UP |

### Quality Checks

All checks should PASS for valid weeks:
- `no_negative_volumes`: PASS
- `no_negative_trades`: PASS
- `market_share_sum_100`: PASS (sum ≈ 100%)
- `symbol_count_positive`: PASS (5 symbols)
- `venue_count_positive`: PASS (4 venues)

---

## Fixture Generation Script

For generating new fixtures or extending existing ones:

```python
#!/usr/bin/env python3
"""Generate OTC test fixtures with realistic patterns."""

import random
from datetime import date, timedelta
from decimal import Decimal

SYMBOLS = ["AAPL", "TSLA", "NVDA", "MSFT", "META"]
VENUES = ["NITE", "CITD", "JANE", "VIRT"]

# Base volumes for each symbol
BASE_VOLUMES = {
    "AAPL": 1_500_000,
    "TSLA": 900_000,
    "NVDA": 2_000_000,
    "MSFT": 500_000,
    "META": 700_000,
}

# Trend multipliers per week (1.0 = no change)
TRENDS = {
    "AAPL": [1.0, 1.03, 1.07, 1.05, 1.08, 1.10],  # UP
    "TSLA": [1.0, 1.05, 1.11, 1.17, 1.22, 1.28],  # UP (stronger)
    "NVDA": [1.0, 0.95, 0.92, 0.90, 0.88, 0.85],  # DOWN
    "MSFT": [1.0, 1.02, 1.00, 1.01, 1.02, 1.01],  # FLAT
    "META": [1.0, 1.03, 1.07, 1.04, 1.09, 1.10],  # UP
}

def generate_week(week_ending: date, tier: str = "NMS_TIER_1") -> list[str]:
    """Generate fixture lines for a single week."""
    lines = ["WeekEnding|Tier|Symbol|MPID|TotalShares|TotalTrades"]
    
    week_index = 0  # Would be calculated based on date
    
    for symbol in SYMBOLS:
        base = BASE_VOLUMES[symbol]
        trend = TRENDS[symbol][week_index]
        
        # Distribute across venues
        for venue in VENUES[:random.randint(2, 4)]:
            share = random.uniform(0.2, 0.5)
            volume = int(base * trend * share)
            trades = volume // random.randint(150, 250)
            
            lines.append(
                f"{week_ending.isoformat()}|{tier}|{symbol}|{venue}|{volume}|{trades}"
            )
    
    return lines

if __name__ == "__main__":
    # Generate 6 weeks
    start = date(2025, 11, 21)
    for i in range(6):
        week = start + timedelta(weeks=i)
        lines = generate_week(week)
        
        filename = f"week_{week.isoformat()}.psv"
        with open(filename, "w") as f:
            f.write("\n".join(lines))
        
        print(f"Generated {filename}: {len(lines)-1} records")
```

---

## Next: Read [10-golden-tests.md](10-golden-tests.md) for test implementations
