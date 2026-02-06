# Market Spine — Ingestion Change Spike (File → FINRA OTC API)

Goal: Add a *second ingestion path* for the FINRA OTC Transparency domain (fetch via FINRA OTC API), specifically to evaluate how modular/change-friendly the architecture is.

This is NOT just “implement API ingest.” This is an architecture changeability spike:
- Identify coupling around ingestion
- Propose the smallest refactor that creates a clean “ingestion seam”
- Implement API ingest as a validation of that seam
- Keep everything aligned with existing layering rules

## Constraints
- Do NOT add DI containers or large frameworks.
- Keep spine-core generic (no FINRA logic).
- Keep sync execution for Basic tier.
- Keep Pydantic only at API boundary.
- Prefer minimal, mechanical refactors that reduce coupling.
- Ensure existing file-based ingest continues to work unchanged.

---

## Part 1 — Analysis: Where is ingestion coupled today?
1) Trace the call graph for the ingest pipeline(s) in `spine.domains.finra.otc_transparency`.
2) Identify every point where “file-ness” leaks into:
   - pipeline params and spec
   - connector/parsing
   - path resolution (app/services/ingest.py)
   - tests/fixtures
3) Produce a short report with:
   - coupling points (with file paths / symbols)
   - why each coupling point makes API ingest hard
   - recommended seam location(s)
   - a “minimal refactor plan” (ordered steps, small commits)

Deliverable: a Markdown report `docs/architecture/ingestion-seam-spike.md`.

---

## Part 2 — Design: Introduce a generic ingestion interface (smallest viable)
Implement a domain-level “ingestion port” (NOT in spine-core) such that pipelines can request records without caring about source type.

Suggested target design (adjust if needed):
- Domain defines:
  - `IngestSource` protocol/interface (e.g., `fetch_records(params) -> Iterable[RawRecord]`)
  - `FileIngestSource`
  - `FinraApiIngestSource`
- Pipelines accept a param like `source=` or `ingest_mode=` and delegate to the chosen source.
- `IngestResolver` (app/services) can derive defaults (file path for file mode, base URL for api mode).
- Connector/normalizer should operate on bytes/rows/records, not “a filename”.

Make the seam testable:
- unit tests for each source
- an integration test that runs ingest using both sources against fixtures/mocked HTTP

---

## Part 3 — Implement: FINRA OTC API ingestion
Add API ingestion in a way that is testable and doesn’t require live network access:
- Use `httpx` or `requests` (pick what is already in the project; prefer stdlib if possible)
- Implement a thin API client in the domain (or a finra-specific submodule inside domain)
- For tests:
  - use mocked HTTP responses (e.g., responses, respx, or a lightweight stub server)
  - add a recorded response fixture (JSON) under tests/fixtures
  - ensure tests pass offline

---

## Part 4 — Smoke test update
Update or add a smoke test script that can run:
- file ingest path (existing)
- api ingest path (against mocked/stubbed local fixtures)

If the smoke test must not use mocking, implement a local “fixture server” mode inside the test script.

---

## Part 5 — Output
Provide:
1) the analysis report markdown
2) the proposed file tree changes
3) code changes (patch/diff or file blocks)
4) tests added/updated
5) exact commands to run:
   - unit tests
   - smoke test
   - one CLI run using api ingest mode
   - one API endpoint run using api ingest mode