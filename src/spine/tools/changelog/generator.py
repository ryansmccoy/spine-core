"""Render changelog and documentation artifacts from parsed data.

Stability: stable
Tier: none
Since: 0.4.0
Dependencies: stdlib-only
Doc-Types: API_REFERENCE, TECHNICAL_DESIGN
Tags: changelog, generator, renderer

The main orchestrator: scans sources + git history, merges data,
and renders all output files. Each output format has a dedicated
render method producing deterministic, style-consistent markdown.

Architecture::

    ┌─────────────┐  ┌──────────────┐  ┌──────────────┐
    │  Docstrings │  │  Git History  │  │  Phase Map   │
    └──────┬──────┘  └──────┬───────┘  └──────┬───────┘
           │                │                  │
           ▼                ▼                  ▼
    ┌──────────────────────────────────────────────────┐
    │              ChangelogGenerator                   │
    │  scan() → parse() → merge() → render() → write() │
    └───┬──────────┬──────────┬──────────┬─────────────┘
        ▼          ▼          ▼          ▼
    CHANGELOG  REVIEW.md  api_index  diagrams/
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from .git_scan import assign_commits_to_phases, scan_git_history
from .kg_builder import build_module_graph
from .model import (
    CommitNote,
    ModuleIndex,
    ModuleInfo,
    PhaseGroup,
    ValidationWarning,
)
from .parse_docstrings import scan_modules
from .render_html import render_html_review

logger = logging.getLogger(__name__)

# Status icon mapping
_STATUS_ICONS = {"A": "➕", "M": "✏️", "D": "🗑️", "R": "🔄", "C": "📋"}

# Mermaid fence pattern
_MERMAID_RE = re.compile(r"```mermaid\s*\n(.*?)```", re.DOTALL)

# Valid output targets
VALID_TARGETS = frozenset({"changelog", "review", "api-index", "diagrams", "html-review"})


class ChangelogGenerator:
    """Orchestrates the full changelog generation operation.

    Manifesto:
        Documentation should be generated FROM code, not written separately.
        This generator turns structured docstrings and git commit metadata
        into first-class documentation artifacts — deterministically,
        without manual authoring or drift.

    Architecture:
        ::

            ┌─────────────┐  ┌──────────────┐  ┌──────────────┐
            │  Docstrings  │  │  Git History  │  │  Phase Map   │
            └──────┬──────┘  └──────┬───────┘  └──────┬───────┘
                   │                │                  │
                   ▼                ▼                  ▼
            ┌──────────────────────────────────────────────────┐
            │              ChangelogGenerator                   │
            │  scan() → parse() → merge() → render() → write() │
            └───┬──────────┬──────────┬──────────┬─────────────┘
                ▼          ▼          ▼          ▼
            CHANGELOG  REVIEW.md  api_index  diagrams/

    Features:
        - 4-stage operation: Scan → Parse → Merge → Render
        - Keep-a-Changelog format with auto-categorization
        - Commit review document mirroring REWRITE_COMMIT_REVIEW.md format
        - API module index grouped by Doc-Type, Tier, Stability
        - Mermaid diagram extraction from docstrings and sidecars
        - Fixture-based testing mode (no git dependency)

    Guardrails:
        - Do NOT import modules to read docstrings
          ✅ Use AST-only extraction
        - Do NOT require git for testing
          ✅ Fixture mode with commits.json
        - Do NOT add runtime dependencies
          ✅ stdlib-only (ast, subprocess, json, tomllib)

    Tags:
        - changelog
        - tooling
        - generator
        - documentation
        - operation

    Doc-Types:
        - API_REFERENCE (section: "Tooling", priority: 7)
        - ARCHITECTURE (section: "Documentation Operation", priority: 6)
        - CHANGELOG (section: "v0.4.0", priority: 9)

    Changelog:
        - 0.4.0: Initial implementation with 4 output targets and 51 tests

    Examples:
        >>> gen = ChangelogGenerator(
        ...     source_root=Path("src/spine"),
        ...     output_dir=Path("docs/_generated"),
        ... )
        >>> outputs = gen.generate()
    """

    def __init__(
        self,
        source_root: Path,
        output_dir: Path,
        *,
        fixture_dir: Path | None = None,
        phase_map_path: Path | None = None,
        commit_notes_dir: Path | None = None,
        project_name: str = "spine-core",
        project_version: str = "",
    ):
        self.source_root = source_root
        self.output_dir = output_dir
        self.fixture_dir = fixture_dir
        self.phase_map_path = phase_map_path
        self.commit_notes_dir = commit_notes_dir
        self.project_name = project_name
        self.project_version = project_version

        # Populated during generate()
        self.modules: list[ModuleInfo] = []
        self.module_index: ModuleIndex = ModuleIndex()
        self.phases: list[PhaseGroup] = []
        self.all_commits: list[CommitNote] = []
        self.warnings: list[ValidationWarning] = []

    def generate(
        self,
        *,
        targets: list[str] | None = None,
    ) -> dict[str, Path]:
        """Run the full operation and write output files.

        Args:
            targets: Which outputs to generate. None = all.

        Returns:
            Dict mapping target name to output file path.
        """
        active_targets = set(targets) if targets else VALID_TARGETS

        # 1. Scan
        self._scan()

        # 2. Ensure output directory
        self.output_dir.mkdir(parents=True, exist_ok=True)

        outputs: dict[str, Path] = {}

        # 3. Render each target
        if "changelog" in active_targets:
            path = self.output_dir / "CHANGELOG.md"
            path.write_text(self.render_changelog(), encoding="utf-8")
            outputs["changelog"] = path

        if "review" in active_targets:
            path = self.output_dir / "REWRITE_REVIEW.md"
            path.write_text(self.render_review(), encoding="utf-8")
            outputs["review"] = path

        if "html-review" in active_targets:
            path = self.output_dir / "REWRITE_REVIEW.html"
            # Build knowledge graph from scanned modules
            kg_data = build_module_graph(self.modules, self.source_root) if self.modules else None
            path.write_text(
                render_html_review(
                    self.phases,
                    project_name=self.project_name,
                    project_version=self.project_version,
                    kg_data=kg_data,
                ),
                encoding="utf-8",
            )
            outputs["html-review"] = path

        if "api-index" in active_targets:
            path = self.output_dir / "api_index.md"
            path.write_text(self.render_api_index(), encoding="utf-8")
            outputs["api-index"] = path

        if "diagrams" in active_targets:
            diagram_dir = self.output_dir / "diagrams"
            diagram_paths = self._extract_diagrams(diagram_dir)
            if diagram_paths:
                outputs["diagrams"] = diagram_dir

        if self.warnings:
            logger.warning(
                "Changelog generation produced %d warnings", len(self.warnings),
            )
            for w in self.warnings:
                logger.warning("  [%s] %s: %s", w.source, w.field, w.message)

        return outputs

    def _scan(self) -> None:
        """Execute scan and parse stages."""
        # Scan docstrings
        self.modules, doc_warns = scan_modules(self.source_root)
        self.warnings.extend(doc_warns)

        # Build module index
        self.module_index = ModuleIndex(modules=list(self.modules))
        self.module_index.build_indexes()

        # Scan git history
        if self.fixture_dir:
            commits, git_warns = scan_git_history(fixture_dir=self.fixture_dir)
        else:
            repo_dir = self.source_root
            # Walk up to find .git directory
            for parent in [self.source_root] + list(self.source_root.parents):
                if (parent / ".git").exists():
                    repo_dir = parent
                    break
            commits, git_warns = scan_git_history(
                repo_dir=repo_dir,
                sidecar_dir=self.commit_notes_dir,
            )
        self.warnings.extend(git_warns)
        self.all_commits = commits

        # Assign commits to phases
        self.phases = assign_commits_to_phases(commits, self.phase_map_path)

    # ------------------------------------------------------------------
    # CHANGELOG.md
    # ------------------------------------------------------------------

    def render_changelog(self) -> str:
        """Render a Keep-a-Changelog style CHANGELOG.md."""
        lines: list[str] = []
        lines.append(f"# Changelog — {self.project_name}")
        lines.append("")
        lines.append(
            "All notable changes to this project are documented in this file.  "
        )
        lines.append(
            "Format follows [Keep a Changelog](https://keepachangelog.com/)."
        )
        lines.append("")

        # Group commits by changelog category
        added: list[str] = []
        changed: list[str] = []
        deprecated: list[str] = []
        fixed: list[str] = []
        security: list[str] = []
        breaking: list[str] = []

        for commit in self.all_commits:
            markers = set(commit.trailers.markers)
            impact = commit.trailers.impact
            migration = commit.trailers.migration

            # Determine entry text
            entry = f"**{commit.subject}**"
            if commit.trailers.surfaces:
                surfaces = ", ".join(f"`{s}`" for s in commit.trailers.surfaces)
                entry += f" — {surfaces}"

            # Categorize
            if migration.value == "breaking":
                breaking.append(entry)
            elif impact.value == "security":
                security.append(entry)
            elif "DEPRECATION" in markers:
                deprecated.append(entry)
            elif commit.subject.startswith("fix(") or commit.subject.startswith("fix:"):
                fixed.append(entry)
            elif "REFACTOR" in markers or impact.value == "behavior":
                changed.append(entry)
            else:
                added.append(entry)

        # Render version header
        version = self.project_version or "Unreleased"
        lines.append(f"## [{version}]")
        lines.append("")

        for section, items in [
            ("⚠️ Breaking", breaking),
            ("Added", added),
            ("Changed", changed),
            ("Deprecated", deprecated),
            ("Fixed", fixed),
            ("Security", security),
        ]:
            if items:
                lines.append(f"### {section}")
                lines.append("")
                for item in items:
                    lines.append(f"- {item}")
                lines.append("")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # REWRITE_REVIEW.md
    # ------------------------------------------------------------------

    def render_review(self) -> str:
        """Render the detailed commit review document.

        Mirrors the format of the existing REWRITE_COMMIT_REVIEW.md:
        phases → commits → file tables → module docstrings.
        """
        lines: list[str] = []
        total_commits = sum(len(p.commits) for p in self.phases)
        total_files = set()
        for p in self.phases:
            for c in p.commits:
                for f in c.files:
                    total_files.add(f.path)

        lines.append(f"# {self.project_name.title()} Rewrite: Commit Review")
        lines.append("")
        lines.append(
            f"> Commits: **{total_commits}** | "
            f"Files: **{len(total_files)}** | "
            f"Phases: **{len(self.phases)}**"
        )
        lines.append("")

        # Summary table
        lines.append("| Phase | Name | Commits | Files |")
        lines.append("|:-----:|:-----|:-------:|:-----:|")
        for phase in self.phases:
            lines.append(
                f"| {phase.number} | {phase.name} | "
                f"{len(phase.commits)} | {phase.total_files} |"
            )
        lines.append("")

        # Render each phase
        commit_number = 0
        for phase in self.phases:
            lines.append("---")
            lines.append("")
            lines.append(f"# Phase {phase.number} — {phase.name}")
            lines.append("")

            for commit in phase.commits:
                commit_number += 1
                lines.extend(
                    self._render_commit(commit, commit_number, total_commits)
                )

        return "\n".join(lines)

    def _render_commit(
        self, commit: CommitNote, num: int, total: int,
    ) -> list[str]:
        """Render a single commit section."""
        lines: list[str] = []
        lines.append(f"## {num} / {total}  `{commit.short_sha}`")
        lines.append("")
        lines.append(f"**{commit.subject}**")
        lines.append("")

        # Metadata table
        added = sum(1 for f in commit.files if f.status == "A")
        modified = sum(1 for f in commit.files if f.status == "M")
        deleted = sum(1 for f in commit.files if f.status == "D")

        lines.append("| | |")
        lines.append("|:--|:--|")
        if commit.date:
            lines.append(f"| Date | {commit.date} |")
        file_summary = f"**{len(commit.files)}** ({added} added"
        if modified:
            file_summary += f", {modified} modified"
        if deleted:
            file_summary += f", {deleted} deleted"
        file_summary += ")"
        lines.append(f"| Files | {file_summary} |")
        lines.append("")

        # Commit message body
        body_parts: list[str] = []
        if commit.body_what:
            body_parts.append("What:")
            for line in commit.body_what.splitlines():
                body_parts.append(f"- {line}")
        if commit.body_why:
            body_parts.append("")
            body_parts.append("Why:")
            for line in commit.body_why.splitlines():
                body_parts.append(f"- {line}")

        # Trailers
        t = commit.trailers
        if t.tags:
            body_parts.append("")
            body_parts.append(f"Tags: {', '.join(t.tags)}")
        if t.markers:
            body_parts.append(f"Markers: {', '.join(t.markers)}")
        if t.impact.value != "internal":
            body_parts.append(f"Impact: {t.impact.value}")
        if t.migration.value != "none":
            body_parts.append(f"Migration: {t.migration.value}")
            if t.migration_notes:
                body_parts.append(f"Migration-Notes: {t.migration_notes}")

        if t.feature_type or t.architecture or t.domain:
            body_parts.append("")
            body_parts.append("Classification:")
            if t.feature_type:
                body_parts.append(f"- Feature-Type: {t.feature_type}")
            if t.architecture:
                body_parts.append(f"- Architecture: {t.architecture}")
            if t.domain:
                body_parts.append(f"- Domain: {t.domain}")

        if body_parts:
            lines.append("### Commit Message")
            lines.append("")
            lines.append("````")
            lines.extend(body_parts)
            lines.append("````")
            lines.append("")

        # File table
        if commit.files:
            lines.append("### Files")
            lines.append("")
            lines.append("| Status | Path |")
            lines.append("|:------:|:-----|")
            for f in commit.files:
                icon = _STATUS_ICONS.get(f.status, f.status)
                lines.append(f"| {icon} | `{f.path}` |")
            lines.append("")

        # Module docstrings
        if commit.docstrings:
            lines.append("### Module Docstrings")
            lines.append("")
            for mod_path, docstring in sorted(commit.docstrings.items()):
                # Skip tiny __init__.py docstrings
                if mod_path.endswith("__init__.py") and len(docstring) < 40:
                    continue
                display_path = mod_path.replace("\\", "/")
                lines.append(f"#### `{display_path}`")
                lines.append("")
                lines.append("```python")
                # Show first ~30 lines to keep review manageable
                ds_lines = docstring.splitlines()
                if len(ds_lines) > 30:
                    lines.append('"""')
                    lines.extend(ds_lines[:30])
                    lines.append(f"    ... ({len(ds_lines) - 30} more lines)")
                    lines.append('"""')
                else:
                    lines.append(f'"""{docstring}"""')
                lines.append("```")
                lines.append("")

        # Sidecar content
        if commit.sidecar:
            sc = commit.sidecar
            if sc.migration_guide:
                lines.append("### Migration Guide")
                lines.append("")
                lines.append(sc.migration_guide)
                lines.append("")
            if sc.examples:
                lines.append("### Examples")
                lines.append("")
                lines.append(sc.examples)
                lines.append("")

        lines.append("---")
        lines.append("")
        return lines

    # ------------------------------------------------------------------
    # api_index.md
    # ------------------------------------------------------------------

    def render_api_index(self) -> str:
        """Render the module index grouped by Doc-Type, Tier, and Stability."""
        lines: list[str] = []
        total = len(self.modules)
        with_headers = sum(1 for m in self.modules if m.has_header_fields)

        lines.append("# API Module Index")
        lines.append("")
        lines.append(
            f"> **{total}** modules | "
            f"**{with_headers}** with Doc Headers"
        )
        lines.append("")

        # By Doc-Type
        lines.append("## By Doc-Type")
        lines.append("")
        for dt_name in sorted(self.module_index.by_doc_type.keys()):
            mods = self.module_index.by_doc_type[dt_name]
            lines.append(f"### {dt_name} ({len(mods)} modules)")
            lines.append("")
            lines.append("| Module | Stability | Tier | Summary |")
            lines.append("|:-------|:---------:|:----:|:--------|")
            for mod in sorted(mods, key=lambda m: m.module_path):
                h = mod.header
                if h:
                    lines.append(
                        f"| `{mod.module_path}` | {h.stability.value} "
                        f"| {h.tier.value} | {h.summary} |"
                    )
            lines.append("")

        # By Tier
        lines.append("## By Tier")
        lines.append("")
        for tier_name in ["basic", "standard", "full", "none"]:
            mods = self.module_index.by_tier.get(tier_name, [])
            if not mods:
                continue
            lines.append(f"### {tier_name} ({len(mods)} modules)")
            lines.append("")
            lines.append("| Module | Summary |")
            lines.append("|:-------|:--------|")
            for mod in sorted(mods, key=lambda m: m.module_path):
                h = mod.header
                if h:
                    lines.append(f"| `{mod.module_path}` | {h.summary} |")
            lines.append("")

        # By Stability
        lines.append("## By Stability")
        lines.append("")
        for stab_name in ["experimental", "stable", "deprecated"]:
            mods = self.module_index.by_stability.get(stab_name, [])
            if not mods:
                continue
            lines.append(f"### {stab_name} ({len(mods)} modules)")
            lines.append("")
            lines.append("| Module | Tier | Summary |")
            lines.append("|:-------|:----:|:--------|")
            for mod in sorted(mods, key=lambda m: m.module_path):
                h = mod.header
                if h:
                    lines.append(
                        f"| `{mod.module_path}` | {h.tier.value} | {h.summary} |"
                    )
            lines.append("")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Diagrams
    # ------------------------------------------------------------------

    def _extract_diagrams(self, diagram_dir: Path) -> list[Path]:
        """Extract Mermaid diagrams from docstrings and sidecar content."""
        diagrams: list[tuple[str, str]] = []  # (name, mermaid_content)

        # From module docstrings
        for mod in self.modules:
            if mod.header and mod.header.raw:
                for i, match in enumerate(_MERMAID_RE.finditer(mod.header.raw)):
                    name = mod.module_path.replace(".", "_")
                    if i > 0:
                        name += f"_{i + 1}"
                    diagrams.append((name, match.group(1).strip()))

        # From sidecar files
        for commit in self.all_commits:
            if commit.sidecar and commit.sidecar.diagrams:
                for i, diagram in enumerate(commit.sidecar.diagrams):
                    name = f"commit_{commit.short_sha}"
                    if i > 0:
                        name += f"_{i + 1}"
                    diagrams.append((name, diagram))

        if not diagrams:
            return []

        diagram_dir.mkdir(parents=True, exist_ok=True)
        paths: list[Path] = []
        for name, content in diagrams:
            path = diagram_dir / f"{name}.mmd"
            path.write_text(content + "\n", encoding="utf-8")
            paths.append(path)

        return paths
