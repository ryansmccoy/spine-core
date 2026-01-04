# Architecture Change Spike Prompts — Market Spine

These prompts are designed to **stress‑test the architecture** of Market Spine by deliberately introducing plausible changes and observing where friction, coupling, or rigidity appears.

Each prompt follows the same philosophy:

* Treat the change as an **architecture fitness test**
* Prefer **analysis + minimal refactor + validation**
* Optimize for learning, not feature completeness

You can paste any of these prompts directly into Claude (or another LLM) and run them independently.

---

## Prompt 1 — Ingestion Change Spike (File → API)

**Primary goal:** Evaluate how easy it is to change *how data enters the system*.

```markdown
# Market Spine — Ingestion Change Spike (File → FINRA OTC API)

Goal: Evaluate how change‑friendly the ingestion layer is by adding a second ingestion mechanism for FINRA OTC data.

Current state:
- Ingest pipelines read from local files (CSV)

Target change:
- Add support for ingesting data from the FINRA OTC API
- Preserve existing file‑based ingestion unchanged

This is NOT a feature request. It is an architecture changeability experiment.

## Constraints
- No DI containers or frameworks
- spine‑core must remain generic (no FINRA logic)
- Keep sync execution for Basic tier
- Pydantic remains API‑boundary only
- Prefer minimal, mechanical refactors

---

## Part 1 — Architecture Analysis
1. Trace the ingest pipeline call graph end‑to‑end.
2. Identify every point where **file‑specific assumptions** exist:
   - pipeline specs
   - parameter handling
   - connector/parsing
   - path resolution
3. Classify coupling as:
   - Acceptable
   - Accidental
   - Harmful to extensibility

Output a short report:
- Where ingestion is tightly coupled
- Why those couplings make API ingestion hard
- Where a clean ingestion seam should exist

---

## Part 2 — Minimal Refactor Design
Design the smallest abstraction that allows:
- file ingestion
- API ingestion
- future DB ingestion

Rules:
- Pipelines must not care where records come from
- Normalization and calculations operate on records, not filenames
- The abstraction should live in the domain layer

Provide:
- Proposed interface / protocol
- Updated pipeline flow diagram
- File tree diff

---

## Part 3 — Implementation
1. Implement API ingestion using mocked or recorded responses (offline‑safe)
2. Preserve file ingestion behavior exactly
3. Add unit tests for both ingestion paths

---

## Part 4 — Validation
Update or add a smoke test that:
- runs file ingestion
- runs API ingestion
- proves both reach normalization successfully

Provide commands to run locally.
```

---

## Prompt 2 — Storage Backend Swap (SQLite → Postgres)

**Primary goal:** Test how well storage concerns are isolated.

```markdown
# Market Spine — Storage Backend Change Spike (SQLite → Postgres)

Goal: Evaluate how tightly persistence logic is coupled to SQLite.

Current state:
- SQLite used via spine.framework.db

Target change:
- Enable Postgres as an alternative backend
- SQLite must continue to work

## Analysis Tasks
1. Identify where SQLite assumptions exist:
   - SQL dialect
   - connection lifecycle
   - transactions
   - pragmas / WAL
2. Identify which assumptions belong in:
   - framework
   - domain
   - app

## Design Task
Propose the minimal abstraction needed to support multiple backends without rewriting pipelines.

## Implementation Task
- Implement Postgres backend behind the same interface
- Add a backend selection mechanism (env or config)
- Add a smoke test that runs against both backends (can be sequential)

Focus on learning where coupling exists — not on performance tuning.
```

---

## Prompt 3 — New Domain Spike (Minimal Second Domain)

**Primary goal:** Test domain plugin boundaries and onboarding cost.

```markdown
# Market Spine — New Domain Change Spike (Toy Domain)

Goal: Evaluate how easy it is to add a second domain.

Create a minimal new domain (e.g., `spine.domains.demo.hello_world`) with:
- 1 ingest pipeline
- 1 normalize pipeline
- 1 query path

Constraints:
- No copying large chunks of FINRA logic
- Follow documented domain structure

Tasks:
1. Identify boilerplate required to add a domain
2. Identify framework assumptions that favor FINRA implicitly
3. Implement the domain end‑to‑end
4. Add one CLI command and one API endpoint

Deliverables:
- File tree diff
- Lines of code added
- Subjective friction report
```

---

## Prompt 4 — Calculation Versioning Spike (v1 → v2)

**Primary goal:** Test evolution of business logic over time.

```markdown
# Market Spine — Calculation Versioning Spike

Goal: Evaluate how well the system supports evolving calculations.

Current state:
- Single calculation implementation per metric

Target change:
- Add a v2 version of an existing calculation
- Preserve v1 for historical queries

Tasks:
1. Identify where calculations are registered
2. Identify how versions are named, stored, and queried
3. Propose a versioning convention
4. Implement v2 with minimal duplication
5. Demonstrate querying v1 vs v2

Focus on schema evolution, idempotency, and replay safety.
```

---

## Prompt 5 — Input Format Spike (CSV → JSON / Gzip)

**Primary goal:** Test parsing and connector isolation.

```markdown
# Market Spine — Input Format Change Spike (CSV → JSON / Gzip)

Goal: Evaluate how flexible the parsing layer is.

Target change:
- Support a second input format (JSON lines or gzip CSV)
- No pipeline logic should change

Tasks:
1. Identify where parsing assumptions exist
2. Propose a connector abstraction if needed
3. Implement second format support
4. Add tests proving both formats normalize identically

Deliverables:
- Parsing seam documentation
- Test fixtures
```

---

## Prompt 6 — Temporal Replay Spike (Capture‑Time Variants)

**Primary goal:** Validate the three‑clock temporal model.

```markdown
# Market Spine — Temporal Replay Change Spike

Goal: Validate the system’s ability to support multiple captures for the same business time.

Tasks:
1. Trace how week_ending, source_last_update_date, and captured_at are stored
2. Identify uniqueness constraints
3. Attempt to re‑ingest the same week with a new capture_id
4. Verify both versions coexist
5. Demonstrate querying "latest" vs "as‑of capture"

Focus on temporal correctness, not UI polish.
```

---

## How to Use These Prompts

* Run **one spike at a time**
* Commit changes on a short‑lived branch
* Measure:

  * files touched
  * layers impacted
  * abstractions added
  * tests required
* Decide whether to keep, revert, or generalize the refactor

These are **architecture fitness tests**, not permanent feature commitments.

---

## Recommendation

Start with **Prompt 1 (Ingestion Change Spike)** — it is the highest signal‑to‑noise test of modularity in Market Spine.
