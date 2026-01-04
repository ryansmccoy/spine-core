# FINRA OTC Weekly Transparency Data

> **Purpose:** Process and serve FINRA OTC Weekly Transparency data  
> **Data Type:** Weekly aggregated volume by symbol and venue (NOT trade-level)  
> **Last Updated:** 2026-01-02

---

## Overview

FINRA publishes **weekly aggregate trading volume** for OTC equities, showing where trading occurs across Alternative Trading Systems (ATSs).

**Key characteristics:**
- Pre-aggregated weekly totals (not individual trades)
- One record = one symbol + one venue + one week
- Published with 2-week (T1) or 4-week (T2) delay

## Documentation

| Document | Description |
|----------|-------------|
| [Data Source](01-data-source.md) | FINRA file format, fields, known venues |
| [Data Model](02-data-model.md) | SQL tables, Python models, TimescaleDB config |
| [Pipeline](03-pipeline.md) | Ingest, normalize, compute stages |
| [Quality](04-quality.md) | Validation, quality gates, quality metrics |
| [Analytics](05-analytics.md) | Rolling averages, concentration (HHI), market share |
| [API](06-api.md) | REST endpoints, response models, examples |
| [Operations](07-operations.md) | Monitoring, alerting, recovery procedures |

## Pipeline Philosophy

```
┌─────────┐   ┌─────────┐   ┌─────────┐   ┌─────────┐   ┌─────────┐
│ CAPTURE │ → │  STORE  │ → │ QUALITY │ → │ COMPUTE │ → │  SERVE  │
│         │   │         │   │         │   │         │   │         │
│ Ingest  │   │ Append- │   │ Validate│   │ Derive  │   │ Query & │
│ with    │   │ only    │   │ before  │   │ metrics │   │ expose  │
│ lineage │   │ storage │   │ compute │   │ safely  │   │ via API │
└─────────┘   └─────────┘   └─────────┘   └─────────┘   └─────────┘
```

**Core principles:**
1. **Lineage** - Every row traces to source via `capture_id`
2. **Immutability** - Append-only storage, never UPDATE/DELETE
3. **Quality Gates** - Validate before computing
4. **Versioning** - Metrics link to `execution_id`
5. **As-Of Queries** - Point-in-time reproducibility

## Business Use Cases

| Use Case | Question Answered |
|----------|-------------------|
| Venue market share | Which ATSs have the most volume for AAPL? |
| Best execution | Where should we route orders? |
| Trend analysis | How has venue distribution changed over 6 weeks? |
| Concentration risk | Is one venue dominant? (HHI metric) |

## Data Tiers

| Tier | Delay | Content |
|------|-------|---------|
| **T1** | 2 weeks | ATS volume |
| **T2** | 4 weeks | Non-ATS OTC volume |

**Timeline example (week ending 2025-12-29):**
- T1 available: Wednesday, January 8, 2026
- T2 available: Wednesday, January 22, 2026
