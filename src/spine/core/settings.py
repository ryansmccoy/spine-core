"""Shared base settings for all Spine packages.

Every spine service shares common configuration needs (host, port, log level,
debug mode, data directory).  ``SpineBaseSettings`` provides these as a base
class so each spine only declares its domain-specific fields.

Usage::

    from spine.core.settings import SpineBaseSettings

    class KnowledgeSettings(SpineBaseSettings):
        model_config = {"env_prefix": "KNOWLEDGE_"}

        graph_backend: str = "memory"
        neo4j_uri: str = "bolt://localhost:7687"

Requires the ``pydantic-settings`` optional extra::

    pip install spine-core[settings]
"""

from __future__ import annotations

from pathlib import Path

try:
    from pydantic_settings import BaseSettings, SettingsConfigDict
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "spine.core.settings requires pydantic-settings. Install it with: pip install spine-core[settings]"
    ) from exc

from pydantic import Field


class SpineBaseSettings(BaseSettings):
    """Common settings shared across all Spine services.

    Each spine subclass should set ``model_config`` with its own ``env_prefix``
    (e.g. ``GENAI_``, ``SEARCH_``, ``KNOWLEDGE_``).

    Fields
    ──────
    host         : Bind address for HTTP/MCP transports
    port         : Bind port for HTTP/MCP transports (override per spine)
    debug        : Enable debug mode (verbose logging, etc.)
    log_level    : Structlog log level
    data_dir     : Per-spine persistent data directory
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Network ──────────────────────────────────────────────────
    host: str = "0.0.0.0"
    port: int = 8000  # override per spine

    # ── Observability ────────────────────────────────────────────
    debug: bool = False
    log_level: str = "INFO"

    # ── Storage ──────────────────────────────────────────────────
    data_dir: Path = Field(
        default_factory=lambda: Path.home() / ".spine",
        description="Per-spine persistent data directory",
    )
