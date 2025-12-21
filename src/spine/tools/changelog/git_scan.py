"""Git history scanning for changelog generation.

Stability: stable
Tier: none
Since: 0.4.0
Dependencies: stdlib-only
Doc-Types: API_REFERENCE, TECHNICAL_DESIGN
Tags: changelog, git, scanner

Extracts commit history from a git repository via ``subprocess`` calls,
or from fixture files for deterministic testing. Produces raw commit
data that ``parse_commit_notes`` converts into ``CommitNote`` objects.

Architecture::

    ┌─────────────────────────────────────────────────┐
    │                  git_scan.py                     │
    ├─────────────────────┬───────────────────────────┤
    │  LiveGitScanner     │  FixtureGitScanner        │
    │  (subprocess calls) │  (reads fixture files)    │
    └─────────────────────┴───────────────────────────┘
                │                     │
                ▼                     ▼
         CommitNote[]           CommitNote[]

Usage::

    from spine.tools.changelog.git_scan import scan_git_history

    # Live git
    commits = scan_git_history(repo_dir=Path("."))

    # From fixtures
    commits = scan_git_history(fixture_dir=Path("tests/fixtures/changelog_repo"))
"""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path

from .model import CommitFile, CommitNote, PhaseGroup, ValidationWarning
from .parse_commit_notes import (
    load_sidecar_dir,
    parse_commit_message,
)

logger = logging.getLogger(__name__)

# Git log format: SHA, short SHA, subject, date, author, body
# Use a unique string separator instead of null byte (Windows rejects null in args)
_GIT_LOG_FORMAT = "%H%n%h%n%s%n%aI%n%aN%n%B"
_RECORD_SEP = "---COMMIT_RECORD_SEP---"


def scan_git_history(
    *,
    repo_dir: Path | None = None,
    fixture_dir: Path | None = None,
    branch: str | None = None,
    sidecar_dir: Path | None = None,
    source_prefix: str = "src/spine/",
) -> tuple[list[CommitNote], list[ValidationWarning]]:
    """Scan git history and return parsed commit notes.

    Exactly one of ``repo_dir`` or ``fixture_dir`` must be provided.

    Args:
        repo_dir: Path to git repository root (for live scanning).
        fixture_dir: Path to fixture directory (for testing).
        branch: Git branch/ref to scan (default: current HEAD).
        sidecar_dir: Path to commit notes sidecar directory.
        source_prefix: Path prefix for source files (for docstring extraction).

    Returns:
        Tuple of (list of CommitNote, list of validation warnings).

    Raises:
        ValueError: If neither or both of repo_dir/fixture_dir are provided.
    """
    if fixture_dir is not None:
        return _scan_fixtures(fixture_dir)
    if repo_dir is not None:
        return _scan_live(
            repo_dir, branch=branch,
            sidecar_dir=sidecar_dir,
            source_prefix=source_prefix,
        )
    msg = "Provide either repo_dir or fixture_dir"
    raise ValueError(msg)


def _scan_live(
    repo_dir: Path,
    *,
    branch: str | None = None,
    sidecar_dir: Path | None = None,
    source_prefix: str = "src/spine/",
) -> tuple[list[CommitNote], list[ValidationWarning]]:
    """Scan a live git repository."""
    all_warns: list[ValidationWarning] = []

    # Load sidecars if directory exists
    sidecar_map: dict[str, object] = {}
    if sidecar_dir:
        sidecar_map = load_sidecar_dir(sidecar_dir)
    elif (repo_dir / "docs" / "commit_notes").is_dir():
        sidecar_map = load_sidecar_dir(repo_dir / "docs" / "commit_notes")

    # Get commit list
    cmd = ["git", "log", "--reverse", f"--format={_GIT_LOG_FORMAT}\n{_RECORD_SEP}"]
    if branch:
        cmd.append(branch)
    try:
        result = subprocess.run(
            cmd, capture_output=True, cwd=str(repo_dir),
            check=True, timeout=30,
        )
        stdout = result.stdout.decode("utf-8", errors="replace")
        result_stdout = stdout
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as exc:
        logger.error("Git log failed: %s", exc)
        return [], []

    commits: list[CommitNote] = []
    records = result_stdout.strip().split(_RECORD_SEP)

    for record in records:
        record = record.strip()
        if not record:
            continue

        lines = record.split("\n", 5)
        if len(lines) < 5:
            continue

        sha = lines[0].strip()
        short_sha = lines[1].strip()
        # lines[2] = subject (we get it from full body parsing)
        date = lines[3].strip()
        author = lines[4].strip()
        body = lines[5].strip() if len(lines) > 5 else lines[2].strip()

        # Get files for this commit
        files = _get_commit_files(repo_dir, sha)

        # Get docstrings for new source files
        docstrings = _get_commit_docstrings(repo_dir, sha, files, source_prefix)

        # Get sidecar content
        sidecar = sidecar_map.get(short_sha)

        note, warns = parse_commit_message(
            body, sha=sha, short_sha=short_sha,
            date=date, author=author,
            files=files, sidecar=sidecar,
            docstrings=docstrings,
        )
        all_warns.extend(warns)
        commits.append(note)

    return commits, all_warns


