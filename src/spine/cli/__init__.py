"""
CLI layer for spine-core.

Provides a Typer application with sub-commands that delegate to the
operations layer (``spine.ops``).  All business logic lives in ops —
this package handles only terminal transport: argument parsing,
coloured output, and table formatting.

Entry point::

    spine-core --help
"""

from spine.cli.app import app

__all__ = ["app"]
