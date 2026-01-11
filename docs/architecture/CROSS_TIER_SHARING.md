# Cross-Tier Code Sharing

This document explains how `spine.core` and `spine.domains.*` are shared
across all tiers (Basic, Intermediate, Advanced, Full).

---

## Monorepo Layering

```
spine-core/
├── packages/                    # Shared packages (symlinked or installed)
│   ├── spine-core/              # Platform primitives
│   │   ├── pyproject.toml
│   │   └── src/spine/core/
│   │
│   └── spine-domains-otc/       # OTC domain
│       ├── pyproject.toml
│       └── src/spine/domains/otc/
│
├── market-spine-basic/          # Basic tier
│   ├── pyproject.toml           # depends on spine-core, spine-domains-otc
│   └── src/market_spine/        # Tier-specific infrastructure
│
├── market-spine-intermediate/   # Intermediate tier  
│   ├── pyproject.toml           # depends on spine-core, spine-domains-otc
│   └── src/market_spine/        # Tier-specific: async wrappers
│
├── market-spine-advanced/       # Advanced tier
│   ├── pyproject.toml           # depends on spine-core, spine-domains-otc
│   └── src/market_spine/        # Tier-specific: Celery tasks
│
└── market-spine-full/           # Full tier
    ├── pyproject.toml           # depends on spine-core, spine-domains-otc
    └── src/market_spine/        # Tier-specific: event handlers
```

---

## Import Rules

### 1. Domain Code CAN Import

```python
# ✅ Platform primitives
from spine.core import WorkManifest, RejectSink, QualityRunner, WeekEnding

# ✅ Other domain modules
from spine.domains.otc.schema import TABLES, STAGES
from spine.domains.otc.calculations import compute_symbol_summaries

# ✅ Standard library
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional
```

### 2. Domain Code CANNOT Import

```python
# ❌ Database drivers
import sqlite3  # FORBIDDEN
import asyncpg  # FORBIDDEN

# ❌ Task queues
from celery import Celery  # FORBIDDEN

# ❌ HTTP clients
import httpx  # FORBIDDEN
import requests  # FORBIDDEN

# ❌ Cloud SDKs
import boto3  # FORBIDDEN
```

### 3. Tier Code CAN Import

```python
# ✅ Shared packages
from spine.core import WorkManifest, create_core_tables
from spine.domains.otc.pipelines import IngestWeekPipeline

# ✅ Infrastructure (tier-specific)
import sqlite3  # OK in tier code
import asyncpg  # OK in intermediate/advanced/full
from celery import Celery  # OK in advanced tier
```

---

## Installation Methods

### Method 1: Editable Install (Development)

```bash
# In each tier's pyproject.toml
[project]
dependencies = [
    "spine-core @ {root:parent}/packages/spine-core",
    "spine-domains-otc @ {root:parent}/packages/spine-domains-otc",
]

# Or with pip
cd market-spine-basic
pip install -e ../packages/spine-core
pip install -e ../packages/spine-domains-otc
pip install -e .
```

### Method 2: Path Dependencies (Monorepo)

```toml
# market-spine-basic/pyproject.toml
[tool.setuptools]
package-dir = {"" = "src"}

[project]
dependencies = []

[tool.uv.sources]
spine-core = { path = "../packages/spine-core", editable = true }
spine-domains-otc = { path = "../packages/spine-domains-otc", editable = true }
```

### Method 3: Symlinks (Simple)

```bash
# Create symlinks so tiers can import directly
cd market-spine-basic/src
ln -s ../../packages/spine-core/src/spine .
# Now `from spine.core import ...` works

cd market-spine-intermediate/src
ln -s ../../packages/spine-core/src/spine .
# Same code, different tier
```

---

## How Tiers Differ

### Basic Tier (SQLite, Sync)

```python
# market-spine-basic/src/market_spine/db.py
import sqlite3

def get_connection():
    conn = sqlite3.connect("spine.db")
    conn.row_factory = sqlite3.Row
    return conn

# Domains use this directly - no wrapper needed
# spine.core primitives work with sqlite3.Connection
```

### Intermediate Tier (PostgreSQL, Async)

```python
# market-spine-intermediate/src/market_spine/db.py
import asyncio
import asyncpg

class SyncPgAdapter:
    """Wraps asyncpg to provide sync interface for spine.core primitives."""
    
    def __init__(self, async_conn):
        self._conn = async_conn
        self._loop = asyncio.get_event_loop()
    
    def execute(self, sql: str, params: tuple = ()):
        sql = self._convert_placeholders(sql)
        return self._loop.run_until_complete(
            self._conn.fetch(sql, *params)
        )
    
    def commit(self):
        pass  # asyncpg auto-commits

def get_connection():
    loop = asyncio.get_event_loop()
    async_conn = loop.run_until_complete(asyncpg.connect(...))
    return SyncPgAdapter(async_conn)

# Now spine.core primitives work unchanged!
```

### Advanced Tier (Celery Tasks)

```python
# market-spine-advanced/src/market_spine/tasks.py
from celery import Celery
from spine.domains.otc.pipelines import IngestWeekPipeline
from market_spine.db import get_connection

app = Celery("spine")

@app.task
def ingest_week(week_ending: str, tier: str, file_path: str):
    """Celery task wrapping OTC ingest pipeline."""
    # Domain code is UNCHANGED - just wrapped in Celery task
    pipeline = IngestWeekPipeline({
        "week_ending": week_ending,
        "tier": tier,
        "file_path": file_path,
    })
    return pipeline.run()
```

### Full Tier (Event-Driven)

```python
# market-spine-full/src/market_spine/handlers.py
from spine.domains.otc.pipelines import IngestWeekPipeline
from market_spine.events import subscribe

@subscribe("otc.file.arrived")
async def handle_file_arrived(event: dict):
    """Event handler for file arrival."""
    # Domain code is UNCHANGED - just triggered by event
    pipeline = IngestWeekPipeline({
        "week_ending": event["week_ending"],
        "tier": event["tier"],
        "file_path": event["file_path"],
    })
    await asyncio.to_thread(pipeline.run)  # Run sync code in thread
```

---

## Verification

### 1. Run Domain Purity Check

```bash
python tests/test_domain_purity.py
```

### 2. Verify Same Code Across Tiers

```bash
# All tiers should use identical spine.core and spine.domains
diff market-spine-basic/src/spine market-spine-intermediate/src/spine
# (Should be empty or show symlinks)
```

### 3. Test Pipeline Works on Each Tier

```bash
# Basic
cd market-spine-basic
python -c "from spine.domains.otc.pipelines import IngestWeekPipeline; print('OK')"

# Intermediate
cd market-spine-intermediate  
python -c "from spine.domains.otc.pipelines import IngestWeekPipeline; print('OK')"

# All should print "OK" with no import errors
```

---

## Summary

| Layer | Contains | Imports |
|-------|----------|---------|
| `spine.core` | Platform primitives | Standard library only |
| `spine.domains.*` | Business logic | `spine.core` + stdlib |
| `market_spine` (tier) | Infrastructure | Everything |

**The key insight**: Domain code is identical across all tiers. Only the tier's
infrastructure (db.py, tasks.py, handlers.py) differs.
