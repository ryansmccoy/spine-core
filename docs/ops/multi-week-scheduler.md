# Multi-Week Scheduler Design

## Overview

The FINRA OTC multi-week scheduler enables production-grade data ingestion with revision detection, lookback windows, and non-destructive restatements. It's designed to run on cron, Kubernetes CronJobs, or OpenShift without requiring Docker or heavyweight orchestration frameworks.

**Key Principles:**
- **No deletions** - Historical captures preserved via `capture_id` versioning
- **Revision detection** - Skip unchanged weeks to avoid unnecessary reprocessing
- **Lookback windows** - Process multiple weeks per run (FINRA can revise prior weeks)
- **Robust failure handling** - Continue processing other partitions when one fails
- **Pure Python** - No Docker dependency, works in any Python 3.10+ environment

---

## 1. Which Weeks to Ingest (Lookback Windows)

### 1A. Default Behavior: Lookback N Weeks

```bash
# Process last 6 weeks (current + 5 prior for revisions)
python scripts/run_finra_weekly_schedule.py --lookback-weeks 6

# Computes week_endings:
# - 2026-01-03 (most recent Friday)
# - 2025-12-27
# - 2025-12-20
# - 2025-12-13
# - 2025-12-06
# - 2025-11-29
```

**Why 6 weeks?**
- FINRA typically revises data up to 4 weeks after initial publication
- Extra buffer (6 weeks) catches late corrections
- Configurable via `--lookback-weeks` for different requirements

### 1B. Week Calculation Logic

```python
from datetime import date, timedelta

def calculate_target_weeks(lookback_weeks: int, reference_date: date | None = None) -> list[date]:
    """
    Calculate target week_endings (Fridays) for lookback window.
    
    Args:
        lookback_weeks: Number of weeks to look back (including current)
        reference_date: Starting point (default: today)
    
    Returns:
        List of Friday dates in descending order (newest first)
    """
    if reference_date is None:
        reference_date = date.today()
    
    # Find most recent Friday (or today if Friday)
    days_since_friday = (reference_date.weekday() - 4) % 7
    most_recent_friday = reference_date - timedelta(days=days_since_friday)
    
    # Generate lookback_weeks Fridays
    weeks = []
    for i in range(lookback_weeks):
        week_ending = most_recent_friday - timedelta(weeks=i)
        weeks.append(week_ending)
    
    return weeks
```

**Example outputs:**
```python
# Today is Monday, 2026-01-05
calculate_target_weeks(4)
# → [2026-01-03, 2025-12-27, 2025-12-20, 2025-12-13]

# Today is Friday, 2026-01-02
calculate_target_weeks(4)
# → [2026-01-02, 2025-12-26, 2025-12-19, 2025-12-12]
```

### 1C. Manual Week Override (Backfill)

```bash
# Process specific weeks (comma-separated)
python scripts/run_finra_weekly_schedule.py \
  --weeks 2025-12-15,2025-12-22,2025-12-29 \
  --force

# Ignores --lookback-weeks when --weeks provided
```

**Use cases:**
- Backfill historical data
- Reprocess specific weeks after FINRA corrections
- Manual restatement for audit requirements

---

## 2. Revision Detection (Skip Unchanged Weeks)

### 2A. Problem: Avoid Unnecessary Reprocessing

FINRA may not change data every week. Reprocessing unchanged weeks wastes:
- API quota (if rate-limited)
- Compute resources (normalization + analytics)
- Database IOPS (write amplification)
- Storage (duplicate captures)

**Goal:** Only ingest/process weeks that have changed since last successful capture.

### 2B. Detection Method 1: `lastUpdateDate` (Preferred)

Many data sources include metadata indicating last modification time. For FINRA OTC:

```python
def check_revision_needed_via_metadata(
    week_ending: date,
    tier: str,
    source_last_updated: datetime,
    db_connection
) -> tuple[bool, str]:
    """
    Compare source lastUpdateDate with our latest capture's metadata.
    
    Returns:
        (needs_revision: bool, reason: str)
    """
    # Query latest capture for this partition
    latest_capture = db_connection.execute("""
        SELECT 
            json_extract(metadata_json, '$.source_last_updated') as stored_last_updated,
            captured_at
        FROM core_manifest
        WHERE domain = 'finra.otc_transparency'
          AND stage = 'RAW'
          AND json_extract(partition_key, '$.week_ending') = ?
          AND json_extract(partition_key, '$.tier') = ?
        ORDER BY captured_at DESC
        LIMIT 1
    """, (week_ending.isoformat(), tier)).fetchone()
    
    if not latest_capture:
        return (True, "No prior capture found (first ingest)")
    
    stored_last_updated = datetime.fromisoformat(latest_capture[0])
    
    if source_last_updated > stored_last_updated:
        return (True, f"Source updated {source_last_updated} > stored {stored_last_updated}")
    else:
        return (False, f"Source unchanged since {stored_last_updated}")
```

