Test Refactor + Rehome (spine-core + spine-domains-finra)

You are refactoring and reorganizing the test suite for the Spine monorepo so it scales across:

packages/spine-core (framework + shared primitives)

packages/spine-domains-* (domain implementations, starting with FINRA OTC transparency)

the “basic” sandbox app/repo (thin integration + smoke tests only)

Context / current pain

Right now, most tests live under the basic project directory and are not well organized. As we move toward a real multi-package monorepo and add more domains/sources, tests must live alongside the code they validate, and we need a clear taxonomy.

High-level goals

Move tests to the correct package

Core tests → packages/spine-core/tests/

Domain tests → packages/spine-domains-finra/.../tests/ (or the chosen domains package layout)

Basic repo tests → only “end-to-end / smoke / wiring” tests that validate packaging + CLI + one golden path.

Make the structure obvious

A new dev should know where to add a test without thinking.

Scenarios/fixtures should be deterministic, small, and reusable.

Keep CI + dev UX simple

uv run pytest at repo root should run everything.

Optional: uv run pytest packages/spine-core/tests and uv run pytest packages/spine-domains-finra/.../tests should also work.

No import hacks.

A) Decide and implement the final test layout
Preferred structure (implement this unless it causes major friction)
1) spine-core package tests

packages/spine-core/tests/

test_logging_*

test_dispatcher_*

test_runner_*

test_registry_*

test_cli_* (core CLI behavior only, not FINRA specifics)

test_db_* (core DB init/migrations utilities)

test_guardrails_* (forbidden imports checks, etc.)

2) domain package tests (FINRA OTC transparency)

packages/spine-domains-finra/src/spine/domains/finra/otc_transparency/tests/ OR packages/spine-domains-finra/tests/finra/otc_transparency/
Pick one approach and be consistent.

Organize into:

test_connector.py (file metadata/date derivation, tier detection)

test_pipelines_unit.py (ingest/normalize/aggregate/rolling unit-ish tests)

test_scenarios.py (messy data scenarios: missing cols, bad dates, duplicates, corrupt numbers, empty files)

test_integration.py (tiny “mini-e2e” using fixtures: ingest -> normalize -> aggregate)

3) “basic” repo tests become minimal

In the basic project (or root repo), keep only:

tests/smoke/test_basic_golden_path.py (db init + run 1–2 pipelines with fixtures)

tests/smoke/test_packaging_imports.py (imports resolve from installed packages)

tests/smoke/test_cli_commands.py (list/run works and outputs expected high-level summary)

Everything else moves to package-owned test folders.

B) Fixtures and scenario data rules (IMPORTANT)
Fixture location rules

Domain fixtures belong to the domain package:

packages/spine-domains-finra/.../tests/fixtures/finra/otc_transparency/...

Core fixtures belong to core:

packages/spine-core/tests/fixtures/...

Basic repo should NOT own domain fixtures long-term (only thin smoke fixtures if absolutely necessary).

Scenario fixture policy

Create small, readable fixtures:

10–50 rows typical

include explicit “bad row” examples for rejection tests

include at least:

header-only

missing required column

corrupt numeric value

duplicated natural key rows

filename without tier/date (forces fallback behavior)

Add a README.md under the domain fixtures folder explaining each file and the scenario.

C) Pytest config / tooling changes
1) Central pytest config

Add/adjust root pyproject.toml or pytest.ini so pytest discovers tests across packages cleanly.

Requirements:

Use testpaths that include package tests

Configure pythonpath correctly (prefer install editable packages vs hacking sys.path)

Make sure uv run pytest at repo root works

2) Markers

Add markers to keep tiers sane:

@pytest.mark.unit

@pytest.mark.integration

@pytest.mark.smoke

Default run should include unit + small integration tests, and smoke tests should be fast (or optionally skipped unless requested).

3) Best-practice tooling

Add/confirm:

ruff for lint

ruff format (or black, but prefer ruff if consistent)

mypy optional (only if low friction)

pytest-cov optional

pre-commit optional (nice-to-have)

Ensure configs live in the right place (root pyproject.toml) and apply consistently across packages.

D) Refactor tests to be more useful (fix naming + assertions)

While moving files:

Rename tests to reflect intent (avoid overly generic names like test_otc.py unless it’s a package-level grouping file).

Make assertions more meaningful:

verify counts: rows_in, rows_inserted, accepted, rejected

verify derived semantics: file_date, week_ending, tier

verify invariants: accepted + rejected == rows_in

verify idempotency/skip rules where present

Also fix misleading log/error labels you notice during tests (example: “runner.pipeline_not_found” showing for a KeyError — correct the error classification if that’s still happening).

E) Deliverables required in your response

Plan (ordered checklist)

Proposed file tree after refactor

Unified diffs implementing:

moved tests

fixture moves

pytest config updates

any import fixes

A short “How to run tests” doc update (root README + package README sections):

uv run pytest

uv run pytest packages/spine-core/tests

uv run pytest packages/spine-domains-finra/.../tests

uv run pytest -m smoke

Confirmation:

all tests pass

no duplicated tests left behind in basic

CI command(s) specified

F) Constraints / non-goals

Do NOT change business logic unless a test reveals a real bug (but if you find one, fix it with a targeted diff + explanation).

Keep smoke tests minimal and fast.

Avoid brittle tests that depend on wall-clock time or external network.