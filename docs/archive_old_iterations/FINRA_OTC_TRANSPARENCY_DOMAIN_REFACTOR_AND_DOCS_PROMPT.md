# FINRA OTC Transparency Domain Documentation & Naming Refactor  
**Implementation Prompt + Design Notes for Claude**

This document is a **paste‑ready prompt** you can give to Claude to:
1. Properly document the FINRA OTC Transparency dataset
2. Rename/re‑nest the current “otc” domain under a clearer FINRA‑scoped namespace
3. Prepare the codebase and docs for **additional FINRA market transparency datasets** in the future

It also includes **additional architectural suggestions** to improve clarity, discoverability, and long‑term scalability.

---

## 1) High‑level intent

We want to:
- Make it *explicit* that the current OTC data is **FINRA OTC Transparency data**
- Nest it under a broader **FINRA data namespace**
- Document the dataset thoroughly so future contributors understand:
  - what the data is
  - where it comes from
  - how often it updates
  - how we ingest, normalize, and query it
  - how it fits into the Spine model (clocks, captures, pipelines)

This should feel like **institutional‑grade documentation**, not just code comments.

---

## 2) Canonical naming decision (IMPORTANT)

### Rename the current OTC domain to a FINRA‑scoped name

**Current (too vague):**
```
otc
```

**Proposed (explicit and future‑proof):**
```
finra.otc_transparency
```

or filesystem‑safe equivalents such as:
```
finra_otc_transparency
```

or (if cadence matters in naming):
```
finra.otc_transparency.weekly
```

### Why this matters
FINRA publishes **many different datasets**, and “OTC” alone is ambiguous.  
We expect to add more FINRA sources over time, such as:

- TRACE (fixed income)
- TRF (equity trade reporting)
- SLATE (securities lending)
- ORF
- ADF
- PDM
- New Issue Management
- Uniform Practice Code (UPC)

Nesting under `finra.*` ensures:
- clean mental model
- predictable folder structure
- no future renames when new FINRA datasets are added

---

## 3) Required refactor scope

Claude should implement the following:

### A) Rename domain code and paths
- Rename domain folders, registries, and identifiers:
  - `otc` → `finra_otc_transparency`
- Update:
  - pipeline names
  - registry keys
  - CLI names
  - docs references
  - tests and fixtures
- Preserve behavior; this is a **semantic rename**, not a rewrite

Example pipeline names after rename:
```
finra.otc_transparency.ingest_week
finra.otc_transparency.normalize_week
finra.otc_transparency.aggregate_week
```

---

## 4) Domain‑level documentation (REQUIRED)

Create a **README.md inside the domain folder**, e.g.:

```
packages/
  spine-domains-finra-otc-transparency/
    README.md
    docs/
      overview.md
      data_dictionary.md
      pipelines.md
      timing_and_clocks.md
```

### 4.1 Domain README.md (overview)

This file should explain:

- What FINRA OTC Transparency data is
- Why it exists
- What questions it answers
- How it fits into Spine

Include:
- Link to official FINRA page  
  https://www.finra.org/filing-reporting/otc-transparency
- Plain‑English explanation of:
  - ATS vs Non‑ATS
  - de minimis aggregation
  - delayed publication

---

### 4.2 Overview doc (`overview.md`)

Include:
- Description from FINRA (paraphrased, not copy‑paste)
- Explanation of **who reports the data**
- Explanation of **what is aggregated**
- Publication cadence (weekly, Monday publication)
- Regulatory basis:
  - FINRA Rules 6110 and 6610
  - Regulatory Notices 15‑48, 16‑14, 19‑29

---

### 4.3 Data dictionary (`data_dictionary.md`)

Document each important field:
- tierDescription
- issueSymbolIdentifier
- issueName
- marketParticipantName
- MPID
- totalWeeklyShareQuantity
- totalWeeklyTradeCount
- lastUpdateDate

For each field:
- definition
- source
- how we store it internally
- how/if it is transformed

---

### 4.4 Timing & clocks (`timing_and_clocks.md`)

Explain clearly:

- FINRA publishes files on **Monday**
- Data represents the **prior trading week**
- `lastUpdateDate` ≠ business time
- How `week_ending` is derived (Friday of prior week)
- How holidays affect this (not yet handled in Basic)

Include example table:

| FINRA File Date (Monday) | Derived Week Ending |
|--------------------------|-------------------|
| 2025‑12‑15 | 2025‑12‑12 |
| 2025‑12‑22 | 2025‑12‑19 |
| 2025‑12‑29 | 2025‑12‑26 |

Tie explicitly to the **3‑clock Spine model**.

---

### 4.5 Pipelines doc (`pipelines.md`)

For each pipeline:
- ingest_week
- normalize_week
- aggregate_week
- compute_rolling (if applicable)

Document:
- inputs
- outputs
- tables touched
- invariants
- failure modes
- example CLI commands

---

## 5) Additional architectural improvements (optional but recommended)

Claude should consider and, if appropriate, implement:

### A) FINRA super‑namespace
Create a top‑level FINRA namespace to make future expansion obvious:

```
finra/
  otc_transparency/
  trace/
  trf/
  slate/
```

Even if only OTC exists today, this sets expectations.

---

### B) Shared FINRA utilities
If useful, extract:
- FINRA‑specific date logic
- FINRA publication cadence helpers
into a small shared module for future datasets.

---

### C) Cross‑dataset alignment notes
In docs, briefly note how FINRA OTC Transparency could later be joined with:
- TRACE (bonds)
- Short interest
- Price/volume data

No implementation required — documentation only.

---

## 6) Required outputs from Claude

Claude must produce:

1. **Renaming plan**
   - Old → new names
   - File paths
   - Pipeline identifiers
2. **Unified diffs** for the rename
3. **Domain README.md**
4. **Supporting domain docs**
5. **Updated references across repo**
6. **Verification commands**
   - `spine list`
   - `spine run finra.otc_transparency.ingest_week ...`

---

## 7) Guiding principles (do not violate)

- Be explicit rather than short
- Optimize for future datasets
- Avoid ambiguous names
- Prefer discoverability over brevity
- Treat data documentation as first‑class code

---

## 8) Reminder

This refactor is foundational.

Once this is done:
- FINRA becomes a clean data family
- Adding TRACE / TRF / SLATE later is obvious
- The system reads like a real market‑data platform

Implement carefully and document thoroughly.