**Metadata storage:**
```python
# When ingesting, store source metadata in manifest
metadata_json = {
    "source_last_updated": "2025-12-23T14:30:00Z",
    "source_url": "https://api.finra.org/data/otc/...",
    "content_hash": "a3f5b2c8...",
    "file_size_bytes": 1024567
}
```

### 2C. Detection Method 2: Content Hash (Fallback)

If source doesn't provide `lastUpdateDate`, compute hash of raw content:

```python
import hashlib

def compute_content_hash(content: bytes) -> str:
    """
    Compute SHA256 hash of raw content for change detection.
    
    Args:
        content: Raw file/API response bytes
    
    Returns:
        Hex digest (first 16 chars for brevity)
    """
    return hashlib.sha256(content).hexdigest()[:16]

def check_revision_needed_via_hash(
    week_ending: date,
    tier: str,
    content: bytes,
    db_connection
) -> tuple[bool, str]:
    """
    Compare content hash with latest capture.
    
    Returns:
        (needs_revision: bool, reason: str)
    """
    new_hash = compute_content_hash(content)
    
    latest_capture = db_connection.execute("""
        SELECT json_extract(metadata_json, '$.content_hash') as stored_hash
        FROM core_manifest
        WHERE domain = 'finra.otc_transparency'
          AND stage = 'RAW'
          AND json_extract(partition_key, '$.week_ending') = ?
          AND json_extract(partition_key, '$.tier') = ?
        ORDER BY captured_at DESC
        LIMIT 1
    """, (week_ending.isoformat(), tier)).fetchone()
    
    if not latest_capture:
        return (True, "No prior capture (first ingest)")
    
    stored_hash = latest_capture[0]
    
    if new_hash != stored_hash:
        return (True, f"Content changed (hash {new_hash[:8]} != {stored_hash[:8]})")
    else:
        return (False, f"Content identical (hash {new_hash[:8]})")
```

### 2D. Override: Force Restatement

```bash
# Ignore revision detection, always restate
python scripts/run_finra_weekly_schedule.py --lookback-weeks 6 --force

# Use cases:
# - Schema change requires reprocessing
# - Analytics bug fix requires recalculation
# - Compliance audit needs fresh snapshot
```

### 2E. Revision Detection Summary

**Decision tree:**

```
For each (week_ending, tier):
  1. Fetch source metadata/content
  2. If --force flag set:
       → INGEST with new capture_id
  3. Else if source provides lastUpdateDate:
       → Compare with stored metadata
       → SKIP if unchanged, INGEST if changed
  4. Else:
       → Compute content hash
       → Compare with stored hash
       → SKIP if identical, INGEST if changed
```

**Benefits:**
- **Efficiency:** Skip ~70-80% of weeks (typical FINRA revision rate)
- **Audit trail:** Decision logged to anomalies table (INFO severity)
- **Deterministic:** Same inputs → same decision (testable)

---

## 3. Capture ID Strategy

### 3A. Deterministic Capture ID Format

```python
def generate_capture_id(
    domain: str,
    week_ending: date,
    tier: str,
    run_date: date | None = None
) -> str:
    """
    Generate deterministic capture_id for partition.
    
    Format: {domain}:{tier}:{week_ending}:{YYYYMMDD}
    
    Args:
        domain: e.g., "finra.otc_transparency"
        week_ending: Friday date (e.g., 2025-12-26)
        tier: NMS_TIER_1, NMS_TIER_2, or OTC
        run_date: Date of ingestion run (default: today)
    
    Returns:
        Capture ID string
    """
    if run_date is None:
        run_date = date.today()
    
    # Format: finra.otc_transparency:NMS_TIER_1:2025-12-26:20251230
    return f"{domain}:{tier}:{week_ending.isoformat()}:{run_date.strftime('%Y%m%d')}"
```

**Examples:**

