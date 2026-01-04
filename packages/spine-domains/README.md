# Spine Domains

Domain logic for the Spine framework — business rules, calculations, and pipelines.

## Purpose

`spine-domains` contains **pure business logic** that is:
- Independent of infrastructure (no database drivers, no HTTP clients)
- Shareable across all tiers (Basic, Intermediate, Advanced, Full)
- Testable without mocks or fixtures

This package defines **what** the data processing does, not **how** it runs.

---

## What Lives Here

```
spine-domains/
└── src/spine/domains/
    └── finra/                           # FINRA regulatory source
        └── otc_transparency/            # OTC Transparency dataset
            ├── schema.py                # Tier enum, table definitions, aliases
            ├── connector.py             # File parsing (PSV format)
            ├── normalizer.py            # Validation and normalization rules
            ├── calculations.py          # Aggregation and metrics
            ├── pipelines.py             # Pipeline definitions
            └── docs/                    # Domain-specific documentation
```

---

## Current Domains

### FINRA OTC Transparency

Weekly trading data from FINRA's OTC (ATS) Transparency program.

| Pipeline | Description |
|----------|-------------|
| `finra.otc_transparency.ingest_week` | Parse FINRA PSV file → raw table |
| `finra.otc_transparency.normalize_week` | Validate and normalize → normalized table |
| `finra.otc_transparency.aggregate_week` | Symbol-level aggregation → summary table |
| `finra.otc_transparency.compute_rolling` | Rolling 4-week metrics |
| `finra.otc_transparency.backfill_range` | Batch process date range |

**Tiers:**
- `OTC` — Over-the-counter securities
- `NMS_TIER_1` — NMS Tier 1 (large cap)
- `NMS_TIER_2` — NMS Tier 2 (small cap)

**Tier Aliases** (user-friendly input):
```python
"tier1" → "NMS_TIER_1"
"Tier2" → "NMS_TIER_2"
"otc"   → "OTC"
```

---

## Key Concepts

### Three-Clock Temporal Model

| Clock | Field | Example |
|-------|-------|---------|
| **Business Time** | `week_ending` | `2025-12-26` (Friday) |
| **Source Time** | `last_update_date` | When FINRA published |
| **Capture Time** | `captured_at` | When we ingested |

### Data Flow

```
FINRA PSV File
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  IngestWeekPipeline                                         │
│  - Parse PSV with connector.py                              │
│  - Insert to finra_otc_transparency_raw                     │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  NormalizeWeekPipeline                                      │
│  - Validate with normalizer.py                              │
│  - Normalize tier values, symbols                           │
│  - Insert to finra_otc_transparency_normalized              │
│  - Record rejects for invalid rows                          │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  AggregateWeekPipeline                                      │
│  - Calculate symbol-level metrics                           │
│  - Insert to finra_otc_transparency_aggregated              │
└─────────────────────────────────────────────────────────────┘
```

---

## Usage

Domains are imported by the framework, not used directly:

```python
# Framework auto-discovers and registers pipelines
from spine.framework.registry import get_pipeline, list_pipelines

# List all pipelines (includes domain pipelines)
pipelines = list_pipelines()
# → ["finra.otc_transparency.ingest_week", ...]

# Get pipeline class
IngestPipeline = get_pipeline("finra.otc_transparency.ingest_week")

# Access domain schema
from spine.domains.finra.otc_transparency.schema import (
    Tier,
    TIER_VALUES,
    TIER_ALIASES,
    TABLES,
)
```

---

## Domain Purity

Domains have **strict import restrictions**:

```python
# ✅ Allowed imports
from spine.core import WeekEnding, RejectSink, QualityRunner
from dataclasses import dataclass
from enum import Enum
import re, datetime, decimal  # stdlib only

# ❌ Forbidden imports (will fail CI)
import sqlite3        # Infrastructure
import asyncpg        # Infrastructure  
import requests       # Infrastructure
import pandas         # Heavy dependency
from spine.framework import Dispatcher  # Framework
```

Verify purity:
```bash
uv run pytest tests/test_domain_purity.py
```

---

## Adding New Domains

### Adding Another FINRA Dataset

```
spine-domains/
└── src/spine/domains/finra/
    ├── otc_transparency/     # Existing
    ├── trace/                # New: FINRA TRACE
    └── trf/                  # New: Trade Reporting Facility
```

### Adding a New Regulatory Source

```
spine-domains/
└── src/spine/domains/
    ├── finra/                # Existing
    └── sec/                  # New regulatory source
        └── edgar/            # SEC EDGAR filings
```

### Domain Structure Template

Each domain should have:

| File | Purpose |
|------|---------|
| `schema.py` | Enums, constants, table definitions |
| `connector.py` | Data source parsing |
| `normalizer.py` | Validation and normalization |
| `calculations.py` | Business logic and aggregations |
| `pipelines.py` | Pipeline definitions (decorated with `@register_pipeline`) |
| `docs/` | Domain-specific documentation |

---

## Installation

```toml
# In pyproject.toml
[tool.uv.sources]
spine-domains = { path = "../packages/spine-domains", editable = true }
```

This package uses **PEP 420 namespace packaging**. Imports remain consistent:

```python
from spine.domains.finra.otc_transparency import schema
from spine.domains.finra.otc_transparency.pipelines import IngestWeekPipeline
```

---

## Development

```bash
cd packages/spine-domains
uv sync
uv run pytest tests/ -v
```

---

## See Also

- [Repository README](../../README.md) — Full architecture overview
- [spine-core](../spine-core/README.md) — Platform primitives
- [OTC Transparency Docs](src/spine/domains/finra/otc_transparency/docs/) — Domain deep-dive
