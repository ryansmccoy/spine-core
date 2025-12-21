"""Parse Commit Notes from git commit messages and sidecar files.

Stability: stable
Tier: none
Since: 0.4.0
Dependencies: stdlib-only
Doc-Types: API_REFERENCE
Tags: changelog, parser, commit, trailers

Parses the hybrid commit-notes format: structured trailers from
commit messages plus optional rich sidecar markdown files from
``docs/commit_notes/<sha>.md``.

Usage::

    from spine.tools.changelog.parse_commit_notes import (
        parse_commit_message,
        parse_sidecar_file,
    )

    note = parse_commit_message(message_text, sha="a1b2c3d")
    sidecar = parse_sidecar_file(Path("docs/commit_notes/a1b2c3d.md"))
"""

from __future__ import annotations

import re
from pathlib import Path

from .model import (
    VALID_ARCHITECTURE,
    VALID_DOMAIN,
    VALID_FEATURE_TYPES,
    VALID_IMPACT,
    VALID_MARKERS,
    VALID_MIGRATION,
    CommitFile,
    CommitNote,
    CommitTrailers,
    Impact,
    Migration,
    SidecarContent,
    ValidationWarning,
)

# Regex for conventional commit subject line
_SUBJECT_RE = re.compile(
    r"^(?P<type>[a-z]+)"           # type (feat, fix, etc.)
    r"(?:\((?P<scope>[^)]+)\))?"   # optional scope
    r":\s*"                        # colon + space
    r"(?P<desc>.+)"                # description
    r"$"
)

# Regex for trailer lines (Key: value or Key: value1, value2)
_TRAILER_RE = re.compile(r"^(?P<key>[A-Za-z][\w-]*)\s*:\s*(?P<value>.+)$")

# Known trailer keys (case-insensitive matching)
_TRAILER_KEYS = frozenset({
    "impact", "migration", "migration-notes", "feature-type",
    "architecture", "domain", "surfaces", "tags", "markers", "sidecar",
})

# Body section headers
_SECTION_HEADERS = frozenset({"what:", "why:", "testing:", "classification:"})

# Mermaid fence pattern
_MERMAID_RE = re.compile(
    r"```mermaid\s*\n(.*?)```",
    re.DOTALL,
)


def parse_commit_message(
    message: str,
    *,
    sha: str = "",
    short_sha: str = "",
    date: str = "",
    author: str = "",
    files: list[CommitFile] | None = None,
    sidecar: SidecarContent | None = None,
    docstrings: dict[str, str] | None = None,
) -> tuple[CommitNote, list[ValidationWarning]]:
    """Parse a full commit message into a CommitNote.

    Extracts the subject line, body sections (What/Why), structured
    trailers, and merges with optional sidecar content.

    Args:
        message: Complete commit message text.
        sha: Full commit SHA.
        short_sha: 7-character short SHA (derived from sha if empty).
        date: Commit date string.
        author: Commit author name.
        files: List of files touched by this commit.
        sidecar: Pre-parsed sidecar content (if any).
        docstrings: Module path → docstring mapping.

    Returns:
        Tuple of (CommitNote, list of validation warnings).
    """
    warns: list[ValidationWarning] = []
    lines = message.strip().splitlines()

    if not lines:
        return CommitNote(sha=sha, short_sha=short_sha or sha[:7], subject=""), warns

    subject = lines[0].strip()
    if not short_sha:
        short_sha = sha[:7] if sha else ""

    # Parse body sections and trailers
    body_what = ""
    body_why = ""
    trailer_map: dict[str, str] = {}

    current_section = ""
    section_lines: dict[str, list[str]] = {"what": [], "why": [], "testing": []}

    for line in lines[1:]:
        stripped = line.strip()
        lower = stripped.lower()

        # Check for section header
        if lower in _SECTION_HEADERS:
            current_section = lower.rstrip(":")
            continue

        # Check for Classification: section (following lines are trailers)
        if lower == "classification:":
            current_section = "classification"
            continue

        # In classification section, strip leading bullet "- "
        check_line = stripped
        if current_section == "classification" and check_line.startswith("- "):
            check_line = check_line[2:].strip()

        # Check for trailer line
        trailer_match = _TRAILER_RE.match(check_line)
        if trailer_match:
            key = trailer_match.group("key").lower()
            value = trailer_match.group("value").strip()
            if key in _TRAILER_KEYS or current_section == "classification":
                trailer_map[key] = value
                continue

        # Accumulate section content
        if current_section in section_lines:
            # Strip leading "- " from bullet items
            content = stripped.lstrip("- ").strip() if stripped.startswith("- ") else stripped
            if content:
                section_lines[current_section].append(content)

    body_what = "\n".join(section_lines.get("what", []))
    body_why = "\n".join(section_lines.get("why", []))

    # Parse trailers into CommitTrailers
    trailers = _parse_trailers(trailer_map, subject, warns)

    return CommitNote(
        sha=sha,
        short_sha=short_sha,
        subject=subject,
        date=date,
        author=author,
        body_what=body_what,
        body_why=body_why,
        trailers=trailers,
        files=tuple(files or []),
        sidecar=sidecar,
        docstrings=docstrings or {},
    ), warns