```python
# Monday, December 30, 2025 - process last 3 weeks
generate_capture_id("finra.otc_transparency", date(2025, 12, 26), "NMS_TIER_1", date(2025, 12, 30))
# → "finra.otc_transparency:NMS_TIER_1:2025-12-26:20251230"

generate_capture_id("finra.otc_transparency", date(2025, 12, 19), "OTC", date(2025, 12, 30))
# → "finra.otc_transparency:OTC:2025-12-19:20251230"

# Tuesday, December 31 - rerun for same weeks (different run_date)
generate_capture_id("finra.otc_transparency", date(2025, 12, 26), "NMS_TIER_1", date(2025, 12, 31))
# → "finra.otc_transparency:NMS_TIER_1:2025-12-26:20251231"  # NEW capture
```

### 3B. Replay vs Restatement Semantics

**Replay (same run_date):**
```bash
# Run scheduler Monday morning
python scripts/run_finra_weekly_schedule.py --lookback-weeks 4
# Generates capture IDs with run_date=2025-12-30

# Re-run same day (e.g., after fixing bug)
python scripts/run_finra_weekly_schedule.py --lookback-weeks 4
# Generates SAME capture IDs (safe idempotent replay)
# Existing data REPLACED (UPSERT on capture_id)
```

**Restatement (different run_date):**
```bash
# Run scheduler Monday morning
# capture_id = "....:20251230"

# Run scheduler Tuesday morning
# capture_id = "....:20251231"  # NEW snapshot
# Both captures coexist in database
# _latest views automatically point to Tuesday data
```

### 3C. As-of Queries (Historical Snapshots)

```sql
-- View data as it existed on Monday (2025-12-30 run)
SELECT *
FROM finra_otc_transparency_normalized
WHERE week_ending = '2025-12-26'
  AND tier = 'NMS_TIER_1'
  AND capture_id LIKE '%:20251230';

-- View latest data (whatever run_date was most recent)
SELECT *
FROM finra_otc_transparency_normalized_latest
WHERE week_ending = '2025-12-26'
  AND tier = 'NMS_TIER_1';
```

### 3D. Storage Implications

**Scenario:** 6-week lookback, daily runs, typical FINRA revision rate

```
Weeks in lookback: 6
Tiers: 3
Revision rate: ~20% (FINRA changes 1-2 weeks per run)
Runs per week: 7 (daily)

Partitions processed per run: 6 weeks × 3 tiers = 18
Partitions actually restated: 18 × 20% = ~3-4
New captures per week: 3-4 × 7 runs = 21-28

Storage per capture: ~2-5 MB (one tier, one week)
Storage per week: 21-28 captures × 3 MB avg = 60-84 MB
Storage per year: 60 MB × 52 weeks = 3.1 GB
```

**Acceptable:** Modern databases handle this easily. Optional retention policies can prune captures older than 2 years.

---

## 4. Order of Execution

### 4A. Pipeline Dependencies

FINRA OTC processing has natural dependencies:

```
RAW (ingest_week)
  ↓
NORMALIZED (normalize_week)
  ↓
CALC (compute_venue_volume, compute_venue_share, compute_hhi, etc.)
```

**Per-tier independence:**
- NMS_TIER_1, NMS_TIER_2, OTC can process in parallel
- No cross-tier dependencies

### 4B. Execution Strategy: Phased Approach

Process all partitions stage-by-stage to minimize orchestration complexity:

```python
# Phase 1: Ingest all changed weeks/tiers
for week_ending in target_weeks:
    for tier in tiers:
        if needs_revision(week_ending, tier):
            ingest_week(week_ending, tier)

# Phase 2: Normalize all newly ingested
for week_ending in target_weeks:
    for tier in tiers:
        if was_ingested_this_run(week_ending, tier):
            normalize_week(week_ending, tier)

# Phase 3: Compute analytics
for week_ending in target_weeks:
    # Calcs typically aggregate across tiers
    if all_tiers_normalized(week_ending):
        compute_venue_volume(week_ending)
        compute_venue_share(week_ending)
        compute_hhi(week_ending)
        compute_weekly_totals(week_ending)
```

**Benefits:**
- Simple to implement (no DAG engine needed)
- Clear progress tracking (100% ingest → 100% normalize → 100% calc)
- Bulk operations opportunities (e.g., batch inserts)

### 4C. Alternative: Per-Partition Chaining

