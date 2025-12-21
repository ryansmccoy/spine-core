"""Changelog and documentation generation system for spine-core.

Stability: stable
Tier: none
Since: 0.4.0
Dependencies: stdlib-only
Doc-Types: API_REFERENCE, TECHNICAL_DESIGN
Tags: changelog, documentation, generator, tooling

Turns module docstrings and git commit metadata into first-class
documentation artifacts: CHANGELOG.md, commit review documents,
API module indexes, and Mermaid diagrams.

Usage::

    from spine.tools.changelog import generate_changelog

    # Generate all outputs from live git repo
    generate_changelog(
        source_root=Path("src/spine"),
        output_dir=Path("docs/_generated"),
    )

    # Generate from fixture data (for testing)
    generate_changelog(
        source_root=Path("tests/fixtures/changelog_repo/src/spine"),
        output_dir=Path("docs/_generated"),
        fixture_dir=Path("tests/fixtures/changelog_repo"),
    )
"""

from __future__ import annotations

from pathlib import Path

from .generator import ChangelogGenerator
from .model import CommitNote, DocHeader, ModuleInfo, PhaseGroup


def generate_changelog(
    source_root: Path,
    output_dir: Path,
    *,
    fixture_dir: Path | None = None,
    phase_map_path: Path | None = None,
    commit_notes_dir: Path | None = None,
    targets: list[str] | None = None,
) -> dict[str, Path]:
    """Generate documentation artifacts.

    Args:
        source_root: Path to ``src/spine/`` (or equivalent).
        output_dir: Directory for generated files.
        fixture_dir: If set, read git data from fixtures instead of live git.
        phase_map_path: Path to ``phase_map.toml``. Auto-detected if None.
        commit_notes_dir: Path to ``docs/commit_notes/``. Auto-detected if None.
        targets: Which outputs to generate. None = all.
            Valid: ``["changelog", "review", "api-index", "diagrams"]``

    Returns:
        Dict mapping target name to output file path.
    """
    gen = ChangelogGenerator(
        source_root=source_root,
        output_dir=output_dir,
        fixture_dir=fixture_dir,
        phase_map_path=phase_map_path,
        commit_notes_dir=commit_notes_dir,
    )
    return gen.generate(targets=targets)


__all__ = [
    "generate_changelog",
    "ChangelogGenerator",
    "DocHeader",
    "CommitNote",
    "PhaseGroup",
    "ModuleInfo",
]