def _get_commit_files(repo_dir: Path, sha: str) -> list[CommitFile]:
    """Get the list of files changed in a commit."""
    try:
        # Use diff-tree for non-root commits, ls-tree for root
        result = subprocess.run(
            ["git", "diff-tree", "--no-commit-id", "-r", "--name-status", sha],
            capture_output=True, cwd=str(repo_dir),
            check=True, timeout=10,
        )
        output = result.stdout.decode("utf-8", errors="replace").strip()

        # If empty, might be root commit — use ls-tree
        if not output:
            result = subprocess.run(
                ["git", "ls-tree", "-r", "--name-only", sha],
                capture_output=True, cwd=str(repo_dir),
                check=True, timeout=10,
            )
            return [
                CommitFile(path=line.strip(), status="A")
                for line in result.stdout.decode("utf-8", errors="replace").strip().splitlines()
                if line.strip()
            ]

        files: list[CommitFile] = []
        for line in output.splitlines():
            parts = line.split("\t", 1)
            if len(parts) == 2:
                status = parts[0].strip()[0]  # First char: A, M, D, R, C
                path = parts[1].strip()
                files.append(CommitFile(path=path, status=status))
        return files

    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return []


def _get_commit_docstrings(
    repo_dir: Path,
    sha: str,
    files: list[CommitFile],
    source_prefix: str,
) -> dict[str, str]:
    """Extract module docstrings for new source files in a commit."""
    docstrings: dict[str, str] = {}

    for f in files:
        if f.status != "A":
            continue
        if not f.path.startswith(source_prefix):
            continue
        if not f.path.endswith(".py"):
            continue

        try:
            result = subprocess.run(
                ["git", "show", f"{sha}:{f.path}"],
                capture_output=True, cwd=str(repo_dir),
                check=True, timeout=5,
            )
            file_content = result.stdout.decode("utf-8", errors="replace")
            import ast as _ast
            tree = _ast.parse(file_content)
            ds = _ast.get_docstring(tree)
            if ds:
                # Use module path relative to source_prefix parent
                mod_path = f.path
                if mod_path.startswith("src/"):
                    mod_path = mod_path[4:]  # strip "src/"
                docstrings[mod_path] = ds
        except Exception:
            pass

    return docstrings


def _scan_fixtures(
    fixture_dir: Path,
) -> tuple[list[CommitNote], list[ValidationWarning]]:
    """Load commit data from fixture files.

    Expected fixture structure::

        fixture_dir/
        ├── commits.json     # List of commit records
        ├── commit_notes/    # Optional sidecar files
        │   └── <sha>.md
        └── src/spine/       # Optional source tree for docstrings
            └── ...

    Each entry in ``commits.json``::

        {
            "sha": "abc1234...",
            "short_sha": "abc1234",
            "date": "2026-02-15T08:00:00-05:00",
            "author": "Ryan McCoy",
            "message": "feat(core): ...\n\nWhat:\n- ...",
            "files": [{"path": "src/spine/core/foo.py", "status": "A"}]
        }
    """
    commits_file = fixture_dir / "commits.json"
    if not commits_file.is_file():
        logger.warning("No commits.json in fixture dir: %s", fixture_dir)
        return [], []

    raw = json.loads(commits_file.read_text(encoding="utf-8"))
    sidecar_map = load_sidecar_dir(fixture_dir / "commit_notes")

    all_warns: list[ValidationWarning] = []
    commits: list[CommitNote] = []

    for entry in raw:
        sha = entry.get("sha", "")
        short_sha = entry.get("short_sha", sha[:7])
        date = entry.get("date", "")
        author = entry.get("author", "")
        message = entry.get("message", "")
        files = [
            CommitFile(path=f["path"], status=f.get("status", "A"))
            for f in entry.get("files", [])
        ]
        docstrings = entry.get("docstrings", {})
        sidecar = sidecar_map.get(short_sha)

        note, warns = parse_commit_message(
            message, sha=sha, short_sha=short_sha,
            date=date, author=author,
            files=files, sidecar=sidecar,
            docstrings=docstrings,
        )
        all_warns.extend(warns)
        commits.append(note)

    return commits, all_warns