For lower latency (each week available ASAP):

```python
for week_ending in target_weeks:
    for tier in tiers:
        if needs_revision(week_ending, tier):
            ingest_week(week_ending, tier)
            normalize_week(week_ending, tier)
    
    # After all tiers normalized
    if all_tiers_normalized(week_ending):
        compute_venue_volume(week_ending)
        compute_venue_share(week_ending)
        compute_hhi(week_ending)
```

**Trade-offs:**
- ✅ Lower latency (weeks available incrementally)
- ❌ More complex error handling
- ❌ Less efficient (can't batch operations)

**Recommendation:** Use phased approach unless latency requirements dictate otherwise.

### 4D. Manifest-Based Gating

Before running downstream stage, verify prerequisite completed:

```python
def check_stage_ready(week_ending: date, tier: str, stage: str, db_connection) -> bool:
    """
    Check if prerequisite stage completed successfully.
    
    Args:
        week_ending: Friday date
        tier: NMS_TIER_1, NMS_TIER_2, or OTC
        stage: "RAW", "NORMALIZED", etc.
    
    Returns:
        True if stage has data (row_count > 0)
    """
    result = db_connection.execute("""
        SELECT row_count
        FROM core_manifest
        WHERE domain = 'finra.otc_transparency'
          AND stage = ?
          AND json_extract(partition_key, '$.week_ending') = ?
          AND json_extract(partition_key, '$.tier') = ?
        ORDER BY captured_at DESC
        LIMIT 1
    """, (stage, week_ending.isoformat(), tier)).fetchone()
    
    return result is not None and result[0] > 0
```

**Usage:**

```python
# Before normalizing, ensure RAW exists
if check_stage_ready(week_ending, tier, "RAW", conn):
    normalize_week(week_ending, tier)
else:
    record_anomaly(
        domain="finra.otc_transparency",
        severity="ERROR",
        category="MISSING_DEPENDENCY",
        message=f"Cannot normalize {week_ending}/{tier}: RAW stage missing"
    )
```

---

## 5. Failure Behavior

### 5A. Failure Categories

**CRITICAL** - Abort entire scheduler run:
- Database connection failure
- Invalid configuration (malformed --weeks, bad tier names)
- Permission errors (can't write to DB)

**ERROR** - Skip partition, continue others:
- API fetch 404/503 (source unavailable)
- File parse error (corrupted CSV)
- Constraint violation (duplicate key, schema mismatch)

**WARN** - Record anomaly, continue processing:
- Partial venue coverage (only 45/150 venues)
- Missing tier (2/3 tiers present)
- Late-arriving data (past expected_delay_hours)

**INFO** - Log for audit trail:
- Revision skipped (unchanged content)
- Successful stage completion

### 5B. Partition-Level Isolation

**Key principle:** Failure in one partition shouldn't block others.

```python
# Pseudocode
successes = []
failures = []

for week_ending in target_weeks:
    for tier in tiers:
        try:
            if needs_revision(week_ending, tier):
                ingest_week(week_ending, tier)
                successes.append((week_ending, tier))
            else:
                # INFO anomaly: skipped unchanged
                pass
        except APIError as e:
            # ERROR anomaly: source unavailable
            record_anomaly(
                severity="ERROR",
                category="SOURCE_UNAVAILABLE",
                partition_key={"week_ending": week_ending, "tier": tier},
                message=f"API fetch failed: {e}",
                details_json={"status_code": e.status_code}
            )
            failures.append((week_ending, tier, str(e)))
        except Exception as e:
            # ERROR anomaly: unexpected failure
            record_anomaly(
                severity="ERROR",
                category="PIPELINE_ERROR",
                partition_key={"week_ending": week_ending, "tier": tier},
                message=f"Ingest failed: {e}"
            )
            failures.append((week_ending, tier, str(e)))
```

### 5C. Missing Tier Detection

After ingest phase, check expected vs actual tiers:

```python
def check_tier_completeness(week_ending: date, db_connection) -> bool:
    """
    Verify all 3 tiers present for a week.
    
    Returns:
        True if NMS_TIER_1, NMS_TIER_2, OTC all have RAW data
    """
    expected_tiers = {"NMS_TIER_1", "NMS_TIER_2", "OTC"}
    
    actual_tiers = set()
    rows = db_connection.execute("""
        SELECT DISTINCT json_extract(partition_key, '$.tier') as tier
        FROM core_manifest
        WHERE domain = 'finra.otc_transparency'
          AND stage = 'RAW'
          AND json_extract(partition_key, '$.week_ending') = ?
    """, (week_ending.isoformat(),)).fetchall()
    
    for row in rows:
        actual_tiers.add(row[0])
    
    missing = expected_tiers - actual_tiers
    
    if missing:
        record_anomaly(
            domain="finra.otc_transparency",
            severity="ERROR",
            category="INCOMPLETE_INPUT",
            partition_key={"week_ending": week_ending.isoformat()},
            message=f"Missing tiers: {', '.join(missing)}",
            details_json={"expected": list(expected_tiers), "actual": list(actual_tiers)}
        )
        return False
    
    return True
```

### 5D. Data Readiness Blocking

After processing week, evaluate readiness:

```python
def evaluate_readiness(week_ending: date, db_connection):
    """
    Determine if week is ready for trading/compliance use.
    
    Criteria:
    - all_partitions_present: 3/3 tiers
    - all_stages_complete: RAW, NORMALIZED, CALC
    - no_critical_anomalies: Zero unresolved CRITICAL
    """
    criteria = {
        "all_partitions_present": check_tier_completeness(week_ending, db_connection),
        "all_stages_complete": check_all_stages(week_ending, db_connection),
        "no_critical_anomalies": check_no_critical(week_ending, db_connection)
    }
    
    is_ready = all(criteria.values())
    
    db_connection.execute("""
        INSERT INTO core_data_readiness (
            domain, partition_key, is_ready, ready_for,
            all_partitions_present, all_stages_complete, no_critical_anomalies
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(domain, partition_key, ready_for) DO UPDATE SET
            is_ready = excluded.is_ready,
            all_partitions_present = excluded.all_partitions_present,
            all_stages_complete = excluded.all_stages_complete,
            no_critical_anomalies = excluded.no_critical_anomalies,
            updated_at = datetime('now')
    """, (
        "finra.otc_transparency",
        json.dumps({"week_ending": week_ending.isoformat()}),
        1 if is_ready else 0,
        "trading",
        1 if criteria["all_partitions_present"] else 0,
        1 if criteria["all_stages_complete"] else 0,
        1 if criteria["no_critical_anomalies"] else 0
    ))
```

### 5E. Exit Codes

```python
# Scheduler exit codes
EXIT_SUCCESS = 0         # All weeks processed successfully
EXIT_PARTIAL = 1         # Some partitions failed (ERROR anomalies)
EXIT_CRITICAL = 2        # Critical failure (DB down, config invalid)

# Example:
if critical_errors:
    sys.exit(EXIT_CRITICAL)
elif error_anomalies:
    sys.exit(EXIT_PARTIAL)
else:
    sys.exit(EXIT_SUCCESS)
```

**CI/CD integration:**
```bash
# Alerting based on exit code
if ! python scripts/run_finra_weekly_schedule.py --lookback-weeks 6; then
    EXITCODE=$?
    if [ $EXITCODE -eq 2 ]; then
        # Page on-call engineer
        send_alert "CRITICAL: FINRA scheduler failed"
    elif [ $EXITCODE -eq 1 ]; then
        # Email data ops team
        send_email "WARN: FINRA scheduler partial failure"
    fi
fi
```

---

## 6. Summary: Scheduler Behavior

### 6A. Typical Run (Monday morning, 10:30 AM)

```bash
python scripts/run_finra_weekly_schedule.py \
  --lookback-weeks 6 \
  --source api \
  --mode run

# Output:
# [INFO] Target weeks: 2026-01-03, 2025-12-27, 2025-12-20, 2025-12-13, 2025-12-06, 2025-11-29
# [INFO] Phase 1: Ingestion
# [INFO]   2026-01-03 / NMS_TIER_1: Fetching from API...
# [INFO]   2026-01-03 / NMS_TIER_1: Revision needed (source updated 2026-01-04 > stored 2025-12-30)
# [INFO]   2026-01-03 / NMS_TIER_1: ✓ Ingested 48,765 rows (capture: ...20260104)
# [INFO]   2026-01-03 / NMS_TIER_2: Content unchanged (hash a3f5b2c8), skipping
# [INFO]   2026-01-03 / OTC: ✓ Ingested 12,543 rows (capture: ...20260104)
# [INFO]   2025-12-27 / NMS_TIER_1: Content unchanged, skipping
# [INFO]   2025-12-27 / NMS_TIER_2: Content unchanged, skipping
# [INFO]   2025-12-27 / OTC: Content unchanged, skipping
# ... (repeat for other weeks)
# [INFO] Phase 2: Normalization
# [INFO]   2026-01-03 / NMS_TIER_1: ✓ Normalized 48,765 rows
# [INFO]   2026-01-03 / OTC: ✓ Normalized 12,543 rows
# [INFO] Phase 3: Analytics
# [INFO]   2026-01-03: ✓ Computed venue_volume (98 venues)
# [INFO]   2026-01-03: ✓ Computed venue_share (sum=1.0)
# [INFO]   2026-01-03: ✓ Computed HHI (NMS_TIER_1: 0.156)
# [INFO] Readiness Evaluation:
# [INFO]   2026-01-03: ✓ Ready for trading
# [INFO]   2025-12-27: ✓ Already ready (no changes)
# [SUMMARY]
# Weeks processed: 6
# Partitions ingested: 2 / 18 (revision detected)
# Partitions skipped: 16 / 18 (unchanged)
# Failures: 0
# Anomalies: 0 CRITICAL, 0 ERROR, 0 WARN, 16 INFO
# Exit code: 0
```

### 6B. Typical Run with Failure (API down for OTC tier)

```bash
# Same command
# Output:
# [INFO] Phase 1: Ingestion
# [INFO]   2026-01-03 / NMS_TIER_1: ✓ Ingested 48,765 rows
# [INFO]   2026-01-03 / NMS_TIER_2: ✓ Ingested 15,234 rows
# [ERROR]  2026-01-03 / OTC: API fetch failed (HTTP 503)
# [ERROR]  Anomaly recorded: SOURCE_UNAVAILABLE
# [INFO]   2025-12-27 / NMS_TIER_1: Content unchanged, skipping
# ... (continue other weeks)
# [INFO] Phase 2: Normalization
# [INFO]   2026-01-03 / NMS_TIER_1: ✓ Normalized
# [INFO]   2026-01-03 / NMS_TIER_2: ✓ Normalized
# [WARN]   2026-01-03: Missing tier OTC, skipping cross-tier analytics
# [INFO] Readiness Evaluation:
# [ERROR]  2026-01-03: NOT READY (all_partitions_present=0, blocking_issues: ["Missing tier: OTC"])
# [SUMMARY]
# Weeks processed: 6
# Partitions ingested: 2 / 18
# Partitions failed: 1 / 18
# Anomalies: 0 CRITICAL, 1 ERROR, 1 WARN, 15 INFO
# Exit code: 1 (partial failure)
```

### 6C. Dry-Run Mode

```bash
python scripts/run_finra_weekly_schedule.py \
  --lookback-weeks 6 \
  --mode dry-run

# Output:
# [DRY-RUN] Would process weeks: 2026-01-03, 2025-12-27, ...
# [DRY-RUN] Would ingest 2026-01-03 / NMS_TIER_1 (source updated)
# [DRY-RUN] Would skip 2025-12-27 / NMS_TIER_1 (unchanged)
# [DRY-RUN] Summary: 2 ingests, 16 skips
# No database writes performed.
# Exit code: 0
```

---

## 7. Implementation Checklist

- [ ] Implement week calculation (`calculate_target_weeks`)
- [ ] Implement revision detection (metadata + hash)
- [ ] Implement capture_id generation
- [ ] Implement phased execution (ingest → normalize → calc)
- [ ] Implement partition-level error handling
- [ ] Implement tier completeness checks
- [ ] Implement readiness evaluation
- [ ] Add CLI argument parsing
- [ ] Add dry-run mode
- [ ] Add summary output
- [ ] Write unit tests (week calc, revision detection, capture_id)
- [ ] Write integration tests (mocked API, multiple runs)
- [ ] Document cron/K8s/OpenShift examples

---

## 8. Next Steps

1. **Implement scheduler script** (`scripts/run_finra_weekly_schedule.py`)
2. **Add helper utilities** (`market_spine/app/scheduler.py`)
3. **Write comprehensive tests** (`tests/test_multi_week_scheduler.py`)
4. **Update operational docs** (cron/K8s examples in `scheduling.md`)
5. **Deploy to production** with monitoring/alerting

See [Scheduling Guide](scheduling.md) for cron/K8s deployment examples.
