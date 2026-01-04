# FINRA OTC Transparency Data Overview

## Regulatory Background

FINRA (Financial Industry Regulatory Authority) mandates transparency in over-the-counter trading through two key rules:

### FINRA Rule 6110 - NMS Stock Weekly Data

Requires Alternative Trading Systems (ATSs) and other broker-dealers to report weekly trading data for **NMS stocks** (National Market System securities). These are exchange-listed stocks that trade through off-exchange venues.

**NMS Tier Classification:**
- **Tier 1**: Stocks in the S&P 500 Index or Russell 1000 Index
- **Tier 2**: All other NMS stocks

### FINRA Rule 6610 - OTC Equity Weekly Data

Requires similar reporting for **OTC equity securities** - securities not listed on national exchanges. This includes:
- Pink Sheets securities
- OTCBB (OTC Bulletin Board) securities
- Other unlisted equities

## What's in the Data?

Each weekly report contains:

| Field | Description |
|-------|-------------|
| Symbol | Stock ticker symbol |
| MPID | Market Participant Identifier (identifies the venue) |
| Total Shares | Weekly share volume for this symbol at this venue |
| Total Trades | Weekly trade count for this symbol at this venue |

### ATS vs Non-ATS

The data distinguishes between two venue types:

**ATS (Alternative Trading Systems)**
- Also known as "dark pools"
- Registered with SEC as broker-dealers operating a trading system
- Examples: Citadel Connect, Virtu, Two Sigma

**Non-ATS**
- OTC trading at broker-dealers
- Includes internalizers and wholesalers
- Market makers executing against their own inventory

## Data Semantics

### What Does the Data Represent?

Each row represents:
> "During week ending [date], market participant [MPID] executed [shares] shares in [trades] trades for symbol [symbol]"

### Aggregation Level

- **Venue-Level**: Raw data is per (week, tier, symbol, mpid)
- **Symbol-Level**: Aggregated across all venues per symbol
- **Market-Level**: Aggregated across all symbols (total OTC volume)

### Caveats

1. **Delayed Publication**: Data is published with a T+3 lag
2. **Weekly Granularity**: No intraday or daily breakdowns
3. **Volume Only**: No price data included
4. **ATS Identity**: MPID identifies venues but not clients
5. **Thresholds**: Some venues may suppress low-volume symbols

## Use Cases

### Market Structure Analysis
- Compare ATS vs non-ATS market share
- Track venue concentration
- Identify dark pool activity trends

### Liquidity Research
- Assess off-exchange liquidity for symbols
- Monitor venue diversity for a stock
- Study retail order flow patterns

### Regulatory Compliance
- Best execution analysis
- Trade surveillance
- Market manipulation detection

## Data Quality Notes

- FINRA may issue corrections (restatements)
- Our `capture_id` system tracks different captures of the same week
- Use latest capture for most analyses (rolling metrics do this automatically)

## External Resources

- [FINRA OTC Transparency Portal](https://otctransparency.finra.org/)
- [SEC Rule 606 Reports](https://www.sec.gov/rules/final/2018/34-84528.pdf) (related disclosure)
- [FINRA ATS Transparency FAQ](https://www.finra.org/rules-guidance/guidance/ats-transparency-data-faq)
