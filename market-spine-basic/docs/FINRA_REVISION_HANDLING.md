# FINRA OTC Data Revision Handling Guide

## How Market Spine Handles Data Revisions

### The Problem
FINRA publishes OTC transparency data weekly, but they **update previous weeks** as they receive late submissions or corrections. For example:
- Monday, Jan 6: Publish week ending Dec 29 (initial data)
- Monday, Jan 13: Publish week ending Jan 5 + **revised** Dec 29 data
- Monday, Jan 20: Publish week ending Jan 12 + maybe revise Dec 29 or Jan 5

### The Solution: Capture-Based Versioning

Market Spine uses **`capture_id`** to track different captures of the same business period **without deleting old data**.

## How It Works

### 1. Capture ID Generation

Every time you ingest data, a unique `capture_id` is generated:

```python
# Format: finra.otc_transparency:{tier}:{week_ending}:{timestamp_hash}
# Example: finra.otc_transparency:NMS_TIER_1:2025-12-29:a3f5b2
```

The `capture_id` includes:
- Domain + tier (what data)
- Week ending (business period)
- Timestamp hash (when captured)

### 2. Non-Destructive Updates

When you re-ingest the same week:

```bash
# First capture (Jan 6)
spine run run finra.otc_transparency.ingest_week \
  --week-ending 2025-12-29 --tier NMS_TIER_1

# Revision capture (Jan 13) - same week!
spine run run finra.otc_transparency.ingest_week \
  --week-ending 2025-12-29 --tier NMS_TIER_1
```

**What happens:**
1. New `capture_id` generated (different timestamp)
2. Old data stays in database
3. New data written with new `capture_id`
4. Both versions queryable by `capture_id`

### 3. Latest Data Views

The schema includes `_latest` views that automatically show the most recent capture:

```sql
-- Shows only the latest capture for each week
SELECT * FROM finra_otc_transparency_normalized_latest
WHERE tier = 'NMS_TIER_1' AND week_ending = '2025-12-29';

-- Shows ALL captures (historical versions)
SELECT * FROM finra_otc_transparency_normalized
WHERE tier = 'NMS_TIER_1' AND week_ending = '2025-12-29';
```

## Scheduler Script Example

### Multi-Week Ingestion Script

```python
#!/usr/bin/env python3
"""
FINRA OTC Multi-Week Scheduler
Fetches data for current week + revisions of previous 4 weeks
"""

import subprocess
from datetime import date, timedelta

def get_last_n_mondays(n: int) -> list[str]:
    """Get last N Monday dates (week endings for OTC data)."""
    today = date.today()
    days_since_monday = (today.weekday() + 1) % 7  # 0=Monday
    last_monday = today - timedelta(days=days_since_monday)
    
    mondays = []
    for i in range(n):
        monday = last_monday - timedelta(weeks=i)
        mondays.append(monday.strftime("%Y-%m-%d"))
    
    return mondays

def ingest_finra_otc(week_ending: str, tier: str):
    """Ingest FINRA OTC data for a specific week and tier."""
    print(f"Ingesting {tier} for week ending {week_ending}...")
    
    cmd = [
        "uv", "run", "spine", "run", "run",
        "finra.otc_transparency.ingest_week",
        "--week-ending", week_ending,
        "--tier", tier,
        # No --file means it will fetch from FINRA API
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode == 0:
        print(f"  ✓ Success")
    else:
        print(f"  ✗ Failed: {result.stderr}")
        raise Exception(f"Ingest failed for {tier}/{week_ending}")

def normalize_week(week_ending: str, tier: str):
    """Normalize ingested data."""
    print(f"Normalizing {tier} for week ending {week_ending}...")
    
    cmd = [
        "uv", "run", "spine", "run", "run",
        "finra.otc_transparency.normalize_week",
        "--week-ending", week_ending,
        "--tier", tier,
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode == 0:
        print(f"  ✓ Success")
    else:
        print(f"  ✗ Failed: {result.stderr}")

def main():
    """
    Main scheduler function.
    
    Strategy:
    - Fetch current week + previous 4 weeks (captures revisions)
    - Process all tiers
    - Old data stays in database, new captures added
    """
    # Get last 5 Mondays (current + 4 historical for revisions)
    weeks = get_last_n_mondays(5)
    tiers = ["NMS_TIER_1", "NMS_TIER_2", "OTC"]
    
    print(f"FINRA OTC Scheduler - {date.today()}")
    print(f"Processing weeks: {weeks}")
    print(f"Processing tiers: {tiers}")
    print()
    
    for week in weeks:
        for tier in tiers:
            try:
                # Ingest raw data (creates new capture_id)
                ingest_finra_otc(week, tier)
                
                # Normalize (uses latest capture_id)
                normalize_week(week, tier)
                
            except Exception as e:
                print(f"ERROR processing {tier}/{week}: {e}")
                # Continue with next week/tier
                continue
    
    print()
    print("✓ Scheduler run complete")

if __name__ == "__main__":
    main()
```

### Usage