def _parse_trailers(
    raw: dict[str, str],
    source: str,
    warns: list[ValidationWarning],
) -> CommitTrailers:
    """Convert raw trailer key-value pairs into a validated CommitTrailers."""

    # Impact
    impact = Impact.INTERNAL
    if "impact" in raw:
        val = raw["impact"].lower()
        if val in VALID_IMPACT:
            impact = Impact(val)
        else:
            warns.append(ValidationWarning(
                source=source, field="Impact", value=val,
                message=f"Unknown impact '{val}'",
            ))

    # Migration
    migration = Migration.NONE
    if "migration" in raw:
        val = raw["migration"].lower()
        if val in VALID_MIGRATION:
            migration = Migration(val)
        else:
            warns.append(ValidationWarning(
                source=source, field="Migration", value=val,
                message=f"Unknown migration '{val}'",
            ))

    migration_notes = raw.get("migration-notes", "")

    # Feature-Type
    feature_type = raw.get("feature-type", "")
    if feature_type and feature_type.lower() not in VALID_FEATURE_TYPES:
        warns.append(ValidationWarning(
            source=source, field="Feature-Type", value=feature_type,
            message=f"Unknown feature-type '{feature_type}'",
        ))

    # Architecture
    architecture = raw.get("architecture", "")
    if architecture:
        for arch in (a.strip() for a in architecture.split(",")):
            if arch.lower() not in VALID_ARCHITECTURE:
                warns.append(ValidationWarning(
                    source=source, field="Architecture", value=arch,
                    message=f"Unknown architecture '{arch}'",
                ))

    # Domain
    domain = raw.get("domain", "")
    if domain:
        for dom in (d.strip() for d in domain.split(",")):
            if dom.lower() not in VALID_DOMAIN:
                warns.append(ValidationWarning(
                    source=source, field="Domain", value=dom,
                    message=f"Unknown domain '{dom}'",
                ))

    # Surfaces
    surfaces: tuple[str, ...] = ()
    if "surfaces" in raw:
        surfaces = tuple(s.strip() for s in raw["surfaces"].split(",") if s.strip())

    # Tags
    tags: tuple[str, ...] = ()
    if "tags" in raw:
        tags = tuple(t.strip().lower() for t in raw["tags"].split(",") if t.strip())

    # Markers
    markers: tuple[str, ...] = ()
    if "markers" in raw:
        raw_markers = [m.strip().upper() for m in raw["markers"].split(",") if m.strip()]
        for m in raw_markers:
            if m not in VALID_MARKERS:
                warns.append(ValidationWarning(
                    source=source, field="Markers", value=m,
                    message=f"Unknown marker '{m}'",
                ))
        markers = tuple(raw_markers)

    # Sidecar flag
    has_sidecar = raw.get("sidecar", "").lower() in ("true", "yes", "1")

    return CommitTrailers(
        impact=impact,
        migration=migration,
        migration_notes=migration_notes,
        feature_type=feature_type,
        architecture=architecture,
        domain=domain,
        surfaces=surfaces,
        tags=tags,
        markers=markers,
        has_sidecar=has_sidecar,
    )


def parse_sidecar_file(path: Path) -> SidecarContent | None:
    """Parse a sidecar markdown file for rich commit content.

    Args:
        path: Path to the sidecar ``.md`` file.

    Returns:
        SidecarContent if the file exists and can be parsed, else None.
    """
    if not path.is_file():
        return None

    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None

    return parse_sidecar_text(text)


def parse_sidecar_text(text: str) -> SidecarContent:
    """Parse sidecar markdown text into structured content.

    Extracts named sections (Migration Guide, Examples) and
    Mermaid diagram fenced blocks.

    Args:
        text: Raw markdown text.

    Returns:
        SidecarContent with extracted sections.
    """
    migration_guide = _extract_section(text, "Migration Guide")
    examples = _extract_section(text, "Examples")

    # Extract all mermaid diagrams
    diagrams = tuple(m.group(1).strip() for m in _MERMAID_RE.finditer(text))

    return SidecarContent(
        migration_guide=migration_guide,
        examples=examples,
        diagrams=diagrams,
        raw=text,
    )


def _extract_section(text: str, heading: str) -> str:
    """Extract content under a markdown ## heading.

    Returns content from after the heading line until the next
    heading of equal or higher level (or end of text).
    """
    pattern = re.compile(
        rf"^##\s+{re.escape(heading)}\s*$",
        re.MULTILINE,
    )
    match = pattern.search(text)
    if not match:
        return ""

    start = match.end()
    # Find next heading of level 1 or 2
    next_heading = re.search(r"^#{1,2}\s+", text[start:], re.MULTILINE)
    if next_heading:
        end = start + next_heading.start()
    else:
        end = len(text)

    return text[start:end].strip()


def load_sidecar_dir(
    sidecar_dir: Path,
) -> dict[str, SidecarContent]:
    """Load all sidecar files from a directory.

    Args:
        sidecar_dir: Path to ``docs/commit_notes/`` directory.

    Returns:
        Dict mapping short SHA to parsed SidecarContent.
    """
    result: dict[str, SidecarContent] = {}
    if not sidecar_dir.is_dir():
        return result

    for md_file in sorted(sidecar_dir.glob("*.md")):
        short_sha = md_file.stem  # filename without .md
        content = parse_sidecar_file(md_file)
        if content is not None:
            result[short_sha] = content

    return result
