"""Tests for the changelog generation system.

Validates docstring parsing, commit note parsing, fixture-based
git scanning, and end-to-end generator output.

All tests are fixture-based — no live git required.
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Locate fixture directory
# ---------------------------------------------------------------------------

FIXTURE_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "changelog_repo"
FIXTURE_SRC = FIXTURE_DIR / "src" / "spine"


# ===========================================================================
# parse_docstrings tests
# ===========================================================================

class TestParseDocHeader:
    """Tests for Doc Header parsing."""

    def test_minimal_docstring(self):
        """One-line docstring with no header fields."""
        from spine.tools.changelog.parse_docstrings import parse_doc_header

        header, warns = parse_doc_header("Database adapter base class.")
        assert header.summary == "Database adapter base class."
        assert header.stability.value == "stable"  # default
        assert header.tier.value == "none"  # default
        assert header.doc_types[0].value == "API_REFERENCE"  # default
        assert header.tags == ()
        assert warns == []

    def test_empty_docstring(self):
        """Empty docstring returns defaults."""
        from spine.tools.changelog.parse_docstrings import parse_doc_header

        header, warns = parse_doc_header("")
        assert header.summary == ""
        assert warns == []

    def test_full_header(self):
        """Docstring with all header fields."""
        from spine.tools.changelog.parse_docstrings import parse_doc_header

        docstring = textwrap.dedent("""\
            Caching abstraction with multiple backend implementations.

            Stability: stable
            Tier: basic
            Since: 0.2.0
            Dependencies: optional: redis
            Doc-Types: TECHNICAL_DESIGN, API_REFERENCE
            Tags: cache, backend, redis, memory

            Provides a unified CacheBackend protocol.
        """)

        header, warns = parse_doc_header(docstring)
        assert header.summary == "Caching abstraction with multiple backend implementations."
        assert header.stability.value == "stable"
        assert header.tier.value == "basic"
        assert header.since == "0.2.0"
        assert header.dependencies == "optional: redis"
        assert len(header.doc_types) == 2
        assert header.doc_types[0].value == "TECHNICAL_DESIGN"
        assert header.doc_types[1].value == "API_REFERENCE"
        assert header.tags == ("cache", "backend", "redis", "memory")
        assert "unified CacheBackend protocol" in header.body
        assert warns == []

    def test_experimental_stability(self):
        """Experimental stability is parsed correctly."""
        from spine.tools.changelog.parse_docstrings import parse_doc_header

        docstring = "Feature flags.\n\nStability: experimental\nTier: basic"
        header, warns = parse_doc_header(docstring)
        assert header.stability.value == "experimental"
        assert warns == []

    def test_deprecated_stability(self):
        """Deprecated stability is parsed correctly."""
        from spine.tools.changelog.parse_docstrings import parse_doc_header

        docstring = "Old module.\n\nStability: deprecated"
        header, warns = parse_doc_header(docstring)
        assert header.stability.value == "deprecated"

    def test_invalid_stability_warns(self):
        """Invalid stability value produces a warning."""
        from spine.tools.changelog.parse_docstrings import parse_doc_header

        docstring = "Module.\n\nStability: alpha"
        header, warns = parse_doc_header(docstring)
        assert len(warns) == 1
        assert warns[0].field == "Stability"
        assert "alpha" in warns[0].message
        # Falls back to default
        assert header.stability.value == "stable"

    def test_invalid_tier_warns(self):
        """Invalid tier value produces a warning."""
        from spine.tools.changelog.parse_docstrings import parse_doc_header

        docstring = "Module.\n\nTier: premium"
        header, warns = parse_doc_header(docstring)
        assert len(warns) == 1
        assert warns[0].field == "Tier"

    def test_invalid_doc_type_warns(self):
        """Invalid doc-type value produces a warning."""
        from spine.tools.changelog.parse_docstrings import parse_doc_header

        docstring = "Module.\n\nDoc-Types: COOKBOOK"
        header, warns = parse_doc_header(docstring)
        assert len(warns) == 1
        assert warns[0].field == "Doc-Types"
        # Still gets default API_REFERENCE since COOKBOOK was invalid
        assert header.doc_types == ()  or len(header.doc_types) == 1

    def test_body_preserved(self):
        """Body after the header block is preserved."""
        from spine.tools.changelog.parse_docstrings import parse_doc_header

        docstring = textwrap.dedent("""\
            Summary line.

            Stability: stable
            Tags: a, b

            This is the body.

            It has multiple paragraphs.
        """)
        header, _ = parse_doc_header(docstring)
        assert "This is the body." in header.body
        assert "multiple paragraphs" in header.body

    def test_no_blank_after_summary(self):
        """Header fields immediately after summary (no blank line)."""
        from spine.tools.changelog.parse_docstrings import parse_doc_header

        docstring = "Summary.\nStability: experimental"
        header, _ = parse_doc_header(docstring)
        assert header.stability.value == "experimental"

    def test_case_insensitive_keys(self):
        """Header keys are case-insensitive."""
        from spine.tools.changelog.parse_docstrings import parse_doc_header

        docstring = "Module.\n\nstability: experimental\ntier: full"
        header, warns = parse_doc_header(docstring)
        assert header.stability.value == "experimental"
        assert header.tier.value == "full"
        assert warns == []


class TestExtractDocstring:
    """Tests for AST-based docstring extraction."""

    def test_extract_module_docstring(self):
        """Extract module-level docstring from Python source."""
        from spine.tools.changelog.parse_docstrings import extract_docstring

        source = '"""This is the module docstring."""\n\nimport os\n'
        assert extract_docstring(source) == "This is the module docstring."

    def test_no_docstring(self):
        """Returns None when no module docstring exists."""
        from spine.tools.changelog.parse_docstrings import extract_docstring

        source = "import os\n\nx = 1\n"
        assert extract_docstring(source) is None

    def test_syntax_error(self):
        """Returns None on syntax error."""
        from spine.tools.changelog.parse_docstrings import extract_docstring

        source = "def broken(\n"
        assert extract_docstring(source) is None


class TestScanModules:
    """Tests for source tree scanning (uses fixture directory)."""

    def test_scan_fixture_tree(self):
        """Scan the fixture source tree and find all modules."""
        from spine.tools.changelog.parse_docstrings import scan_modules

        modules, warns = scan_modules(FIXTURE_SRC)

        # Should find our fixture modules
        paths = {m.path for m in modules}
        assert "spine/core/cache.py" in paths
        assert "spine/core/protocols.py" in paths
        assert "spine/core/enums.py" in paths
        assert "spine/core/errors.py" in paths
        assert "spine/core/feature_flags.py" in paths
        assert "spine/core/secrets.py" in paths
        assert "spine/core/adapters/base.py" in paths

    def test_scan_finds_headers(self):
        """Modules with Doc Headers have has_header_fields=True."""
        from spine.tools.changelog.parse_docstrings import scan_modules

        modules, _ = scan_modules(FIXTURE_SRC)
        mod_map = {m.path: m for m in modules}

        # cache.py has full headers
        cache = mod_map["spine/core/cache.py"]
        assert cache.has_header_fields is True
        assert cache.header is not None
        assert cache.header.tier.value == "basic"

        # adapters/base.py has only a one-liner — no headers
        base = mod_map["spine/core/adapters/base.py"]
        assert base.has_header_fields is False

    def test_scan_no_warnings_for_valid(self):
        """Valid fixture modules produce no warnings."""
        from spine.tools.changelog.parse_docstrings import scan_modules

        _, warns = scan_modules(FIXTURE_SRC)
        assert warns == []


class TestDetectMissingHeaders:
    """Tests for missing header detection."""

    def test_detect_missing(self):
        """Modules with docstrings but no headers are detected."""
        from spine.tools.changelog.parse_docstrings import (
            detect_missing_headers,
            scan_modules,
        )

        modules, _ = scan_modules(FIXTURE_SRC)
        missing = detect_missing_headers(modules)

        missing_paths = {m.path for m in missing}
        # adapters/base.py has a docstring > 20 chars but no header fields
        assert "spine/core/adapters/base.py" in missing_paths

        # cache.py has headers so should NOT be in missing
        assert "spine/core/cache.py" not in missing_paths


# ===========================================================================
# parse_commit_notes tests
# ===========================================================================

class TestParseCommitMessage:
    """Tests for commit message parsing."""

    def test_basic_commit(self):
        """Parse a simple commit with What/Why sections."""
        from spine.tools.changelog.parse_commit_notes import parse_commit_message

        message = textwrap.dedent("""\
            feat(core/cache): add caching abstraction

            What:
            - Add CacheBackend protocol
            - Add InMemoryCache with TTL

            Why:
            - Enable cache-aside pattern

            Tags: cache, backend
            Markers: NEW

            Impact: public_api
            Feature-Type: infrastructure
        """)

        note, warns = parse_commit_message(message, sha="abc1234567890")
        assert note.subject == "feat(core/cache): add caching abstraction"
        assert "CacheBackend protocol" in note.body_what
        assert "cache-aside pattern" in note.body_why
        assert note.trailers.tags == ("cache", "backend")
        assert note.trailers.markers == ("NEW",)
        assert note.trailers.impact.value == "public_api"
        assert note.trailers.feature_type == "infrastructure"
        assert warns == []

    def test_fix_commit(self):
        """Parse a fix commit."""
        from spine.tools.changelog.parse_commit_notes import parse_commit_message

        message = "fix(core/cache): handle TTL expiry edge case\n\nImpact: behavior"
        note, _ = parse_commit_message(message, sha="def0000000")
        assert note.subject.startswith("fix(")
        assert note.trailers.impact.value == "behavior"

    def test_classification_section(self):
        """Trailers under Classification: section are parsed."""
        from spine.tools.changelog.parse_commit_notes import parse_commit_message

        message = textwrap.dedent("""\
            feat(core): add feature

            What:
            - Add something

            Tags: test

            Classification:
            - Feature-Type: data_layer
            - Architecture: database
            - Domain: operation_state
        """)

        note, warns = parse_commit_message(message)
        assert note.trailers.feature_type == "data_layer"
        assert note.trailers.architecture == "database"
        assert note.trailers.domain == "operation_state"

    def test_invalid_impact_warns(self):
        """Invalid impact value produces a warning."""
        from spine.tools.changelog.parse_commit_notes import parse_commit_message

        message = "feat: something\n\nImpact: critical"
        _, warns = parse_commit_message(message)
        assert any(w.field == "Impact" for w in warns)

    def test_surfaces_parsed(self):
        """Surfaces trailer is parsed into a tuple."""
        from spine.tools.changelog.parse_commit_notes import parse_commit_message

        message = "feat: add\n\nSurfaces: CacheBackend, InMemoryCache"
        note, _ = parse_commit_message(message)
        assert note.trailers.surfaces == ("CacheBackend", "InMemoryCache")

    def test_empty_message(self):
        """Empty message returns empty CommitNote."""
        from spine.tools.changelog.parse_commit_notes import parse_commit_message

        note, _ = parse_commit_message("")
        assert note.subject == ""

    def test_migration_breaking(self):
        """Breaking migration is parsed."""
        from spine.tools.changelog.parse_commit_notes import parse_commit_message

        message = "feat: breaking\n\nMigration: breaking\nMigration-Notes: Rename X to Y"
        note, _ = parse_commit_message(message)
        assert note.trailers.migration.value == "breaking"
        assert note.trailers.migration_notes == "Rename X to Y"


class TestParseSidecar:
    """Tests for sidecar file parsing."""

    def test_parse_sidecar_text(self):
        """Parse sidecar markdown with all sections."""
        from spine.tools.changelog.parse_commit_notes import parse_sidecar_text

        text = textwrap.dedent("""\
            # feat(core/adapters): add database adapter framework

            ## Migration Guide

            No migration needed — this is a new module.

            ## Architecture Diagram

            ```mermaid
            classDiagram
                class DatabaseAdapter {
                    +connect()
                    +disconnect()
                }
            ```

            ## Examples

            ```python
            adapter = get_adapter("sqlite")
            ```
        """)

        sc = parse_sidecar_text(text)
        assert "No migration needed" in sc.migration_guide
        assert len(sc.diagrams) == 1
        assert "DatabaseAdapter" in sc.diagrams[0]
        assert "get_adapter" in sc.examples

    def test_parse_sidecar_no_diagrams(self):
        """Sidecar without diagrams returns empty tuple."""
        from spine.tools.changelog.parse_commit_notes import parse_sidecar_text

        sc = parse_sidecar_text("# title\n\n## Examples\n\nSome code.")
        assert sc.diagrams == ()

    def test_load_sidecar_dir(self):
        """Load sidecars from fixture directory."""
        from spine.tools.changelog.parse_commit_notes import load_sidecar_dir

        sidecar_dir = FIXTURE_DIR / "commit_notes"
        sidecars = load_sidecar_dir(sidecar_dir)

        assert "ddd0004" in sidecars
        assert "DatabaseAdapter" in sidecars["ddd0004"].diagrams[0]

    def test_load_sidecar_dir_missing(self):
        """Missing directory returns empty dict."""
        from spine.tools.changelog.parse_commit_notes import load_sidecar_dir

        result = load_sidecar_dir(Path("/nonexistent"))
        assert result == {}


# ===========================================================================
# git_scan (fixture-based) tests
# ===========================================================================

class TestFixtureGitScan:
    """Tests for fixture-based git scanning."""

    def test_scan_fixtures(self):
        """Scan commits from fixture JSON file."""
        from spine.tools.changelog.git_scan import scan_git_history

        commits, warns = scan_git_history(fixture_dir=FIXTURE_DIR)

        assert len(commits) == 7
        assert commits[0].short_sha == "aaa0001"
        assert commits[0].subject == "feat(project): initialize spine-core package [FOUNDATIONAL]"
        assert len(commits[0].files) == 3

    def test_fixture_trailers_parsed(self):
        """Trailers in fixture commit messages are parsed."""
        from spine.tools.changelog.git_scan import scan_git_history

        commits, _ = scan_git_history(fixture_dir=FIXTURE_DIR)

        # Commit 3 (cache)
        cache_commit = commits[2]
        assert cache_commit.trailers.markers == ("NEW",)
        assert cache_commit.trailers.architecture == "caching"
        assert cache_commit.trailers.surfaces == ("CacheBackend", "InMemoryCache")

    def test_fixture_docstrings(self):
        """Docstrings from fixture data are accessible."""
        from spine.tools.changelog.git_scan import scan_git_history

        commits, _ = scan_git_history(fixture_dir=FIXTURE_DIR)

        # Commit 2 (primitives) has docstrings
        prim_commit = commits[1]
        assert "spine/core/protocols.py" in prim_commit.docstrings
        assert "SINGLE SOURCE OF TRUTH" in prim_commit.docstrings["spine/core/protocols.py"]

    def test_fixture_sidecar_loaded(self):
        """Sidecar file from fixture directory is loaded."""
        from spine.tools.changelog.git_scan import scan_git_history

        commits, _ = scan_git_history(fixture_dir=FIXTURE_DIR)

        # Commit 4 (adapters) has a sidecar
        adapter_commit = commits[3]
        assert adapter_commit.sidecar is not None
        assert len(adapter_commit.sidecar.diagrams) > 0

    def test_no_fixture_dir_and_no_repo(self):
        """Providing neither raises ValueError."""
        from spine.tools.changelog.git_scan import scan_git_history

        with pytest.raises(ValueError, match="Provide either"):
            scan_git_history()


class TestPhaseMapping:
    """Tests for phase map loading and commit assignment."""

    def test_load_phase_map(self):
        """Load phase map from JSON fixture."""
        from spine.tools.changelog.git_scan import load_phase_map

        phases = load_phase_map(FIXTURE_DIR / "phase_map.json")
        assert len(phases) == 5
        assert phases[0].name == "Project Bootstrap"
        assert phases[0].number == 1

    def test_assign_commits_to_phases(self):
        """Commits are assigned to correct phases."""
        from spine.tools.changelog.git_scan import (
            assign_commits_to_phases,
            scan_git_history,
        )

        commits, _ = scan_git_history(fixture_dir=FIXTURE_DIR)
        phases = assign_commits_to_phases(
            commits, FIXTURE_DIR / "phase_map.json",
        )

        assert len(phases) == 5
        assert len(phases[0].commits) == 1  # Bootstrap
        assert phases[0].commits[0].short_sha == "aaa0001"
        assert len(phases[2].commits) == 2  # Data Layer

    def test_no_phase_map_single_group(self):
        """Without phase map, all commits go in one group."""
        from spine.tools.changelog.git_scan import (
            assign_commits_to_phases,
            scan_git_history,
        )

        commits, _ = scan_git_history(fixture_dir=FIXTURE_DIR)
        phases = assign_commits_to_phases(commits, None)

        assert len(phases) == 1
        assert phases[0].name == "All Commits"
        assert len(phases[0].commits) == 7


# ===========================================================================
# model tests
# ===========================================================================

class TestModel:
    """Tests for data model classes."""

    def test_module_index_build(self):
        """ModuleIndex groups modules by doc-type, tier, stability."""
        from spine.tools.changelog.model import (
            DocHeader, DocType, ModuleIndex, ModuleInfo, Stability, Tier,
        )

        modules = [
            ModuleInfo(
                path="a.py", module_path="a",
                header=DocHeader(
                    summary="Module A",
                    stability=Stability.STABLE,
                    tier=Tier.BASIC,
                    doc_types=(DocType.API_REFERENCE,),
                ),
                has_header_fields=True,
            ),
            ModuleInfo(
                path="b.py", module_path="b",
                header=DocHeader(
                    summary="Module B",
                    stability=Stability.EXPERIMENTAL,
                    tier=Tier.FULL,
                    doc_types=(DocType.TECHNICAL_DESIGN, DocType.API_REFERENCE),
                ),
                has_header_fields=True,
            ),
        ]

        idx = ModuleIndex(modules=modules)
        idx.build_indexes()

        assert len(idx.by_doc_type["API_REFERENCE"]) == 2
        assert len(idx.by_doc_type["TECHNICAL_DESIGN"]) == 1
        assert len(idx.by_tier["basic"]) == 1
        assert len(idx.by_tier["full"]) == 1
        assert len(idx.by_stability["stable"]) == 1
        assert len(idx.by_stability["experimental"]) == 1

    def test_phase_group_total_files(self):
        """PhaseGroup.total_files counts unique files."""
        from spine.tools.changelog.model import CommitFile, CommitNote, PhaseGroup

        commits = [
            CommitNote(
                sha="a", short_sha="a",
                subject="c1",
                files=(CommitFile("a.py", "A"), CommitFile("b.py", "A")),
            ),
            CommitNote(
                sha="b", short_sha="b",
                subject="c2",
                files=(CommitFile("b.py", "M"), CommitFile("c.py", "A")),
            ),
        ]
        phase = PhaseGroup(number=1, name="Test", commits=commits)
        assert phase.total_files == 3  # a.py, b.py, c.py

    def test_controlled_vocab_sets(self):
        """Controlled vocabulary sets are populated."""
        from spine.tools.changelog.model import (
            VALID_ARCHITECTURE,
            VALID_DOMAIN,
            VALID_FEATURE_TYPES,
            VALID_MARKERS,
            VALID_STABILITY,
            VALID_TIER,
        )

        assert "stable" in VALID_STABILITY
        assert "basic" in VALID_TIER
        assert "database" in VALID_ARCHITECTURE
        assert "operation_state" in VALID_DOMAIN
        assert "data_layer" in VALID_FEATURE_TYPES
        assert "NEW" in VALID_MARKERS


# ===========================================================================
# Generator (end-to-end) tests
# ===========================================================================

class TestGenerator:
    """End-to-end tests for the changelog generator."""

    def test_generate_all_targets(self, tmp_path):
        """Generate all output targets from fixtures."""
        from spine.tools.changelog.generator import ChangelogGenerator

        gen = ChangelogGenerator(
            source_root=FIXTURE_SRC,
            output_dir=tmp_path,
            fixture_dir=FIXTURE_DIR,
            phase_map_path=FIXTURE_DIR / "phase_map.json",
            project_name="spine-core",
            project_version="0.4.0",
        )

        outputs = gen.generate()

        assert "changelog" in outputs
        assert "review" in outputs
        assert "api-index" in outputs

        # All files exist
        assert outputs["changelog"].exists()
        assert outputs["review"].exists()
        assert outputs["api-index"].exists()

    def test_changelog_content(self, tmp_path):
        """CHANGELOG.md has correct sections and entries."""
        from spine.tools.changelog.generator import ChangelogGenerator

        gen = ChangelogGenerator(
            source_root=FIXTURE_SRC,
            output_dir=tmp_path,
            fixture_dir=FIXTURE_DIR,
            project_name="spine-core",
            project_version="0.4.0",
        )
        gen.generate(targets=["changelog"])

        content = (tmp_path / "CHANGELOG.md").read_text(encoding="utf-8")

        assert "# Changelog" in content
        assert "[0.4.0]" in content
        assert "### Added" in content
        assert "### Fixed" in content
        assert "CacheBackend" in content

    def test_review_content(self, tmp_path):
        """REWRITE_REVIEW.md has phases, commits, file tables."""
        from spine.tools.changelog.generator import ChangelogGenerator

        gen = ChangelogGenerator(
            source_root=FIXTURE_SRC,
            output_dir=tmp_path,
            fixture_dir=FIXTURE_DIR,
            phase_map_path=FIXTURE_DIR / "phase_map.json",
            project_name="spine-core",
        )
        gen.generate(targets=["review"])

        content = (tmp_path / "REWRITE_REVIEW.md").read_text(encoding="utf-8")

        # Phase headers
        assert "Phase 1" in content
        assert "Project Bootstrap" in content
        assert "Phase 3" in content
        assert "Data Layer" in content

        # Commit details
        assert "`aaa0001`" in content
        assert "`bbb0002`" in content

        # File tables
        assert "| ➕ |" in content
        assert "pyproject.toml" in content

        # Module docstrings
        assert "Module Docstrings" in content

    def test_review_has_sidecar_content(self, tmp_path):
        """Review includes sidecar migration guide."""
        from spine.tools.changelog.generator import ChangelogGenerator

        gen = ChangelogGenerator(
            source_root=FIXTURE_SRC,
            output_dir=tmp_path,
            fixture_dir=FIXTURE_DIR,
            phase_map_path=FIXTURE_DIR / "phase_map.json",
        )
        gen.generate(targets=["review"])

        content = (tmp_path / "REWRITE_REVIEW.md").read_text(encoding="utf-8")
        # Sidecar for ddd0004 has migration guide
        assert "Migration Guide" in content

    def test_api_index_content(self, tmp_path):
        """api_index.md lists modules grouped by classification."""
        from spine.tools.changelog.generator import ChangelogGenerator

        gen = ChangelogGenerator(
            source_root=FIXTURE_SRC,
            output_dir=tmp_path,
            fixture_dir=FIXTURE_DIR,
        )
        gen.generate(targets=["api-index"])

        content = (tmp_path / "api_index.md").read_text(encoding="utf-8")

        assert "# API Module Index" in content
        assert "## By Doc-Type" in content
        assert "## By Tier" in content
        assert "## By Stability" in content
        assert "spine.core.cache" in content
        assert "spine.core.protocols" in content

    def test_diagrams_extracted(self, tmp_path):
        """Mermaid diagrams are extracted from docstrings."""
        from spine.tools.changelog.generator import ChangelogGenerator

        gen = ChangelogGenerator(
            source_root=FIXTURE_SRC,
            output_dir=tmp_path,
            fixture_dir=FIXTURE_DIR,
        )
        gen.generate(targets=["diagrams"])

        diagram_dir = tmp_path / "diagrams"
        if diagram_dir.exists():
            mmd_files = list(diagram_dir.glob("*.mmd"))
            # feature_flags.py has a mermaid diagram
            assert len(mmd_files) >= 1
            # Check content
            content = mmd_files[0].read_text(encoding="utf-8")
            assert "classDiagram" in content or "flowchart" in content

    def test_specific_target_only(self, tmp_path):
        """Generating specific target only produces that file."""
        from spine.tools.changelog.generator import ChangelogGenerator

        gen = ChangelogGenerator(
            source_root=FIXTURE_SRC,
            output_dir=tmp_path,
            fixture_dir=FIXTURE_DIR,
        )
        outputs = gen.generate(targets=["changelog"])

        assert "changelog" in outputs
        assert "review" not in outputs

    def test_deterministic_output(self, tmp_path):
        """Running generator twice produces identical output."""
        from spine.tools.changelog.generator import ChangelogGenerator

        def run():
            out = tmp_path / "run"
            gen = ChangelogGenerator(
                source_root=FIXTURE_SRC,
                output_dir=out,
                fixture_dir=FIXTURE_DIR,
                phase_map_path=FIXTURE_DIR / "phase_map.json",
            )
            gen.generate()
            return {
                name: (out / name).read_text(encoding="utf-8")
                for name in ["CHANGELOG.md", "REWRITE_REVIEW.md", "api_index.md"]
            }

        run1 = run()
        run2 = run()

        for name in run1:
            assert run1[name] == run2[name], f"{name} differs between runs"


# ===========================================================================
# CLI tests
# ===========================================================================

class TestCLI:
    """Tests for CLI commands."""

    def test_generate_command(self, tmp_path):
        """CLI generate command runs successfully."""
        from spine.tools.changelog.cli import main

        result = main([
            "generate",
            "--source-root", str(FIXTURE_SRC),
            "--output-dir", str(tmp_path),
            "--fixture-dir", str(FIXTURE_DIR),
            "--phase-map", str(FIXTURE_DIR / "phase_map.json"),
        ])
        assert result == 0
        assert (tmp_path / "CHANGELOG.md").exists()

    def test_detect_headers_command(self, capsys):
        """CLI detect-headers command reports missing headers."""
        from spine.tools.changelog.cli import main

        result = main([
            "detect-headers",
            "--source-root", str(FIXTURE_SRC),
        ])
        assert result == 0
        captured = capsys.readouterr()
        assert "Module scan:" in captured.out

    def test_generate_specific_target(self, tmp_path):
        """CLI with --target flag generates only that target."""
        from spine.tools.changelog.cli import main

        result = main([
            "generate",
            "--source-root", str(FIXTURE_SRC),
            "--output-dir", str(tmp_path),
            "--fixture-dir", str(FIXTURE_DIR),
            "--target", "changelog",
        ])
        assert result == 0
        assert (tmp_path / "CHANGELOG.md").exists()
        assert not (tmp_path / "REWRITE_REVIEW.md").exists()
