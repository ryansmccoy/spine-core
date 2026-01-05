# Page Spec: Quality & Anomalies

> Part of: [Dashboard Design](00-index.md)

## Page Identity

| Attribute | Value |
|-----------|-------|
| Route | `/dashboard/quality` |
| Primary Question | What data quality issues exist? |
| Secondary Questions | How severe? What's affected? Is it acknowledged? |
| Primary Persona | Quant / Analyst, Platform Operator |
| Tier Required | Intermediate |

---

## Primary Question

> **What data quality issues exist?**

Users need to:
1. See all detected anomalies
2. Understand severity and impact
3. Acknowledge known issues
4. Track resolution

---

## Core Concept: Anomaly Types

| Type | Icon | Description | Example |
|------|------|-------------|---------|
| **Volume Spike** | 📈 | Unusual volume vs historical | AAPL volume 10x normal |
| **Volume Drop** | 📉 | Unexpected low volume | Market holiday not detected |
| **Missing Data** | ⬜ | Expected data not present | Symbol disappeared |
| **Schema Drift** | ⚙️ | Source format changed | New column added |
| **Value Outlier** | ⚠️ | Value outside expected range | Price = $0.00 |
| **Duplicate** | 📋 | Same data ingested twice | Week re-published |
| **Late Arrival** | ⏰ | Data arrived after SLA | Friday data on Monday |

---

## Severity Levels

| Level | Badge | Impact | Response |
|-------|-------|--------|----------|
| 🔴 **Critical** | `CRITICAL` | Data unusable for production | Immediate investigation |
| 🟠 **High** | `HIGH` | Data may be incorrect | Investigate same day |
| 🟡 **Medium** | `MEDIUM` | Minor impact, needs review | Investigate this week |
| ⚪ **Low** | `LOW` | Informational | Review when convenient |

---

## Page Layout

```
┌─────────────────────────────────────────────────────────────────┐
│  Data Quality                                [Time: Last 7d ▾]  │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  SUMMARY                                                         │
│  ═══════                                                         │
│                                                                  │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐        │
│  │ 🔴 2     │  │ 🟠 5     │  │ 🟡 12    │  │ ⚪ 8     │        │
│  │ Critical │  │ High     │  │ Medium   │  │ Low      │        │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘        │
│                                                                  │
│  2 critical issues require immediate attention                  │
│                                                                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ANOMALIES                                                       │
│  ═════════                                                       │
│                                                                  │
│  Filters: [All Severities ▾] [All Types ▾] [All Tiers ▾]       │
│           [Unacknowledged ▾]                                    │
│                                                                  │
│  SEV │ TYPE        │ TIER │ WEEK     │ DETAILS           │ ACK │
│  ────────────────────────────────────────────────────────────── │
│  🔴  │ Missing     │ OTC  │ 12-22    │ 15 symbols absent │ [ ] │
│  🔴  │ Vol Spike   │ NMS1 │ 12-22    │ TSLA 50x normal   │ [ ] │
│  🟠  │ Late Arrival│ OTC  │ 12-15    │ 18h past SLA      │ [✓] │
│  🟠  │ Vol Drop    │ NMS2 │ 12-22    │ Overall -40%      │ [ ] │
│  🟡  │ Outlier     │ OTC  │ 12-22    │ XYZ price=0.001   │ [ ] │
│                                                                  │
│                                     [Showing 5 of 27] [Load ▾]  │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Anomaly Detail View

Clicking an anomaly row expands or opens detail:

```
┌─────────────────────────────────────────────────────────────────┐
│  Anomaly: Missing Symbols                                        │
│  ═══════════════════════════════════════════════════════════════│
│                                                                  │
│  Severity: 🔴 CRITICAL                                          │
│  Type: Missing Data                                              │
│  Detected: 2025-01-04 08:30:00 UTC                              │
│                                                                  │
│  AFFECTED DATA                                                   │
│  ─────────────                                                   │
│  Tier: OTC                                                       │
│  Week: 2025-12-22                                               │
│  Symbols: ACME, BETA, CORP, ... (15 total)                      │
│                                                                  │
│  DETECTION RULE                                                  │
│  ──────────────                                                  │
│  Rule: symbol_continuity_check                                  │
│  Condition: Symbols present in 6/6 prior weeks now absent       │
│  Threshold: Any symbol missing = anomaly                        │
│                                                                  │
│  CONTEXT                                                         │
│  ───────                                                         │
│  These 15 symbols were present in all prior weeks but           │
│  are not present in the 2025-12-22 data.                        │
│                                                                  │
│  Possible causes:                                                │
│  • Symbols delisted                                              │
│  • Source data error                                             │
│  • Ingestion filtering issue                                     │
│                                                                  │
│  HISTORY                                                         │
│  ───────                                                         │
│  Created: 2025-01-04 08:30                                      │
│  Last updated: 2025-01-04 08:30                                 │
│  Acknowledged: No                                                │
│                                                                  │
│  [Acknowledge]  [Create Ticket]  [View Affected Data]           │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Actions