def load_phase_map(
    path: Path,
) -> list[PhaseGroup]:
    """Load phase groupings from a TOML file.

    Falls back to JSON if TOML parsing is unavailable (Python < 3.11
    without tomli).

    Args:
        path: Path to ``phase_map.toml`` or ``phase_map.json``.

    Returns:
        List of PhaseGroup objects (without commits populated).
    """
    if not path.is_file():
        return []

    text = path.read_text(encoding="utf-8")

    if path.suffix == ".json":
        data = json.loads(text)
    elif path.suffix == ".toml":
        try:
            import tomllib  # Python 3.11+
        except ImportError:
            try:
                import tomli as tomllib  # type: ignore[no-redef]
            except ImportError:
                logger.warning(
                    "TOML parsing unavailable — install tomli or use Python 3.11+. "
                    "Falling back to empty phase map."
                )
                return []
        data = tomllib.loads(text)
    else:
        logger.warning("Unknown phase map format: %s", path.suffix)
        return []

    phases_data = data.get("phases", {})
    groups: list[PhaseGroup] = []

    for key in sorted(phases_data.keys(), key=lambda k: int(k) if k.isdigit() else 999):
        phase = phases_data[key]
        groups.append(PhaseGroup(
            number=int(key) if key.isdigit() else len(groups) + 1,
            name=phase.get("name", f"Phase {key}"),
        ))

    return groups


def assign_commits_to_phases(
    commits: list[CommitNote],
    phase_map_path: Path | None,
) -> list[PhaseGroup]:
    """Group commits into phases using the phase map.

    If no phase map exists, creates a single phase containing all commits.

    Args:
        commits: Ordered list of all commits.
        phase_map_path: Path to the phase map file.

    Returns:
        List of PhaseGroup objects with commits assigned.
    """
    if phase_map_path and phase_map_path.is_file():
        groups = load_phase_map(phase_map_path)
        if groups:
            return _assign_by_phase_map(commits, phase_map_path, groups)

    # Fallback: single phase with all commits
    group = PhaseGroup(number=1, name="All Commits", commits=list(commits))
    return [group]


def _assign_by_phase_map(
    commits: list[CommitNote],
    phase_map_path: Path,
    groups: list[PhaseGroup],
) -> list[PhaseGroup]:
    """Assign commits to phases using explicit SHA lists from the phase map."""
    text = phase_map_path.read_text(encoding="utf-8")

    if phase_map_path.suffix == ".json":
        data = json.loads(text)
    else:
        try:
            import tomllib
        except ImportError:
            import tomli as tomllib  # type: ignore[no-redef]
        data = tomllib.loads(text)

    phases_data = data.get("phases", {})

    # Build SHA → phase index mapping
    sha_to_phase: dict[str, int] = {}
    for key, phase in phases_data.items():
        idx = int(key) if key.isdigit() else -1
        for sha in phase.get("commits", []):
            sha_to_phase[sha] = idx

    # Build commit lookup by short SHA
    commit_map = {c.short_sha: c for c in commits}

    # Assign commits to groups
    assigned_shas: set[str] = set()
    for group in groups:
        phase_data = phases_data.get(str(group.number), {})
        for sha in phase_data.get("commits", []):
            if sha in commit_map:
                group.commits.append(commit_map[sha])
                assigned_shas.add(sha)

    # Any unassigned commits go into a catch-all phase
    unassigned = [c for c in commits if c.short_sha not in assigned_shas]
    if unassigned:
        groups.append(PhaseGroup(
            number=len(groups) + 1,
            name="Unassigned",
            commits=unassigned,
        ))

    return groups