```bash
# Run manually
python scripts/finra_otc_scheduler.py

# Run via cron (Linux/macOS)
# Every Monday at 11am
0 11 * * 1 cd /path/to/market-spine-basic && uv run python scripts/finra_otc_scheduler.py

# Run via Windows Task Scheduler
# Trigger: Weekly, Monday, 11:00 AM
# Action: python C:\path\to\market-spine-basic\scripts\finra_otc_scheduler.py
```

## Querying Revisions

### Get Latest Data Only

```python
# CLI
spine query weeks --tier NMS_TIER_1

# SQL (uses _latest view)
SELECT * FROM finra_otc_transparency_normalized_latest
WHERE tier = 'NMS_TIER_1'
ORDER BY week_ending DESC
LIMIT 10;
```

### Compare Revisions

```sql
-- See all captures of a specific week
SELECT 
    capture_id,
    captured_at,
    COUNT(*) as row_count,
    SUM(total_shares) as total_shares
FROM finra_otc_transparency_normalized
WHERE tier = 'NMS_TIER_1' 
  AND week_ending = '2025-12-29'
GROUP BY capture_id, captured_at
ORDER BY captured_at;

-- Results show different versions:
-- capture_id                                    | captured_at         | row_count | total_shares
-- ----------------------------------------------|---------------------|-----------|-------------
-- finra.otc_transparency:NMS_TIER_1:2025-12-29:a3f5b2 | 2026-01-06 10:00:00 | 48765     | 1250000000
-- finra.otc_transparency:NMS_TIER_1:2025-12-29:b7c3d4 | 2026-01-13 10:00:00 | 48975     | 1255000000  <-- Revision
```

### Audit Trail

```sql
-- Track when data changed
SELECT 
    week_ending,
    tier,
    COUNT(DISTINCT capture_id) as num_captures,
    MIN(captured_at) as first_capture,
    MAX(captured_at) as latest_capture
FROM finra_otc_transparency_raw
GROUP BY week_ending, tier
HAVING COUNT(DISTINCT capture_id) > 1  -- Only show revised weeks
ORDER BY week_ending DESC;
```

## Advanced: Manual Deletion (If Needed)

**You typically DON'T need this**, but if you want to clean up old captures:

```sql
-- Delete old captures (keep only latest)
DELETE FROM finra_otc_transparency_raw
WHERE capture_id NOT IN (
    SELECT capture_id
    FROM finra_otc_transparency_raw
    WHERE tier = 'NMS_TIER_1' AND week_ending = '2025-12-29'
    ORDER BY captured_at DESC
    LIMIT 1
);

-- Or delete all captures for a specific week (nuclear option)
DELETE FROM finra_otc_transparency_raw
WHERE tier = 'NMS_TIER_1' AND week_ending = '2025-12-29';
```

**WARNING:** Deleting data breaks audit trail and temporal reconstruction. Only do this if you have storage constraints.

## Storage Considerations

### How Much Space Do Revisions Use?

Rough estimate for FINRA OTC:
- One week, one tier: ~2-5 MB (depends on symbols/venues)
- 52 weeks × 3 tiers = ~300 MB per year
- With 5 revisions per week (excessive): ~1.5 GB per year

**Recommendation:** Keep all captures for audit trail. Storage is cheap, audit trails are valuable.

### Cleanup Policy (Optional)

If storage becomes an issue:

```python
# Keep only captures from last 90 days
DELETE FROM finra_otc_transparency_raw
WHERE captured_at < datetime('now', '-90 days');

# Keep only latest 3 captures per week
WITH ranked_captures AS (
    SELECT 
        capture_id,
        ROW_NUMBER() OVER (
            PARTITION BY tier, week_ending 
            ORDER BY captured_at DESC
        ) as rn
    FROM finra_otc_transparency_raw
)
DELETE FROM finra_otc_transparency_raw
WHERE capture_id IN (
    SELECT capture_id FROM ranked_captures WHERE rn > 3
);
```

## Key Takeaways

✅ **No manual deletion needed** - System handles revisions automatically  
✅ **Multiple captures coexist** - Old data stays for audit trail  
✅ **Latest views** - Queries use most recent data by default  
✅ **Scheduler friendly** - Re-run same weeks safely  
✅ **Temporal reconstruction** - "What did data look like on date X?"  
✅ **Compliance ready** - Full audit trail of data changes  

## Next Steps

1. **Create scheduler script** using the template above
2. **Test with one week** to see capture_id in action
3. **Re-run same week** to see revision handling
4. **Query revisions** to verify both versions exist
5. **Set up automated schedule** for weekly runs

Need help implementing? Check:
- [docs/ops/scheduling.md](c:\projects\spine-core\docs\ops\scheduling.md) - Scheduling patterns
- [docs/domains/otc/03-pipeline.md](c:\projects\spine-core\docs\domains\otc\README.md) - Pipeline details
- [docs/fitness/03-calc-lifecycle-scenarios.md](c:\projects\spine-core\docs\fitness\03-calc-lifecycle-scenarios.md) - Revision scenarios
