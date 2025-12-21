"""CLI entry point for the changelog generation system.

Stability: stable
Tier: none
Since: 0.4.0
Dependencies: stdlib-only
Doc-Types: API_REFERENCE
Tags: changelog, cli

Provides a simple ``__main__``-compatible CLI using only argparse.
No typer/click/rich dependency required.

Usage::

    # Generate all outputs
    python -m spine.tools.changelog generate

    # Generate specific target
    python -m spine.tools.changelog generate --target changelog

    # From fixture data
    python -m spine.tools.changelog generate --fixture-dir tests/fixtures/changelog_repo

    # Detect missing doc headers
    python -m spine.tools.changelog detect-headers

    # Validate generated output is up-to-date
    python -m spine.tools.changelog validate
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .generator import VALID_TARGETS, ChangelogGenerator
from .parse_docstrings import detect_missing_headers, scan_modules


def main(argv: list[str] | None = None) -> int:
    """CLI entry point.

    Args:
        argv: Command-line arguments (defaults to sys.argv[1:]).

    Returns:
        Exit code (0 = success, 1 = error, 2 = validation failure).
    """
    parser = argparse.ArgumentParser(
        prog="spine-changelog",
        description="Generate changelog and documentation artifacts for spine-core.",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="Enable verbose logging.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # --- generate ---
    gen_parser = sub.add_parser(
        "generate",
        help="Generate documentation artifacts.",
    )
    gen_parser.add_argument(
        "--source-root", type=Path, default=Path("src/spine"),
        help="Path to source root (default: src/spine).",
    )
    gen_parser.add_argument(
        "--output-dir", type=Path, default=Path("docs/_generated"),
        help="Output directory (default: docs/_generated).",
    )
    gen_parser.add_argument(
        "--fixture-dir", type=Path, default=None,
        help="Load from fixtures instead of live git.",
    )
    gen_parser.add_argument(
        "--phase-map", type=Path, default=None,
        help="Path to phase_map.toml or phase_map.json.",
    )
    gen_parser.add_argument(
        "--commit-notes-dir", type=Path, default=None,
        help="Path to sidecar commit notes directory.",
    )
    gen_parser.add_argument(
        "--target", action="append", dest="targets",
        choices=sorted(VALID_TARGETS),
        help="Specific target(s) to generate (default: all).",
    )
    gen_parser.add_argument(
        "--project-name", default="spine-core",
        help="Project name for output headers.",
    )
    gen_parser.add_argument(
        "--project-version", default="",
        help="Project version for changelog header.",
    )

    # --- detect-headers ---
    detect_parser = sub.add_parser(
        "detect-headers",
        help="Report modules missing Doc Header fields.",
    )
    detect_parser.add_argument(
        "--source-root", type=Path, default=Path("src/spine"),
        help="Path to source root (default: src/spine).",
    )
    detect_parser.add_argument(
        "--min-length", type=int, default=20,
        help="Minimum docstring length to report (default: 20).",
    )

    # --- validate ---
    validate_parser = sub.add_parser(
        "validate",
        help="Validate that generated output matches checked-in files.",
    )
    validate_parser.add_argument(
        "--output-dir", type=Path, default=Path("docs/_generated"),
        help="Directory containing checked-in generated files.",
    )
    validate_parser.add_argument(
        "--source-root", type=Path, default=Path("src/spine"),
        help="Path to source root.",
    )

    args = parser.parse_args(argv)

    # Configure logging
    level = logging.DEBUG if args.verbose else logging.WARNING
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")

    if args.command == "generate":
        return _cmd_generate(args)
    elif args.command == "detect-headers":
        return _cmd_detect_headers(args)
    elif args.command == "validate":
        return _cmd_validate(args)
    else:
        parser.print_help()
        return 1


def _cmd_generate(args: argparse.Namespace) -> int:
    """Execute the generate command."""
    gen = ChangelogGenerator(
        source_root=args.source_root,
        output_dir=args.output_dir,
        fixture_dir=args.fixture_dir,
        phase_map_path=args.phase_map,
        commit_notes_dir=args.commit_notes_dir,
        project_name=args.project_name,
        project_version=args.project_version,
    )

    outputs = gen.generate(targets=args.targets)

    print(f"Generated {len(outputs)} output(s):")
    for name, path in sorted(outputs.items()):
        print(f"  {name}: {path}")

    if gen.warnings:
        print(f"\n{len(gen.warnings)} warning(s):")
        for w in gen.warnings:
            print(f"  [{w.source}] {w.field}: {w.message}")

    return 0


def _cmd_detect_headers(args: argparse.Namespace) -> int:
    """Execute the detect-headers command."""
    modules, warns = scan_modules(args.source_root)
    missing = detect_missing_headers(modules, min_docstring_length=args.min_length)

    total = len(modules)
    with_headers = sum(1 for m in modules if m.has_header_fields)

    print(f"Module scan: {total} total, {with_headers} with Doc Headers")
    print(f"Missing headers: {len(missing)}")
    print()

    if missing:
        print("Modules with docstrings but no Doc Header fields:")
        print()
        for mod in missing:
            summary = mod.header.summary[:60] if mod.header else "(no docstring)"
            print(f"  {mod.path}")
            print(f"    {summary}")
        print()
        print(
            "Add Stability/Tier/Doc-Types/Tags fields after the summary line. "
            "See docs/changelog_system/01_DOC_HEADERS.md for format."
        )

    return 0


def _cmd_validate(args: argparse.Namespace) -> int:
    """Validate generated output matches checked-in files."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        gen = ChangelogGenerator(
            source_root=args.source_root,
            output_dir=tmp_path,
        )
        gen.generate()

        # Compare each generated file with checked-in version
        mismatches: list[str] = []
        for gen_file in sorted(tmp_path.rglob("*")):
            if gen_file.is_dir():
                continue
            rel = gen_file.relative_to(tmp_path)
            checked_in = args.output_dir / rel

            if not checked_in.exists():
                mismatches.append(f"  MISSING: {rel}")
                continue

            gen_content = gen_file.read_text(encoding="utf-8")
            ci_content = checked_in.read_text(encoding="utf-8")

            if gen_content != ci_content:
                mismatches.append(f"  DIFFERS: {rel}")

        if mismatches:
            print("Validation FAILED — generated files differ from checked-in:")
            for m in mismatches:
                print(m)
            print("\nRun 'make changelog' and commit the updated files.")
            return 2
        else:
            print("Validation passed — generated files are up-to-date.")
            return 0


if __name__ == "__main__":
    sys.exit(main())
