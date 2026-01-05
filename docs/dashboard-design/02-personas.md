# Operator Personas

> Part of: [Dashboard Design](00-index.md)

## Persona 1: Platform Operator (SRE / Data Engineer)

### Role Description

The Platform Operator is responsible for keeping the data platform running. They manage pipeline schedules, debug failures, and ensure data freshness SLAs are met.

### Decisions They Make

| Decision | Frequency | Latency Requirement |
|----------|-----------|---------------------|
| Should I escalate this failure? | Per incident | < 30 seconds to assess |
| Is this a transient or systemic issue? | Daily | < 2 minutes to determine |
| Can I retry this safely? | Per failure | < 1 minute to evaluate |
| Do I need to backfill? | Weekly | < 5 minutes to scope |
| Is it safe to deploy changes? | Per deploy | < 2 minutes to validate |

### Information Needed Immediately

1. **System health summary** - All green or where are the reds?
2. **Recent failures** - What failed in the last hour/day?
3. **Execution context** - Why did it fail? (error, logs, params)
4. **Dependency state** - What else is affected?
5. **Historical pattern** - Is this the first time or recurring?

### Acceptable Latency

| Information Type | Max Latency |
|-----------------|-------------|
| Current health status | < 5 seconds |
| Recent failure list | < 10 seconds |
| Execution logs | < 30 seconds |
| Historical trends | < 60 seconds |

### Mistakes UI Must Prevent

| Mistake | Prevention |
|---------|------------|
| Retrying a pipeline that's already running | Disable retry button when running |
| Running backfill with wrong date range | Validate params, show preview |
| Missing a failure because it scrolled off | Pin critical failures, send alerts |
| Misinterpreting success (stale data) | Show data freshness, not just run status |
| Deploying during active runs | Show active execution count prominently |

---

## Persona 2: Quant / Analyst

### Role Description

The Quant uses Market Spine data for research and trading decisions. They need to trust that data is complete, correct, and reflects the right point in time.

### Decisions They Make

| Decision | Frequency | Latency Requirement |
|----------|-----------|---------------------|
| Is this data safe to use for research? | Per analysis | < 30 seconds |
| Which symbols have complete data? | Per analysis | < 1 minute |
| What's the latest available data? | Daily | < 10 seconds |
| Did data change since I last ran my model? | Per model run | < 1 minute |
| Why do my numbers not match yesterday? | Per discrepancy | < 5 minutes |

### Information Needed Immediately

1. **Data freshness** - What's the latest available week?
2. **Completeness** - Are all expected symbols present?
3. **Certification status** - Is data certified or preliminary?
4. **Revision history** - Did past data change?
5. **Anomaly flags** - Are there known data quality issues?

### Acceptable Latency

| Information Type | Max Latency |
|-----------------|-------------|
| Current data availability | < 5 seconds |
| Symbol coverage check | < 15 seconds |
| Revision/change detection | < 30 seconds |
| Anomaly details | < 30 seconds |

### Mistakes UI Must Prevent

| Mistake | Prevention |
|---------|------------|
| Using preliminary data as final | Clear "PRELIMINARY" badge |
| Missing data gaps | Show completeness indicators |
| Using stale derived analytics | Show last compute timestamp |
| Ignoring known anomalies | Surface anomalies in data view |
| Comparing incompatible captures | Show capture_id in context |

---

## Persona 3: Compliance / Audit

### Role Description

Compliance needs to verify data provenance, ensure proper handling of market data, and produce audit trails for regulatory requirements.

### Decisions They Make

| Decision | Frequency | Latency Requirement |
|----------|-----------|---------------------|
| Can I prove when data was ingested? | Per audit | < 5 minutes |
| What was the state at time T? | Per investigation | < 10 minutes |
| Who triggered this execution? | Per incident | < 2 minutes |
| Is data retention policy enforced? | Monthly | < 30 minutes |
| Are we using licensed data correctly? | Per source | < 10 minutes |

### Information Needed Immediately

1. **Execution history** - Full audit trail of runs
2. **Capture provenance** - Source → ingested → normalized → derived
3. **Timestamp accuracy** - When exactly did events occur?
4. **Parameter history** - What inputs were used?
5. **Data lineage** - Where did this number come from?

### Acceptable Latency

| Information Type | Max Latency |
|-----------------|-------------|
| Execution audit log | < 30 seconds |
| Capture lineage | < 60 seconds |
| Historical state reconstruction | < 5 minutes |
| Full audit report generation | < 10 minutes |

### Mistakes UI Must Prevent

| Mistake | Prevention |
|---------|------------|
| Incomplete audit trail | Log all executions, never delete |
| Ambiguous timestamps | Always show timezone, use ISO 8601 |
| Missing execution context | Capture all params and environment |
| Losing deleted data trace | Soft delete with audit log |
| Confusing captures | Clear capture_id display and lineage |

---

## Persona Priority Matrix

| Feature | Operator | Quant | Compliance |
|---------|----------|-------|------------|
| Real-time health | ★★★ | ★ | ★ |
| Failure debugging | ★★★ | ★ | ★★ |
| Data freshness | ★★ | ★★★ | ★ |
| Anomaly detection | ★★ | ★★★ | ★ |
| Execution history | ★★ | ★ | ★★★ |
| Data lineage | ★ | ★★ | ★★★ |
| Scheduling | ★★★ | ★ | ★ |
| Audit export | ★ | ★ | ★★★ |

**Priority 1**: Platform Operator (most frequent user)  
**Priority 2**: Quant/Analyst (primary data consumer)  
**Priority 3**: Compliance (periodic but critical use)

---

## User Journey: "Morning Check" by Persona

### Operator Morning Check (2 minutes)

1. Open Overview → See all green? Done.
2. If yellow/red → Click to see failures
3. For each failure → Assess: retry or escalate?
4. Check scheduled runs → Any missed?
5. Verify data freshness → Any stale tiers?

### Quant Morning Check (1 minute)

1. Open Data Readiness → Latest week available?
2. Check tier completeness → All symbols present?
3. Check anomaly count → Any new issues?
4. If using derived data → Verify last compute time
5. Proceed to analysis

### Compliance Weekly Check (10 minutes)

1. Open Executions → Filter last 7 days
2. Verify all scheduled runs executed
3. Check for any manual overrides
4. Export execution log to audit file
5. Verify data retention compliance
