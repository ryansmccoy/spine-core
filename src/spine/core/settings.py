"""Shared base settings for all Spine packages.

Every spine service shares common configuration needs (host, port, log level,
debug mode, data directory).  ``SpineBaseSettings`` provides these as a base
class so each spine only declares its domain-specific fields.

Manifesto:
    Configuration should be explicit, validated, and environment-driven.
    Without a shared base, each spine reinvents settings with inconsistent
    field names, missing validation, and no .env support.

    - **Pydantic validation:** Type-checked at startup, not runtime
    - **Environment-driven:** Reads from env vars and .env files
    - **Hierarchical:** Each spine adds its own prefix (GENAI_, SEARCH_, etc.)
    - **Sensible defaults:** Works out of the box for development

Features:
    - **SpineBaseSettings:** Base class with host, port, debug, log_level, data_dir
    - **env_prefix:** Per-spine environment variable namespacing
    - **.env file support:** Automatic loading via pydantic-settings
    - **Extra ignore:** Unknown env vars don't cause startup failures

Examples:
    >>> from spine.core.settings import SpineBaseSettings
    >>> class KnowledgeSettings(SpineBaseSettings):
    ...     model_config = {"env_prefix": "KNOWLEDGE_"}
    ...     graph_backend: str = "memory"

Tags:
    settings, configuration, pydantic, environment, spine-core,
    base-class, env-prefix

Doc-Types:
    - API Reference
    - Configuration Guide

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