### Acknowledge Anomaly

Mark an anomaly as reviewed:

```
┌───────────────────────────────────────────┐
│  Acknowledge Anomaly                      │
│                                           │
│  I have reviewed this anomaly and:        │
│                                           │
│  ○ It is a known issue, no action needed  │
│  ○ It will be fixed in next ingest        │
│  ○ It is not actually an issue            │
│  ○ Other: [_____________________]         │
│                                           │
│  Note (optional):                         │
│  [_____________________________]          │
│  [_____________________________]          │
│                                           │
│            [Cancel]  [Acknowledge]        │
└───────────────────────────────────────────┘
```

### Bulk Acknowledge

For multiple similar anomalies:

```
┌───────────────────────────────────────────┐
│  Bulk Acknowledge                         │
│                                           │
│  Acknowledge 8 selected anomalies?        │
│                                           │
│  Reason: [_____________________]          │
│                                           │
│  ⚠ This includes 1 critical anomaly      │
│                                           │
│            [Cancel]  [Acknowledge All]    │
└───────────────────────────────────────────┘
```

---

## Detection Rules Display

Show users what rules are active:

```
┌─────────────────────────────────────────────────────────────────┐
│  ACTIVE DETECTION RULES                                         │
│  ══════════════════════                                         │
│                                                                  │
│  Rule                    │ Tier │ Threshold        │ Last Run  │
│  ─────────────────────────────────────────────────────────────  │
│  volume_zscore_check     │ All  │ z > 3.0          │ 08:15     │
│  symbol_continuity_check │ All  │ Any missing      │ 08:15     │
│  price_range_check       │ All  │ Outside 1Y range │ 08:15     │
│  late_arrival_check      │ All  │ > 24h after SLA  │ 08:00     │
│  duplicate_detection     │ All  │ Same capture_id  │ 08:15     │
│                                                                  │
│  [View Rule Details]  [Configure Rules ⚙️]                      │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Filters

| Filter | Options | Default |
|--------|---------|---------|
| Severity | All, Critical, High, Medium, Low | All |
| Type | All, Volume, Missing, Schema, Outlier, etc. | All |
| Tier | All, OTC, NMS_TIER_1, NMS_TIER_2 | All |
| Status | All, Unacknowledged, Acknowledged | Unacknowledged |
| Time | Last 24h, 7d, 30d, Custom | Last 7d |

---

## Failure States

### No Anomalies

```
┌─────────────────────────────────────┐
│  ✓ No Anomalies Detected            │
│                                     │
│  No data quality issues have been   │
│  detected in the selected time      │
│  range.                             │
│                                     │
│  Last check: 5 minutes ago          │
│                                     │
│  [View Historical Anomalies]        │
└─────────────────────────────────────┘
```

### Quality Service Unavailable

```
┌─────────────────────────────────────┐
│  ⚠️ Quality Check Unavailable      │
│                                     │
│  Unable to retrieve anomaly data.   │
│  This does not mean data is good    │
│  or bad.                            │
│                                     │
│  [Retry]                            │
└─────────────────────────────────────┘
```

---

## Integration with Other Pages

### From Data Readiness

Link: "2 anomalies" → Quality page filtered to that week/tier

### To Data Assets

Link: "View Affected Data" → Assets page filtered to affected symbols

### To Executions

Link: "View Ingest Run" → Execution that produced this data

---

## Tier Behavior

### Basic Tier

This page is NOT available in Basic tier.

Show:
```
┌─────────────────────────────────────┐
│  📊 Data Quality                    │
│                                     │
│  Automated quality detection is     │
│  available in the Intermediate      │
│  tier.                              │
│                                     │
│  Basic tier includes:               │
│  • Data ingestion                   │
│  • Manual inspection                │
│                                     │
│  [Learn about tiers]                │
└─────────────────────────────────────┘
```

### Intermediate Tier

Full anomaly detection and management:
- All anomaly types
- Acknowledge workflow
- Detection rule visibility
- Basic thresholds

### Advanced Tier

Additional features:
- Custom detection rules
- ML-based anomaly detection
- Alerting integration
- Anomaly trend analysis
- Auto-acknowledge rules
